# Cree le fichier .env avec des cles aleatoires.
# Usage (depuis le dossier wallet-perso) :  powershell -ExecutionPolicy Bypass -File scripts\init-env.ps1

$root = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $root ".env"

if (Test-Path $envPath) {
    Write-Host ".env existe deja, rien n'est modifie." -ForegroundColor Yellow
    exit 0
}

function New-RandomBytes([int]$n) {
    $bytes = New-Object byte[] $n
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $rng.GetBytes($bytes)
    $rng.Dispose()
    return ,$bytes
}

function New-Hex([int]$n) {
    $b = New-RandomBytes $n
    return ($b | ForEach-Object { $_.ToString("x2") }) -join ""
}

$secure = Read-Host "Choisis le mot de passe de l'appli" -AsSecureString
$password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
if ([string]::IsNullOrWhiteSpace($password)) {
    Write-Host "Mot de passe vide, abandon." -ForegroundColor Red
    exit 1
}
if ($password -match '[\$"''#\s]') {
    Write-Host 'Evite les caracteres $ " '' # et les espaces dans le mot de passe.' -ForegroundColor Red
    exit 1
}

# Cle Fernet = 32 octets en base64 url-safe
$fernet = [Convert]::ToBase64String((New-RandomBytes 32)).Replace("+", "-").Replace("/", "_")

$lines = @(
    "APP_PASSWORD=$password",
    "SECRET_KEY=$(New-Hex 32)",
    "ENCRYPTION_KEY=$fernet",
    "POSTGRES_PASSWORD=$(New-Hex 24)",
    "COOKIE_SECURE=false"
)
[IO.File]::WriteAllLines($envPath, $lines)

Write-Host ".env cree." -ForegroundColor Green
Write-Host "IMPORTANT : sauvegarde ENCRYPTION_KEY en lieu sur (gestionnaire de mots de passe)." -ForegroundColor Yellow
Write-Host "Sans elle, les connexions bancaires enregistrees ne pourront plus etre dechiffrees."
