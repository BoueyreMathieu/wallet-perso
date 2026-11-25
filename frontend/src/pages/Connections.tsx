import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { BankConfig } from "../components/bankConnections";

/** Paramètres › Connexions : configuration technique d'Enable Banking. Les banques connectées, la synchro et
 *  l'association des comptes sont dans la page Comptes. */
export default function Connections() {
  const [config, setConfig] = useState<BankConfig | null>(null);
  useEffect(() => {
    api.get<BankConfig>("/connections/config").then(setConfig, () => undefined);
  }, []);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Synchro bancaire (Enable Banking)</h2>
      <p className="card text-sm">
        🏦 Les banques connectées, leur synchro, le renouvellement de l'autorisation et le lien avec tes comptes sont dans{" "}
        <Link to="/comptes" className="font-medium text-accent-600 hover:underline dark:text-accent-300">Comptes</Link>.
      </p>
      {config && config.configured && (
        <p className="card text-sm text-emerald-700 dark:text-emerald-400">
          ✓ Enable Banking est configuré{config.sync_interval_hours > 0 ? ` · synchro automatique toutes les ${config.sync_interval_hours} h` : ""}.
        </p>
      )}
      {config && !config.configured && (
        <section className="card space-y-2 text-sm">
          <h3 className="font-medium">Configurer Enable Banking</h3>
          <ol className="list-decimal space-y-1 pl-5">
            <li>
              Crée une application dans le Control Panel Enable Banking, avec l'adresse de retour{" "}
              <code className="rounded bg-slate-100 px-1 dark:bg-slate-800">{config.redirect_url}</code>.
            </li>
            <li className={config.key_found ? "text-emerald-600" : ""}>
              Range le fichier de clé <code>.pem</code> téléchargé dans le dossier <code>secrets</code> du projet
              {config.key_found ? " ✓" : ""}.
            </li>
            <li className={config.app_id_set ? "text-emerald-600" : ""}>
              Ajoute <code>ENABLE_BANKING_APP_ID=…</code> (l'identifiant de l'application) dans le fichier <code>.env</code>
              {config.app_id_set ? " ✓" : ""}.
            </li>
            <li>
              Relance l'appli : <code>docker compose up -d</code>.
            </li>
          </ol>
        </section>
      )}
    </div>
  );
}
