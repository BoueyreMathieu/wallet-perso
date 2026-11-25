/** Connexions bancaires (Enable Banking) : état, synchro, renouvellement, association des comptes, choix de la banque.
 *  Utilisé par la page Comptes ; Paramètres › Connexions ne garde que la configuration technique. */
import { useEffect, useMemo, useState } from "react";
import { Account, api } from "../api";
import { formatDate } from "../format";

export interface BankConfig {
  app_id_set: boolean;
  key_found: boolean;
  configured: boolean;
  redirect_url: string;
  sync_interval_hours: number;
}

export interface RemoteAccount {
  uid: string;
  name: string | null;
  currency: string | null;
  iban_end: string | null;
  account_id: number | null;
}

export interface Conn {
  id: number;
  provider: string;
  label: string;
  status: string;
  consent_expires_at: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  last_error_at: string | null;
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

export const CONN_STATUS: Record<string, { label: string; cls: string }> = {
  actif: { label: "Active", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-200" },
  en_attente: { label: "Autorisation en cours", cls: "bg-amber-100 text-amber-700 dark:bg-amber-900 dark:text-amber-200" },
  expire: { label: "Autorisation expirée", cls: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200" },
  erreur: { label: "Erreur", cls: "bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-200" },
};

export const daysUntil = (iso: string) => Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);

export function ago(iso: string): string {
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (min < 2) return "à l'instant";
  if (min < 60) return `il y a ${min} min`;
  if (min < 48 * 60) return `il y a ${Math.round(min / 60)} h`;
  return `le ${new Date(iso).toLocaleDateString("fr-FR")}`;
}

export type Msg = { text: string; error?: boolean } | null;

/** État et actions des connexions bancaires. `onChanged` : recharger les comptes après un changement. */
export function useBankConnections(onChanged: () => void) {
  const [config, setConfig] = useState<BankConfig | null>(null);
  const [conns, setConns] = useState<Conn[]>([]);
  const [msg, setMsg] = useState<Msg>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const load = () => {
    api.get<BankConfig>("/connections/config").then(setConfig, () => undefined);
    api.get<Conn[]>("/connections").then(setConns, () => undefined);
  };

  useEffect(() => {
    load();
    // Retour de la banque : ?ok=… / ?erreur=…
    const params = new URLSearchParams(window.location.search);
    if (params.get("erreur")) setMsg({ text: `Connexion refusée : ${params.get("erreur")}`, error: true });
    else if (params.get("ok"))
      setMsg({ text: "Banque connectée. Relie ses comptes ci-dessous puis lance une synchro (dans l'heure, pour récupérer le plus d'historique)." });
    if (params.get("ok") || params.get("erreur")) window.history.replaceState(null, "", window.location.pathname);
  }, []);

  // Tant qu'une autorisation est en cours (dans un autre onglet), on rafraîchit régulièrement.
  const pending = conns.some((c) => c.status === "en_attente");
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => {
      api.get<Conn[]>("/connections").then((next) => {
        setConns(next);
        if (!next.some((c) => c.status === "en_attente")) {
          setMsg({ text: "Banque connectée. Vérifie à quels comptes correspondent ses comptes, puis lance une synchro." });
          onChanged();
        }
      });
    }, 4000);
    return () => clearInterval(timer);
  }, [pending]); // eslint-disable-line react-hooks/exhaustive-deps

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
    try {
      await api.post(`/connections/${c.id}/accounts`, { mapping: { [uid]: target } });
    } catch (err) {
      setMsg({ text: (err as Error).message, error: true });
    }
    load();
    onChanged();
  };

  const syncNow = async (c: Conn) => {
    setBusy(c.id);
    try {
      const res = await api.post<SyncResult[]>(`/connections/${c.id}/sync`);
      setMsg({
        text: res.length
          ? res.map((r) => `${r.account_name} : ${r.imported} nouvelle(s), ${r.skipped} déjà connue(s)`).join(" · ")
          : "Aucun compte relié : choisis à quel compte de l'appli correspond chaque compte de la banque.",
      });
    } catch (err) {
      setMsg({ text: (err as Error).message, error: true });
    } finally {
      setBusy(null);
      load();
      onChanged();
    }
  };

  const remove = async (c: Conn) => {
    if (!confirm(`Supprimer la connexion « ${c.label} » ? Les comptes et opérations déjà importés sont conservés.`)) return;
    await api.del(`/connections/${c.id}`);
    load();
    onChanged();
  };

  return { config, conns, msg, setMsg, busy, start, mapAccount, syncNow, remove, reload: load };
}

