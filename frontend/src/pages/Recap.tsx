import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { api, NATURE_LABELS, Nature, Recap as RecapData } from "../api";
import { CategoryIcon } from "../components/categories";
import { LAYER_COLORS } from "../components/charts";
import { formatCents, isoDate } from "../format";
import { apiBase, authHeader, isNative } from "../native";

const monthFmt = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" });
const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const shift = (key: string, n: number) => {
  const [y, m] = key.split("-").map(Number);
  const d = new Date(y, m - 1 + n, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
const previousMonth = () => shift(isoDate(new Date()).slice(0, 7), -1);

function Delta({ now, before, invert = false }: { now: number; before: number; invert?: boolean }) {
  if (!before) return null;
  const d = now - before;
  if (Math.abs(d) < 100) return <span className="muted text-xs">= mois d'avant</span>;
  const good = invert ? d > 0 : d < 0;
  return (
    <span className={`text-xs font-medium ${good ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>
      {d > 0 ? "▲" : "▼"} {formatCents(Math.abs(d))} vs mois d'avant
    </span>
  );
}

/** Export CSV (Excel) de toutes les opérations, ou du mois affiché. */
async function download(params: Record<string, string>) {
  const res = await fetch(`${apiBase()}/api/export/transactions.csv?${new URLSearchParams(params)}`, { credentials: "same-origin", headers: authHeader() });
  if (!res.ok) throw new Error("Export impossible");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") ?? "")?.[1] ?? "wallet-operations.csv";
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
}

/** Bilan d'un mois : l'essentiel en chiffres, ce qui a changé, et l'export. */
export default function Recap() {
  const location = useLocation();
  const navigate = useNavigate();
  const month = new URLSearchParams(location.search).get("mois") ?? previousMonth();
  const [r, setR] = useState<RecapData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    setR(null);
    api.get<RecapData>(`/recap?month=${month}`).then((x) => { setR(x); setError(null); }, (e) => setError((e as Error).message));
  }, [month]);
  const go = (n: number) => navigate(`/bilan?mois=${shift(month, n)}`);
  const current = isoDate(new Date()).slice(0, 7);
  const exportCsv = async (all: boolean) => {
    if (isNative()) return setMsg("Sur le téléphone, l'export n'est pas encore possible : fais-le depuis l'ordinateur.");
    const [y, m] = month.split("-").map(Number);
    const params: Record<string, string> = all ? {} : { date_from: `${month}-01`, date_to: isoDate(new Date(y, m, 0)) };
    try {
      await download(params);
      setMsg(null);
    } catch (e) {
      setMsg((e as Error).message);
    }
  };

  const title = monthFmt.format(new Date(`${month}-01T12:00:00`));
  const maxLayer = r ? Math.max(1, ...Object.values(r.layers)) : 1;
  const hasExtra = !!r && (r.new_merchants.length > 0 || r.price_increases.length > 0);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">📊 Bilan de {title}</h1>
        <div className="flex items-center gap-1">
          <button className="btn-ghost px-3" onClick={() => go(-1)} aria-label="Mois précédent">‹</button>
          <button className="btn-ghost px-3" onClick={() => go(1)} disabled={month >= current} aria-label="Mois suivant">›</button>
        </div>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      {r && (
        <>
          {!r.complete && <p className="muted text-sm">Mois en cours : bilan provisoire.</p>}
          <div className="grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4 [&>*]:min-w-0">
            <div className="card space-y-0.5 p-3">
              <p className="muted text-xs">Revenus</p>
              <p className="text-lg font-bold tabular-nums text-emerald-600 dark:text-emerald-400">{formatCents(r.income_cents)}</p>
              <Delta now={r.income_cents} before={r.previous.income_cents} invert />
            </div>
            <div className="card space-y-0.5 p-3">
              <p className="muted text-xs">Dépenses</p>
              <p className="text-lg font-bold tabular-nums">{formatCents(-r.spending_cents)}</p>
              <Delta now={r.spending_cents} before={r.previous.spending_cents} />
            </div>
            <div className="card space-y-0.5 p-3">
              <p className="muted text-xs">Reste</p>
              <p className={`text-lg font-bold tabular-nums ${r.net_cents < 0 ? "text-rose-600" : ""}`}>{formatCents(r.net_cents)}</p>
              {r.savings_rate !== null && <p className="muted text-xs">{Math.round(r.savings_rate * 100)} % de tes revenus</p>}
            </div>
            <div className="card space-y-0.5 p-3">
              <p className="muted text-xs">Mis de côté</p>
              <p className="text-lg font-bold tabular-nums">{formatCents(r.saved_cents)}</p>
              <p className="muted text-xs">{r.no_spend_days} jour(s) sans dépense sur {r.days}</p>
            </div>
          </div>

          {r.highlights.length > 0 && (
            <section className="card space-y-1">
              <h2 className="section-title">Ce qui a changé</h2>
              <ul className="list-inside list-disc text-sm">{r.highlights.map((h) => <li key={h}>{h}</li>)}</ul>
            </section>
          )}

          {/* Deux cartes par ligne, de même hauteur ; les longues listes défilent. */}
          <div className="grid gap-4 lg:grid-cols-2 [&>*]:min-w-0">
            <section className="card h-full space-y-3">
              <h2 className="section-title">Par type de dépense</h2>
              {(Object.keys(r.layers) as Nature[]).map((n) => (
                <div key={n} className="space-y-1 text-sm">
                  <div className="flex justify-between"><span>{NATURE_LABELS[n]}</span><span className="tabular-nums">{formatCents(-r.layers[n])}</span></div>
                  <div className="h-2 rounded-full bg-slate-100 dark:bg-white/10">
                    <div className="h-full rounded-full" style={{ width: `${(r.layers[n] / maxLayer) * 100}%`, background: LAYER_COLORS[n] }} />
                  </div>
                </div>
              ))}
            </section>
            <section className="card h-full space-y-2">
              <h2 className="section-title">Plus grosses dépenses</h2>
              <ul className="divide-y divide-slate-100 text-sm dark:divide-white/5">
                {r.biggest.map((b) => (
                  <li key={b.id} className="flex items-center gap-2 py-1.5">
                    <CategoryIcon id={b.category_id} size="sm" />
                    <span className="min-w-0 flex-1 truncate">{b.label}</span>
                    <span className="muted text-xs">{dayFmt.format(new Date(`${b.date}T12:00:00`))}</span>
                    <span className="w-24 text-right font-semibold tabular-nums">{formatCents(b.amount_cents)}</span>
                  </li>
                ))}
              </ul>
            </section>
            <section className={`card flex h-full max-h-[26rem] flex-col gap-2 ${hasExtra ? "" : "lg:col-span-2"}`}>
              <h2 className="section-title">Par catégorie</h2>
              <ul className="-mr-2 min-h-0 divide-y divide-slate-100 overflow-y-auto pr-2 text-sm dark:divide-white/5">
                {r.categories.map((c) => (
                  <li key={c.category_id ?? 0} className="flex items-center gap-2 py-1.5">
                    <CategoryIcon id={c.category_id} size="sm" />
                    <span className="min-w-0 flex-1 truncate">{c.name}</span>
                    {c.usual_cents > 0 && <span className="muted hidden text-xs tabular-nums sm:inline">d'habitude {formatCents(c.usual_cents)}</span>}
                    <span className="w-24 text-right font-semibold tabular-nums">{formatCents(-c.amount_cents)}</span>
                  </li>
                ))}
              </ul>
            </section>
            {(r.new_merchants.length > 0 || r.price_increases.length > 0) && (
              <section className="card h-full max-h-[26rem] space-y-2 overflow-y-auto text-sm">
                {r.new_merchants.length > 0 && (
                  <>
                    <h2 className="section-title">Nouveaux vendeurs</h2>
                    <ul className="space-y-1">
                      {r.new_merchants.map((m) => (
                        <li key={m.name} className="flex justify-between gap-2"><span className="truncate">{m.name}</span><span className="tabular-nums">{formatCents(-m.amount_cents)}</span></li>
                      ))}
                    </ul>
                  </>
                )}
                {r.price_increases.length > 0 && (
                  <>
                    <h2 className="section-title pt-2">Hausses de prix</h2>
                    <ul className="space-y-1">
                      {r.price_increases.map((p) => (
                        <li key={p.label} className="flex justify-between gap-2">
                          <span className="truncate">{p.label}</span>
                          <span className="tabular-nums">{formatCents(p.from_cents)} → {formatCents(p.to_cents)}</span>
                        </li>
                      ))}
                    </ul>
                    <Link to="/prevoir/recurrents" className="text-xs text-accent-600 hover:underline dark:text-accent-300">Voir mes récurrents →</Link>
                  </>
                )}
              </section>
            )}
          </div>

          <section className="card flex flex-wrap items-center gap-2">
            <h2 className="section-title mr-auto">📤 Exporter (Excel / CSV)</h2>
            <button className="btn" onClick={() => exportCsv(false)}>Les opérations de {title}</button>
            <button className="btn-ghost" onClick={() => exportCsv(true)}>Toutes les opérations</button>
            {msg && <p className="muted w-full text-sm">{msg}</p>}
          </section>
        </>
      )}
    </div>
  );
}
