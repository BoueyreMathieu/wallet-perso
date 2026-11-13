# Durcit le fichier .env sans jamais afficher de secret :
#   1. remplace APP_PASSWORD (en clair) par APP_PASSWORD_HASH (empreinte scrypt) ;
#   2. met COOKIE_SECURE=true ;
#   3. redemarre l'API (les sessions ouvertes dans les navigateurs sont fermees ; l'appli Android reste connectee).
# Prerequis : l'appli tourne deja avec la version 0.8 (docker compose up -d --build).
# Usage (depuis le dossier wallet-perso) :  powershell -ExecutionPolicy Bypass -File scripts\securiser-env.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root ".env"
Set-Location $root

if (-not (Test-Path $envPath)) {
    Write-Host ".env introuvable." -ForegroundColor Red
    exit 1
}

Write-Host "Choisis le mot de passe de l'appli (16 caracteres ou plus conseilles, idealement genere par ton gestionnaire)."
Write-Host "Tu peux reprendre le mot de passe actuel ou en profiter pour en mettre un nouveau."
$s1 = Read-Host "Mot de passe" -AsSecureString
$s2 = Read-Host "Encore une fois" -AsSecureString
$p1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s1))
$p2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s2))
if ($p1 -ne $p2) { Write-Host "Les deux saisies ne correspondent pas." -ForegroundColor Red; exit 1 }
if ($p1.Length -lt 12) { Write-Host "Trop court : 12 caracteres minimum." -ForegroundColor Red; exit 1 }

# Le mot de passe passe par l'entree standard du conteneur (jamais en argument, jamais dans un fichier).
$OutputEncoding = New-Object System.Text.UTF8Encoding $false
$hash = ($p1 | docker compose exec -T api python -m app.tools.hash_password --stdin)
$p1 = $null; $p2 = $null
if (-not ($hash -match '^scrypt:\d+:\d+:\d+:[A-Za-z0-9_-]+:[A-Za-z0-9_-]+$')) {
    Write-Host "Echec du calcul de l'empreinte (l'API tourne-t-elle en version 0.8 ?)." -ForegroundColor Red
    exit 1
}

$lines = [IO.File]::ReadAllText($envPath) -split "`r?`n" | Where-Object {
    $_ -notmatch '^\s*APP_PASSWORD\s*=' -and $_ -notmatch '^\s*APP_PASSWORD_HASH\s*=' -and $_ -notmatch '^\s*COOKIE_SECURE\s*='
}
$lines = @($lines | Where-Object { $_ -ne "" }) + @("APP_PASSWORD_HASH=$hash", "COOKIE_SECURE=true")
Copy-Item $envPath "$envPath.avant-securisation" -Force
[IO.File]::WriteAllText($envPath, ($lines -join "`n") + "`n")
Write-Host ".env mis a jour (ancienne version : .env.avant-securisation, a supprimer une fois que tout marche)." -ForegroundColor Green

docker compose up -d --force-recreate api
Write-Host "Termine. Reconnecte-toi dans le navigateur avec ce mot de passe." -ForegroundColor Green
