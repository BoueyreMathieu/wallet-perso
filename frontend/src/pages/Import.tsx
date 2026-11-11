import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Account, ApiError, ImportResult, api, upload } from "../api";
import { formatCents, formatDate } from "../format";

const SOURCES = [
  { id: "credit-agricole", label: "Crédit Agricole (CSV)", help: "Espace en ligne → compte → « Télécharger mes opérations » au format CSV." },
  { id: "paypal", label: "PayPal (CSV)", help: "paypal.com → Activité → Télécharger → format CSV. Les achats payés via ta banque sont rapprochés automatiquement." },
];

export default function Import() {
  const [source, setSource] = useState(SOURCES[0].id);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState<string>("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needAccount, setNeedAccount] = useState(false);
  const [results, setResults] = useState<ImportResult[]>([]);

  useEffect(() => {
    api.get<Account[]>("/accounts").then(setAccounts);
  }, []);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const form = new FormData();
    form.append("file", file);
    if (accountId) form.append("account_id", accountId);
    try {
      const res = await upload<ImportResult>(`/imports/${source}`, form);
      setResults((r) => [res, ...r]);
      setNeedAccount(false);
      setFile(null);
      setAccountId("");
      (e.target as HTMLFormElement).reset();
    } catch (err) {
      setError((err as Error).message);
      setNeedAccount(err instanceof ApiError && err.status === 409);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Importer des opérations</h1>

      <form onSubmit={submit} className="card space-y-3">
        <label className="block space-y-1 text-sm">
          <span>Source</span>
          <select className="input" value={source} onChange={(e) => setSource(e.target.value)}>
            {SOURCES.map((s) => (
              <option key={s.id} value={s.id}>{s.label}</option>
            ))}
          </select>
        </label>
        <p className="text-sm text-slate-500">
          {SOURCES.find((s) => s.id === source)?.help} Tu peux réimporter une période déjà importée : les doublons sont
          ignorés.
        </p>
        <input
          type="file"
          accept=".csv,text/csv"
          className="block w-full text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-slate-200 file:px-3 file:py-2 dark:file:bg-slate-700"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <label className={`block space-y-1 text-sm ${needAccount ? "rounded-lg ring-2 ring-amber-500 p-2" : ""}`}>
          <span>Compte</span>
          <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
            <option value="">Détecter automatiquement</option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
                {a.institution ? ` · ${a.institution}` : ""}
              </option>
            ))}
          </select>
        </label>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="btn" disabled={!file || busy}>
          {busy ? "Import en cours…" : "Importer"}
        </button>
      </form>

      {results.map((r, i) => (
        <div key={i} className="card space-y-1 text-sm">
          <p className="font-medium">
            {r.account_name} : {r.imported} opération{r.imported > 1 ? "s" : ""} importée{r.imported > 1 ? "s" : ""}
          </p>
          {r.period_start && r.period_end && (
            <p className="text-slate-500">
              Du {formatDate(r.period_start)} au {formatDate(r.period_end)} · {r.skipped} déjà présente
              {r.skipped > 1 ? "s" : ""}
            </p>
          )}
          {r.imported > 0 && (
            <p className="text-slate-500">
              {r.categorized} catégorisée{r.categorized > 1 ? "s" : ""} automatiquement (
              {Math.round((100 * r.categorized) / r.imported)} %)
            </p>
          )}
          {r.updated > 0 && <p className="text-slate-500">{r.updated} mise{r.updated > 1 ? "s" : ""} à jour (statut)</p>}
          {r.reconciled > 0 && (
            <p className="text-slate-500">
              {r.reconciled} paiement{r.reconciled > 1 ? "s" : ""} PayPal rapproché{r.reconciled > 1 ? "s" : ""} avec la banque
            </p>
          )}
          {r.merged_manual > 0 && (
            <p className="text-slate-500">
              {r.merged_manual} saisie{r.merged_manual > 1 ? "s" : ""} manuelle{r.merged_manual > 1 ? "s" : ""} retrouvée{r.merged_manual > 1 ? "s" : ""} et fusionnée{r.merged_manual > 1 ? "s" : ""}
            </p>
          )}
          {r.balance_cents !== null && r.balance_date && (
            <p className="text-slate-500">
              Solde mis à jour : {formatCents(r.balance_cents)} au {formatDate(r.balance_date)}
            </p>
          )}
        </div>
      ))}

      {results.length > 0 && (
        <Link to="/operations" className="btn inline-block">
          Voir et catégoriser les opérations
        </Link>
      )}
    </div>
  );
}
