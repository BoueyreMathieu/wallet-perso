import { FormEvent, ReactNode, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AccountType, Patrimoine as Data, WealthAccount, api } from "../api";
import { ChartFrame, LineChart } from "../components/charts";
import { ACCOUNT_TYPE_LABELS, formatCents, parseEuros } from "../format";

const GROUPS: { title: string; icon: string; types: AccountType[] }[] = [
  { title: "Disponible", icon: "💳", types: ["courant", "paypal", "especes", "titres"] },
  { title: "Épargne", icon: "🐷", types: ["epargne"] },
  { title: "Placements", icon: "📈", types: ["investissement"] },
  { title: "Biens", icon: "🚗", types: ["bien"] },
  { title: "Dettes", icon: "🏦", types: ["credit"] },
];
const monthShort = new Intl.DateTimeFormat("fr-FR", { month: "short", year: "2-digit" });
const dateFr = (iso?: string | null) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR") : "");
const euros = (c?: number | string | null) => (c === undefined || c === null || c === "" ? "" : String(Number(c) / 100).replace(".", ","));

/** Patrimoine : ce que tu possèdes et ce que tu dois, son évolution, les biens qui se déprécient, les crédits
 *  (capital restant dû) et les livrets (intérêts, plafond). */
export default function Patrimoine() {
  const [d, setD] = useState<Data | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api.get<Data>("/patrimoine").then((x) => { setD(x); setError(null); }, (e) => setError((e as Error).message));
  useEffect(() => {
    load();
  }, []);
  if (error) return <p className="card text-sm text-red-600">{error}</p>;
  if (!d) return <p className="muted p-4 text-sm">Chargement…</p>;
  const first = d.history.find((h) => h.net_worth_cents !== 0);
  const yearAgo = d.history.length >= 13 ? d.history[d.history.length - 13] : first;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">💎 Patrimoine</h1>
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi label="Patrimoine net" value={formatCents(d.net_worth_cents)} strong
          sub={yearAgo ? `${d.net_worth_cents - yearAgo.net_worth_cents >= 0 ? "+" : ""}${formatCents(d.net_worth_cents - yearAgo.net_worth_cents)} en un an` : undefined} />
        <Kpi label="Ce que tu possèdes" value={formatCents(d.assets_cents)} />
        <Kpi label="Ce que tu dois" value={formatCents(d.debts_cents)} />
        <Kpi label="Intérêts de l'épargne" value={`${formatCents(d.yearly_interest_cents)} / an`} sub="estimation au taux indiqué" />
      </section>
      <ChartFrame title="Évolution (fin de chaque mois)" help="Comptes du quotidien et épargne : solde d'aujourd'hui moins les opérations passées depuis. Biens et crédits réglés ci-dessous : valeur calculée à chaque date (dépréciation, capital restant dû).">
        <LineChart label="Patrimoine net" points={d.history.map((h) => ({ label: monthShort.format(new Date(`${h.month}-01T12:00:00`)), value: h.net_worth_cents }))} />
      </ChartFrame>
      {GROUPS.map((g) => {
        const rows = d.accounts.filter((a) => g.types.includes(a.type));
        if (rows.length === 0) return null;
        const total = rows.filter((a) => a.in_net_worth).reduce((s, a) => s + a.balance_cents, 0);
        return (
          <section key={g.title} className="card space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="section-title">{g.icon} {g.title}</h2>
              <span className="font-semibold tabular-nums">{formatCents(total)}</span>
            </div>
            <ul className="space-y-3">
              {rows.map((a) => <WealthRow key={a.id} a={a} onChanged={load} />)}
            </ul>
          </section>
        );
      })}
      <p className="muted px-1 text-xs">
        Ajouter une voiture, un crédit ou un livret : <Link to="/comptes" className="font-medium text-accent-600 hover:underline dark:text-accent-300">Comptes › Ajouter un compte</Link> (type
        « Bien », « Crédit » ou « Épargne »), puis règle-le ici.
      </p>
    </div>
  );
}

