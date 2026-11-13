# Appli Android (Capacitor) et widgets

L'appli reprend toute l'interface du Wallet dans une vraie appli Android, avec 8 widgets d'écran d'accueil
(voir [Widgets](#widgets)) : **Solde d'un compte**, **Fin du mois**, **Ce mois-ci**, **Budgets**, **À venir**,
**Patrimoine**, **Dernières opérations**, **Ajout rapide**.
Elle parle au serveur du Wallet par Tailscale (`https://wallet.<ton-réseau>.ts.net`) avec un jeton d'appareil :
ni mot de passe ni données bancaires ne sont stockés sur le téléphone, seulement ce jeton (révocable).

## Côté serveur (une fois)

```powershell
docker compose up -d --build
```
(nouvelle table des appareils + autorisation de l'appli : rien à configurer).

## Tester en local avec Android Studio (Windows)

1. Installer **Node.js 22 LTS** (nodejs.org) et **Android Studio Otter (2025.2.1) ou plus récent** — il fournit le JDK.
2. Dans le dossier `frontend` :
   ```powershell
   npm install
   npm run android:prepare
   npx cap open android
   ```
   `android:prepare` compile l'interface, crée le projet `frontend/android` au premier lancement (dossier ignoré
   par git), puis ajoute les widgets et les liens `walletperso://`.
3. Téléphone : Paramètres › À propos › appuyer 7 fois sur « Numéro de build », puis Options pour les
   développeurs › **Débogage USB**. Brancher le téléphone, l'accepter, puis ▶ **Run** dans Android Studio.
4. Sur le téléphone : appli **Tailscale** installée et connectée au même compte.
5. Dans l'appli Wallet : adresse du serveur `https://wallet.<ton-réseau>.ts.net`, mot de passe, nom de l'appareil.
6. Widgets : appui long sur l'écran d'accueil › Widgets › Wallet perso.

Après une modification du code : `npm run android:prepare`, puis ▶ Run.

## APK construit par GitHub Actions

Mise en place (une fois) : le fichier de workflow est fourni dans `docs/workflow-android.yml` ; le placer à son
emplacement GitHub (les outils de Claude ne peuvent pas écrire dans `.github/`) :
```powershell
Move-Item docs\workflow-android.yml .github\workflows\android.yml
```

À chaque push qui touche `frontend/` (ou bouton « Run workflow » dans l'onglet **Actions** du dépôt) :
onglet Actions › exécution « Appli Android » › **Artifacts** › `wallet-perso-apk` (zip contenant `app-debug.apk`).
Sur le téléphone, ouvrir l'APK et autoriser l'installation depuis cette source.

Même signature partout (pour installer une nouvelle version par-dessus l'ancienne sans tout désinstaller) :
dans le dépôt GitHub › Settings › Secrets and variables › Actions › **New repository secret**
`ANDROID_DEBUG_KEYSTORE` = contenu de `%USERPROFILE%\.android\debug.keystore` en base64 :
```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:USERPROFILE\.android\debug.keystore")) | Set-Clipboard
```

## Sécurité

- Paramètres › **Sécurité** : chaque téléphone et chaque navigateur y apparaît, « Déconnecter » révoque son accès.
- Déconnexion depuis l'appli = jeton révoqué côté serveur. Un téléphone inutilisé 90 jours est déconnecté.
- Les données de l'appli (jeton, cache des widgets) sont **exclues des sauvegardes Google** et des transferts vers
  un nouveau téléphone (`allowBackup=false`) : sur un nouveau téléphone, il suffit de se reconnecter.
- Le serveur n'accepte les appels de l'appli que depuis son adresse interne (`https://localhost`, réglable :
  `CORS_ORIGINS` dans `.env`) et seulement avec un jeton valide.
- Les APK « debug » sont faits pour tester : ils autorisent l'inspection de l'appli par USB. Pour l'usage de tous
  les jours, installe un **APK release signé** (ci-dessous).

## APK release signé (usage quotidien)

Une fois, dans `frontend` (PowerShell ; `keytool` est fourni avec Android Studio, dans `jbr\bin`) :

```powershell
keytool -genkeypair -v -keystore wallet-release.jks -alias wallet -keyalg RSA -keysize 4096 -validity 10000
```

Garde le fichier `wallet-release.jks` **et** son mot de passe dans ton gestionnaire de mots de passe : sans eux,
impossible de publier une mise à jour par-dessus l'appli installée. Crée ensuite `frontend/keystore.properties`
(ignoré par git) :

```
storeFile=wallet-release.jks
storePassword=…
keyAlias=wallet
keyPassword=…
```

Puis :

```powershell
npm run android:prepare
cd android; .\gradlew assembleRelease
# APK : android\app\build\outputs\apk\release\app-release.apk
```

La première fois, désinstalle l'APK debug (signature différente) avant d'installer la version release.

## Widgets

Chaque widget s'adapte à sa taille (appui long › redimensionner) : 1 case = le chiffre clé, bandeau = + une ligne
d'explication, 2×2 = + détails, 3×3 et plus = + liste complète ou courbe.

| Widget | Petit | 2×2 | Grand |
|---|---|---|---|
| 🏦 Solde d'un compte (au choix) | solde, entrées / sorties du mois | + à venir, 2 dernières opérations | 5 opérations |
| 🔮 Fin du mois | solde prévu, point bas | + aujourd'hui, point bas, écart | + courbe jour par jour |
| 💸 Ce mois-ci | dépensé, ▲▼ vs mois dernier | + barre fixes / essentiels / plaisirs | + 3 premières catégories |
| 🎯 Budgets | « Tout va bien » / « 2 en alerte » | 3 budgets les plus tendus (barres) | jusqu'à 7 |
| 📅 À venir | prochain prélèvement ou revenu | total à payer sur 7 jours + 3 prochains | jusqu'à 7 |
| 💎 Patrimoine | total, variation du mois | + 3 plus gros comptes | jusqu'à 7 comptes |
| 🧾 Dernières opérations | la dernière | 4 dernières + nombre à catégoriser | 8 |
| ➕ Ajout rapide | bouton 1 case | | |

- **Solde d'un compte** : le compte se choisit à la pose du widget ; Android 12+ : appui long › Reconfigurer
  pour en changer. On peut en poser plusieurs (un par compte).
- Un seul appel au serveur pour tous les widgets (`/api/widgets/summary`) ; « Fin du mois » et « Budgets » utilisent
  le même calcul que l'onglet 🔮 Prévoir (sans scénario).
- Mise à jour automatique toutes les 30 min (minimum imposé par Android), ↻ sur un widget (les met tous à jour),
  et à chaque fois qu'on quitte l'appli.
- Hors connexion (Tailscale coupé, serveur éteint) : dernières valeurs connues + message.
- Clic : ouvre l'appli sur la bonne page (accueil, comptes, opérations, « à catégoriser », nouvelle dépense).
