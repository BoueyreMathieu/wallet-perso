// Prépare (ou met à jour) le projet Android de l'appli :
//   1. crée frontend/android avec Capacitor s'il n'existe pas ;
//   2. y copie l'interface compilée (dist/) ;
//   3. ajoute les widgets et MainActivity (frontend/android-overlay), retire les anciens fichiers de widgets,
//      et déclare widgets + écran de choix du compte + liens walletperso:// dans le manifeste.
// Usage : npm run android:prepare   (puis ouvrir frontend/android dans Android Studio, ou ./gradlew assembleDebug)
import { execSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const run = (cmd) => execSync(cmd, { stdio: "inherit", cwd: root, shell: true });
const android = path.join(root, "android");

if (!fs.existsSync(android)) run("npx cap add android");
run("npx cap sync android");

function copyDir(src, dst) {
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dst, entry.name);
    if (entry.isDirectory()) {
      fs.mkdirSync(d, { recursive: true });
      copyDir(s, d);
    } else {
      fs.copyFileSync(s, d);
    }
  }
}
copyDir(path.join(root, "android-overlay"), android);

// Anciens fichiers des widgets (avant la refonte « taille évolutive ») : retirés du projet Android et de l'overlay.
const OBSOLETE = [
  "app/src/main/res/layout/widget_spent.xml",
  "app/src/main/res/layout/widget_balances.xml",
  "app/src/main/res/layout/widget_recent.xml",
  "app/src/main/res/drawable/wallet_widget_chip.xml",
];
for (const rel of OBSOLETE) {
  for (const base of [android, path.join(root, "android-overlay")]) {
    const f = path.join(base, rel);
    if (fs.existsSync(f)) fs.rmSync(f);
  }
}

const manifestPath = path.join(android, "app", "src", "main", "AndroidManifest.xml");
let xml = fs.readFileSync(manifestPath, "utf8");
// Bloc des widgets : toujours régénéré (on retire l'ancien, quelle que soit sa version).
const MARK = "<!-- wallet-perso:widgets -->";
const END = "<!-- /wallet-perso:widgets -->";
const manifestBefore = xml;
xml = xml
  .replace(/\s*<receiver android:name="\.widget\.[\s\S]*?<\/receiver>/g, "")
  .replace(/\s*<activity android:name="\.widget\.[\s\S]*?<\/activity>/g, "")
  .replace(/\s*<!-- \/?wallet-perso:widgets -->/g, "")
  .replace(/\s*<\/application>/, "\n    </application>");
const WIDGETS = [
  ["AccountWidget", "widget_account_info", "widget_account_name"],
  ["MonthEndWidget", "widget_monthend_info", "widget_monthend_name"],
  ["SpentWidget", "widget_spent_info", "widget_spent_name"],
  ["BudgetsWidget", "widget_budgets_info", "widget_budgets_name"],
  ["UpcomingWidget", "widget_upcoming_info", "widget_upcoming_name"],
  ["BalancesWidget", "widget_balances_info", "widget_balances_name"],
  ["RecentWidget", "widget_recent_info", "widget_recent_name"],
  ["QuickAddWidget", "widget_quickadd_info", "widget_quickadd_name"],
];
const receiver = ([cls, info, label]) => `
        <receiver android:name=".widget.${cls}" android:exported="false" android:label="@string/${label}">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_UPDATE" />
            </intent-filter>
            <meta-data android:name="android.appwidget.provider" android:resource="@xml/${info}" />
        </receiver>`;
// Écran de choix du compte (widget « Solde d'un compte ») : lancé par l'écran d'accueil, donc exporté.
const configure = `
        <activity android:name=".widget.AccountWidgetConfigure" android:exported="true"
            android:excludeFromRecents="true" android:taskAffinity=""
            android:theme="@style/Theme.AppCompat.DayNight.Dialog">
            <intent-filter>
                <action android:name="android.appwidget.action.APPWIDGET_CONFIGURE" />
            </intent-filter>
        </activity>`;
xml = xml.replace("</application>", `
        ${MARK}${WIDGETS.map(receiver).join("")}${configure}
        ${END}
    </application>`);
// Liens walletperso://… (ouverts par les widgets) vers l'activité principale.
if (!xml.includes('android:scheme="walletperso"')) {
  const deepLink = `</intent-filter>

            <intent-filter>
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="walletperso" />
            </intent-filter>`;
  xml = xml.replace("</intent-filter>", deepLink);
}
if (xml !== manifestBefore) {
  fs.writeFileSync(manifestPath, xml);
  console.log(`Manifeste : ${WIDGETS.length} widgets, écran de choix du compte et liens walletperso:// à jour.`);
}
// --- Sécurité : pas de sauvegarde Google / transfert des données de l'appli (le jeton d'accès y est stocké) ---
let secured = fs.readFileSync(manifestPath, "utf8");
const before = secured;
secured = secured.replace('android:allowBackup="true"', 'android:allowBackup="false"');
if (!secured.includes("android:allowBackup=")) secured = secured.replace("<application", '<application\n        android:allowBackup="false"');
if (!secured.includes("android:fullBackupContent=")) {
  secured = secured.replace('android:allowBackup="false"', 'android:allowBackup="false"\n        android:fullBackupContent="false"');
}
if (!secured.includes("android:dataExtractionRules=")) {
  secured = secured.replace('android:allowBackup="false"', 'android:allowBackup="false"\n        android:dataExtractionRules="@xml/wallet_data_extraction"');
}
if (secured !== before) {
  fs.writeFileSync(manifestPath, secured);
  console.log("Manifeste : sauvegarde Android désactivée pour les données de l'appli.");
}

// --- Signature « release » : si frontend/keystore.properties existe (jamais versionné), voir docs/android.md ---
const gradlePath = path.join(android, "app", "build.gradle");
const SIGN_MARK = "// wallet-perso:signing";
if (fs.existsSync(gradlePath)) {
  let gradle = fs.readFileSync(gradlePath, "utf8");
  if (!gradle.includes(SIGN_MARK)) {
    const header = `${SIGN_MARK}
def walletKeyFile = rootProject.file("../keystore.properties")
def walletKey = new Properties()
if (walletKeyFile.exists()) { walletKeyFile.withInputStream { walletKey.load(it) } }
`;
    const signing = `
    signingConfigs {
        walletRelease {
            if (walletKeyFile.exists()) {
                storeFile rootProject.file("../" + walletKey["storeFile"])
                storePassword walletKey["storePassword"]
                keyAlias walletKey["keyAlias"]
                keyPassword walletKey["keyPassword"]
            }
        }
    }`;
    const releaseRe = /(buildTypes\s*\{\s*release\s*\{)/;
    if (/^android\s*\{/m.test(gradle) && releaseRe.test(gradle)) {
      // Juste avant le bloc android { } (après un éventuel bloc plugins { }, qui doit rester en tête du fichier).
      gradle = gradle.replace(/^android\s*\{/m, (m) => `${header}${m}${signing}`);
      gradle = gradle.replace(releaseRe, (m) => `${m}\n            if (walletKeyFile.exists()) signingConfig signingConfigs.walletRelease`);
      fs.writeFileSync(gradlePath, gradle);
      console.log("build.gradle : signature release branchée sur keystore.properties.");
    } else {
      console.warn("build.gradle inattendu : signature release non configurée (voir docs/android.md).");
    }
  }
}

console.log("Projet Android prêt : ouvre frontend/android dans Android Studio (ou npx cap open android).");