function Kpi({ label, value, sub, strong = false }: { label: string; value: string; sub?: string; strong?: boolean }) {
  return (
    <div className="card">
      <p className="muted text-xs">{label}</p>
      <p className={`${strong ? "text-2xl" : "text-lg"} font-bold tabular-nums`}>{value}</p>
      {sub && <p className="muted text-xs">{sub}</p>}
    </div>
  );
}

function WealthRow({ a, onChanged }: { a: WealthAccount; onChanged: () => void }) {
  const [edit, setEdit] = useState(false);
  const [table, setTable] = useState(false);
  const x = a.details;
  const configurable = a.type === "bien" || a.type === "credit" || a.type === "epargne";
  let info: ReactNode = null;
  if (a.type === "bien" && x.purchase_cents) {
    info = <>Acheté {formatCents(x.purchase_cents)} le {dateFr(x.purchase_date)} · −{x.depreciation_pct} %/an (≈ {formatCents(x.yearly_loss_cents ?? 0)} cette année)</>;
  } else if (a.type === "credit" && x.principal_cents) {
    info = (
      <>
        {formatCents(x.monthly_payment_cents ?? 0)}/mois{x.insurance_cents ? ` + ${formatCents(x.insurance_cents)} d'assurance` : ""} · {x.rate_pct} % · fin le {dateFr(x.end_date)}
        <span className="block">{x.payments_left} échéance(s) restante(s) · {formatCents(x.interest_left_cents ?? 0)} d'intérêts encore à payer</span>
      </>
    );
  } else if (a.type === "epargne" && x.rate_pct !== undefined) {
    info = (
      <>
        {x.rate_pct} % · ≈ {formatCents(x.yearly_interest_cents ?? 0)} d'intérêts sur un an
        {x.ceiling_cents ? (x.at_ceiling ? " · 🐷 au plafond : les versements en plus ne rapportent plus" : ` · encore ${formatCents(x.room_cents ?? 0)} avant le plafond`) : ""}
      </>
    );
  }
  return (
    <li className="space-y-1.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{a.name}</p>
          <p className="muted text-xs">{ACCOUNT_TYPE_LABELS[a.type]}{!a.in_net_worth && " · hors patrimoine"}</p>
        </div>
        <span className={`shrink-0 font-semibold tabular-nums ${a.balance_cents < 0 ? "text-rose-600" : ""}`}>{formatCents(a.balance_cents)}</span>
      </div>
      {a.type === "credit" && x.paid_pct !== undefined && (
        <div className="h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-white/10" title={`${Math.round(x.paid_pct * 100)} % remboursé`}>
          <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.round(x.paid_pct * 100)}%` }} />
        </div>
      )}
      {info && <p className="muted text-xs">{info}</p>}
      {configurable && (
        <div className="flex flex-wrap gap-1">
          <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setEdit(!edit)}>⚙️ {info ? "Modifier les réglages" : a.type === "bien" ? "Calculer sa valeur" : a.type === "credit" ? "Calculer le restant dû" : "Taux et plafond"}</button>
          {x.schedule && <button className="btn-ghost px-2 py-1 text-xs" onClick={() => setTable(!table)}>📋 Tableau d'amortissement</button>}
        </div>
      )}
      {edit && <ParamsForm a={a} onSaved={() => { setEdit(false); onChanged(); }} />}
      {table && x.schedule && (
        <div className="max-h-72 overflow-auto rounded-xl border border-slate-100 dark:border-white/10">
          <table className="w-full text-right text-xs tabular-nums">
            <thead className="muted sticky top-0 bg-panel dark:bg-panel-dark"><tr><th className="p-1.5 text-left">N°</th><th>Date</th><th>Échéance</th><th>Intérêts</th><th>Capital</th><th className="pr-2">Restant dû</th></tr></thead>
            <tbody>
              {x.schedule.map((s) => (
                <tr key={s.n} className={s.date <= new Date().toISOString().slice(0, 10) ? "muted" : ""}>
                  <td className="p-1 text-left">{s.n}</td><td>{dateFr(s.date)}</td><td>{formatCents(s.payment_cents)}</td><td>{formatCents(s.interest_cents)}</td>
                  <td>{formatCents(s.principal_cents)}</td><td className="pr-2">{formatCents(s.remaining_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </li>
  );
}

function ParamsForm({ a, onSaved }: { a: WealthAccount; onSaved: () => void }) {
  const p = a.params;
  const [v, setV] = useState<Record<string, string>>({
    purchase: euros(p.purchase_cents), purchase_date: String(p.purchase_date ?? ""), depreciation: String(p.depreciation_pct ?? (a.type === "bien" ? "15" : "")),
    principal: euros(p.principal_cents), rate: String(p.rate_pct ?? "").replace(".", ","), months: String(p.months ?? ""), first: String(p.first_payment ?? ""),
    insurance: euros(p.insurance_cents), ceiling: euros(p.ceiling_cents),
  });
  const [msg, setMsg] = useState<string | null>(null);
  const set = (k: string) => (e: { target: { value: string } }) => setV({ ...v, [k]: e.target.value });
  const num = (s: string) => (s.trim() ? Number(s.replace(",", ".")) : null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body =
      a.type === "bien" ? { purchase_cents: parseEuros(v.purchase), purchase_date: v.purchase_date || null, depreciation_pct: num(v.depreciation) }
      : a.type === "credit" ? { principal_cents: parseEuros(v.principal), rate_pct: num(v.rate) ?? 0, months: num(v.months), first_payment: v.first || null, insurance_cents: v.insurance.trim() ? parseEuros(v.insurance) : null }
      : { rate_pct: num(v.rate), ceiling_cents: v.ceiling.trim() ? parseEuros(v.ceiling) : null };
    try {
      await api.put(`/accounts/${a.id}/params`, body);
      setMsg(null);
      onSaved();
    } catch (err) {
      setMsg((err as Error).message);
    }
  };
  const field = (label: string, k: string, extra: Record<string, string> = {}) => (
    <label className="space-y-1 text-xs"><span className="muted">{label}</span><input className="input py-1.5 text-sm" value={v[k]} onChange={set(k)} {...extra} /></label>
  );
  return (
    <form className="grid gap-2 rounded-xl bg-slate-50 p-3 sm:grid-cols-2 dark:bg-white/5" onSubmit={submit}>
      {a.type === "bien" && (<>
        {field("Prix d'achat (€)", "purchase", { inputMode: "decimal" })}
        {field("Date d'achat", "purchase_date", { type: "date" })}
        {field("Perte de valeur par an (%) — voiture ≈ 15", "depreciation", { inputMode: "decimal" })}
      </>)}
      {a.type === "credit" && (<>
        {field("Capital emprunté (€)", "principal", { inputMode: "decimal" })}
        {field("Taux annuel (%)", "rate", { inputMode: "decimal" })}
        {field("Durée (mois)", "months", { inputMode: "numeric" })}
        {field("Date de la 1re échéance", "first", { type: "date" })}
        {field("Assurance par mois (€, facultatif)", "insurance", { inputMode: "decimal" })}
      </>)}
      {a.type === "epargne" && (<>
        {field("Taux annuel (%) — Livret A : voir le taux en vigueur", "rate", { inputMode: "decimal" })}
        {field("Plafond (€, facultatif)", "ceiling", { inputMode: "decimal" })}
      </>)}
      <div className="flex items-center gap-2 sm:col-span-2">
        <button className="btn">Enregistrer</button>
        {msg && <span className="text-sm text-red-600">{msg}</span>}
      </div>
    </form>
  );
}