/** En-tête d'une banque connectée : état, dernière synchro, autorisation, erreurs, actions. */
export function ConnectionHeader({ c, busy, onSync, onRenew, onRemove }: {
  c: Conn; busy: boolean; onSync: () => void; onRenew: () => void; onRemove: () => void;
}) {
  const st = CONN_STATUS[c.status] ?? { label: c.status, cls: "bg-slate-100" };
  const left = c.consent_expires_at ? daysUntil(c.consent_expires_at) : null;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 text-lg font-semibold">
            🏦 {c.label} <span className={`rounded-full px-2 py-0.5 text-xs font-normal ${st.cls}`}>{st.label}</span>
          </p>
          <p className="muted text-xs">
            {c.last_sync_at ? `🔄 Synchro ${ago(c.last_sync_at)}` : "Jamais synchronisée"}
            {c.consent_expires_at && ` · autorisation jusqu'au ${formatDate(c.consent_expires_at)}`}
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          <button className="btn px-3 py-1.5 text-sm" disabled={busy} onClick={onSync}>{busy ? "Synchro…" : "Synchroniser"}</button>
          <button className="btn-ghost px-2 text-sm" onClick={onRenew} title="Renouveler l'autorisation de la banque">🔑 Renouveler</button>
          <button className="btn-ghost px-2 text-sm text-red-600" onClick={onRemove} title="Supprimer la connexion" aria-label="Supprimer la connexion">🗑️</button>
        </div>
      </div>
      {c.last_error && (
        <p className="rounded-xl bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
          ⚠️ Dernière synchro en échec{c.last_error_at ? ` (${new Date(c.last_error_at).toLocaleString("fr-FR")})` : ""} : {c.last_error}
        </p>
      )}
      {left !== null && left <= 14 && (
        <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-200">
          🔑 {left > 0 ? `L'autorisation expire dans ${left} jour(s)` : "L'autorisation a expiré"} : « Renouveler » pour que la synchro continue.
        </p>
      )}
    </div>
  );
}

/** Comptes de la banque pas encore reliés à un compte de l'appli. */
export function UnlinkedBankAccounts({ c, accounts, onMap }: { c: Conn; accounts: Account[]; onMap: (uid: string, value: string) => void }) {
  const unlinked = c.accounts.filter((a) => a.account_id === null);
  if (unlinked.length === 0) return null;
  return (
    <div className="space-y-2 rounded-xl border border-dashed border-slate-300 p-3 text-sm dark:border-white/15">
      <p className="font-medium">Comptes de la banque pas encore reliés</p>
      {unlinked.map((a) => (
        <div key={a.uid} className="flex flex-wrap items-center gap-2">
          <span className="min-w-0 flex-1 truncate">
            {a.name ?? "Compte"}
            {a.iban_end && <span className="muted text-xs"> · …{a.iban_end}</span>}
          </span>
          <select className="input w-auto py-1.5 text-sm" value="" onChange={(e) => onMap(a.uid, e.target.value)} aria-label={`Relier ${a.name ?? "ce compte"}`}>
            <option value="">Ne pas synchroniser</option>
            <option value="new">+ Créer un compte dans l'appli</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>Relier à « {acc.name} »</option>
            ))}
          </select>
        </div>
      ))}
      <p className="muted text-xs">Relier à un compte existant (par exemple importé en CSV au début) garde son historique : la synchro reprend à la suite, sans doublons.</p>
    </div>
  );
}

/** « Connecter une banque » : recherche puis redirection vers la banque. */
export function BankPicker({ onPick, syncHours }: { onPick: (name: string) => void; syncHours: number }) {
  const [banks, setBanks] = useState<Bank[] | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return (banks ?? []).filter((b) => !needle || b.name.toLowerCase().includes(needle)).slice(0, 30);
  }, [banks, search]);
  const loadBanks = async () => {
    try {
      setBanks(await api.get<Bank[]>("/connections/aspsps?country=FR"));
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <section className="card space-y-2 text-sm">
      <h2 className="section-title">➕ Connecter une banque</h2>
      {banks === null ? (
        <button className="btn" onClick={loadBanks}>Choisir ma banque</button>
      ) : (
        <>
          <input className="input" placeholder="Rechercher (ex. Crédit Agricole, PayPal…)" value={search} onChange={(e) => setSearch(e.target.value)} autoFocus />
          <ul className="max-h-80 divide-y divide-slate-100 overflow-auto dark:divide-slate-800">
            {filtered.map((b) => (
              <li key={b.name}>
                <button className="flex w-full items-center gap-3 px-1 py-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800" onClick={() => onPick(b.name)}>
                  {b.logo && <img src={b.logo} alt="" className="h-6 w-6 object-contain" />}
                  <span>{b.name}</span>
                </button>
              </li>
            ))}
            {filtered.length === 0 && <li className="py-2 text-slate-500">Aucune banque trouvée.</li>}
          </ul>
          <p className="muted text-xs">Tu vas être redirigé vers ta banque pour autoriser l'accès en lecture seule, puis ramené ici.</p>
        </>
      )}
      {error && <p className="text-red-600">{error}</p>}
      {syncHours > 0 && <p className="muted text-xs">Synchro automatique toutes les {syncHours} h tant que l'appli tourne, et à l'ouverture de l'appli.</p>}
    </section>
  );
}
