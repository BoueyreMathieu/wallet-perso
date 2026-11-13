import { useEffect, useMemo, useState } from "react";
import { Account, api } from "../api";
import { formatDate } from "../format";

interface Config {
  app_id_set: boolean;
  key_found: boolean;
  configured: boolean;
  redirect_url: string;
  sync_interval_hours: number;
}

interface RemoteAccount {
  uid: string;
  name: string | null;
  currency: string | null;
  iban_end: string | null;
  account_id: number | null;
}

interface Conn {
  id: number;
  provider: string;
  label: string;
  status: string;
  consent_expires_at: string | null;
  last_sync_at: string | null;
  accounts: RemoteAccount[];
}

interface Bank {
  name: string;
  country: string;
  logo: string | null;
}

interface SyncResult {
  account_name: string;
  imported: number;
  skipped: number;
  categorized: number;
  reconciled: number;
}

const STATUS: Record<string, { label: string; cls: string }> = {
  actif: { label: "Active", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200" },
  en_attente: { label: "Autorisation en cours", cls: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200" },
  expire: { label: "Autorisation expirée", cls: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200" },
  erreur: { label: "Erreur", cls: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200" },
};

const daysUntil = (iso: string) => Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);

export default function Connections() {
  const [config, setConfig] = useState<Config | null>(null);
  const [conns, setConns] = useState<Conn[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [banks, setBanks] = useState<Bank[] | null>(null);
  const [search, setSearch] = useState("");
  const [msg, setMsg] = useState<{ text: string; error?: boolean } | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = () => {
    api.get<Config>("/connections/config").then(setConfig);
    api.get<Conn[]>("/connections").then(setConns);
    api.get<Account[]>("/accounts").then(setAccounts);
  };

  useEffect(() => {
    load();
    const params = new URLSearchParams(window.location.search);
    if (params.get("erreur")) setMsg({ text: `Connexion refusée : ${params.get("erreur")}`, error: true });
    else if (params.get("ok"))
      setMsg({ text: "Banque connectée. Associe ses comptes ci-dessous puis lance une synchro (dans l'heure, pour récupérer le plus d'historique)." });
    if (params.toString()) window.history.replaceState(null, "", "/parametres/connexions");
  }, []);

  // Tant qu'une autorisation est en cours (dans un autre onglet), on rafraîchit régulièrement.
  const pending = conns.some((c) => c.status === "en_attente");
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => {
      api.get<Conn[]>("/connections").then((next) => {
        setConns(next);
        if (!next.some((c) => c.status === "en_attente")) {
          setMsg({ text: "Banque connectée. Vérifie l'association des comptes ci-dessous puis lance une synchro." });
          api.get<Account[]>("/accounts").then(setAccounts);
        }
      });
    }, 4000);
    return () => clearInterval(timer);
  }, [pending]);

  const loadBanks = async () => {
    try {
      setBanks(await api.get<Bank[]>("/connections/aspsps?country=FR"));
    } catch (err) {
      setMsg({ text: (err as Error).message, error: true });
    }
  };

  const start = async (bankName: string, connectionId?: number) => {
    try {
      const { url } = await api.post<{ url: string }>("/connections/start", { aspsp_name: bankName, country: "FR", connection_id: connectionId ?? null });
      // Nouvel onglet : l'appli reste ouverte ici et se met à jour toute seule au retour de la banque.
      const tab = window.open(url, "_blank");
      if (!tab) window.location.href = url; // fenêtres bloquées : on y va dans cet onglet
      else setMsg({ text: "Autorise l'accès dans l'onglet qui vient de s'ouvrir : cette page se mettra à jour toute seule." });
      load();
    } catch (err) {
      setMsg({ text: (err as Error).message, error: true });
    }
  };

  const mapAccount = async (c: Conn, uid: string, value: string) => {
    const target = value === "" ? null : value === "new" ? "new" : Number(value);
    await api.post(`/connections/${c.id}/accounts`, { mapping: { [uid]: target } });
    load();
  };

  const syncNow = async (c: Conn) => {
    setBusy(c.id);
    try {
      const res = await api.post<SyncResult[]>(`/connections/${c.id}/sync`);
      setMsg({
        text: res.length
          ? res.map((r) => `${r.account_name} : ${r.imported} nouvelle(s), ${r.skipped} déjà connue(s)`).join(" · ")
          : "Aucun compte associé : choisis à quel compte de l'appli correspond chaque compte bancaire.",
      });
    } catch (err) {
      setMsg({ text: (err as Error).message, error: true });
    } finally {
      setBusy(null);
      load();
    }
  };

  const remove = async (c: Conn) => {
    if (!confirm(`Supprimer la connexion « ${c.label} » ? Les comptes et opérations déjà importés sont conservés.`)) return;
    await api.del(`/connections/${c.id}`);
    load();
  };

  const filteredBanks = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (banks ?? []).filter((b) => !needle || b.name.toLowerCase().includes(needle)).slice(0, 30);
  }, [banks, search]);

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Connexions bancaires</h2>
      {msg && <p className={`card text-sm ${msg.error ? "text-red-600" : ""}`}>{msg.text}</p>}

      {config && !config.configured && (
        <section className="card space-y-2 text-sm">
          <h2 className="font-medium">Configurer Enable Banking</h2>
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

      {conns.map((c) => {
        const st = STATUS[c.status] ?? { label: c.status, cls: "bg-slate-100" };
        const left = c.consent_expires_at ? daysUntil(c.consent_expires_at) : null;
        return (
          <section key={c.id} className="card space-y-3 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <p className="font-medium">{c.label}</p>
                <p className="text-xs text-slate-500">
                  {c.last_sync_at ? `Dernière synchro : ${new Date(c.last_sync_at).toLocaleString("fr-FR")}` : "Jamais synchronisée"}
                  {c.consent_expires_at && ` · autorisation valable jusqu'au ${formatDate(c.consent_expires_at)}`}
                </p>
              </div>
              <span className={`rounded-full px-2 py-0.5 text-xs ${st.cls}`}>{st.label}</span>
            </div>
            {left !== null && left <= 14 && (
              <p className="text-xs text-amber-600">
                {left > 0 ? `L'autorisation expire dans ${left} jour(s)` : "L'autorisation a expiré"} : renouvelle-la pour que la synchro continue.
              </p>
            )}
            <table className="w-full text-left">
              <thead className="text-xs text-slate-500">
                <tr>
                  <th className="py-1">Compte à la banque</th>
                  <th className="py-1">Compte dans l'appli</th>
                </tr>
              </thead>
              <tbody>
                {c.accounts.map((a) => (
                  <tr key={a.uid} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 pr-2">
                      {a.name}
                      {a.iban_end && <span className="text-xs text-slate-500"> · …{a.iban_end}</span>}
                    </td>
                    <td className="py-2">
                      <select className="input" value={a.account_id ?? ""} onChange={(e) => mapAccount(c, a.uid, e.target.value)}>
                        <option value="">Ne pas synchroniser</option>
                        <option value="new">+ Créer un nouveau compte</option>
                        {accounts.map((acc) => (
                          <option key={acc.id} value={acc.id}>{acc.name}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex flex-wrap gap-2">
              <button className="btn" disabled={busy === c.id} onClick={() => syncNow(c)}>
                {busy === c.id ? "Synchro en cours…" : "Synchroniser maintenant"}
              </button>
              <button className="btn-ghost" onClick={() => start(c.label, c.id)}>Renouveler l'autorisation</button>
              <button className="btn-ghost text-red-600" onClick={() => remove(c)}>Supprimer</button>
            </div>
          </section>
        );
      })}

      {config?.configured && (
        <section className="card space-y-2 text-sm">
          <h2 className="font-medium">Connecter une banque</h2>
          {banks === null ? (
            <button className="btn" onClick={loadBanks}>Choisir ma banque</button>
          ) : (
            <>
              <input className="input" placeholder="Rechercher (ex. Crédit Agricole, PayPal…)" value={search} onChange={(e) => setSearch(e.target.value)} autoFocus />
              <ul className="max-h-80 divide-y divide-slate-100 overflow-auto dark:divide-slate-800">
                {filteredBanks.map((b) => (
                  <li key={b.name}>
                    <button className="flex w-full items-center gap-3 px-1 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800" onClick={() => start(b.name)}>
                      {b.logo && <img src={b.logo} alt="" className="h-6 w-6 object-contain" />}
                      <span>{b.name}</span>
                    </button>
                  </li>
                ))}
                {filteredBanks.length === 0 && <li className="py-2 text-slate-500">Aucune banque trouvée.</li>}
              </ul>
              <p className="text-xs text-slate-500">
                Tu vas être redirigé vers ta banque pour autoriser l'accès en lecture seule, puis ramené ici.
              </p>
            </>
          )}
          {config.sync_interval_hours > 0 && (
            <p className="text-xs text-slate-500">Synchro automatique toutes les {config.sync_interval_hours} h tant que l'appli tourne.</p>
          )}
        </section>
      )}
    </div>
  );
}
