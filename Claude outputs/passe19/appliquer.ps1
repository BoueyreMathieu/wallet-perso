# Wallet perso - 19e passe : copie les fichiers dans le projet, seulement si personne n'y a touché entre-temps.
# Lancer depuis le dossier du projet :
#   powershell -ExecutionPolicy Bypass -File <dossier dézippé>\appliquer.ps1
$ErrorActionPreference = "Stop"
$src = Join-Path $PSScriptRoot "fichiers"
if (-not (Test-Path "backend") -or -not (Test-Path "frontend")) { Write-Host "Lance ce script depuis le dossier du projet wallet-perso." -ForegroundColor Red; exit 1 }

if (Test-Path ".dev-lock") {
    $lock = Get-Content ".dev-lock" -Raw
    if ($lock -match "etat: en cours" -and $lock -notmatch "conversation principale") {
        Write-Host "L'autre conversation est en train de livrer (.dev-lock). Réessaie dans quelques minutes." -ForegroundColor Yellow
        Write-Host $lock; exit 1
    }
}

$rows = Get-Content (Join-Path $PSScriptRoot "fichiers.txt") | Where-Object { $_ } | ForEach-Object { $p = $_ -split ";"; [pscustomobject]@{ Path = $p[0]; Old = $p[1]; New = $p[2] } }
$conflicts = @()
foreach ($r in $rows) {
    if ($r.Old -eq "NOUVEAU") {
        if (Test-Path $r.Path) {
            if ((Get-FileHash $r.Path -Algorithm MD5).Hash.ToLower() -ne $r.New) { $conflicts += "$($r.Path) (existe déjà)" }
        }
    } elseif (-not (Test-Path $r.Path)) {
        $conflicts += "$($r.Path) (introuvable)"
    } else {
        $h = (Get-FileHash $r.Path -Algorithm MD5).Hash.ToLower()
        if ($h -ne $r.Old -and $h -ne $r.New) { $conflicts += "$($r.Path) (modifié depuis la dernière livraison)" }
    }
}
if ($conflicts.Count -gt 0) {
    Write-Host "Rien n'a été copié : ces fichiers ont changé depuis ma dernière livraison (sans doute l'autre conversation) :" -ForegroundColor Red
    $conflicts | ForEach-Object { Write-Host "  - $_" }
    Write-Host "Dis-le moi dans la conversation : je fusionnerai les changements." -ForegroundColor Yellow
    exit 1
}

Set-Content ".dev-lock" "etat: en cours`npar: conversation principale (zip 19e passe)`ndepuis: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mmZ'))`nfichiers: 19e passe"
foreach ($r in $rows) {
    $dest = $r.Path
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item (Join-Path $src $r.Path) $dest -Force
    if ((Get-FileHash $dest -Algorithm MD5).Hash.ToLower() -ne $r.New) { Write-Host "Copie incorrecte : $dest" -ForegroundColor Red; exit 1 }
}
Set-Content ".dev-lock" "etat: libre`npar: conversation principale`ndepuis: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mmZ'))`nfichiers: -"
Write-Host "OK : $($rows.Count) fichiers copiés et vérifiés." -ForegroundColor Green
Write-Host "Ensuite : docker compose up -d --build   (migration 0013 appliquée au démarrage)"
