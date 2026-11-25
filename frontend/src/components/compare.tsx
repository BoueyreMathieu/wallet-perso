/** Bilan › Comparer à l'an dernier : année civile à date, ou 12 derniers mois, contre la même période un an plus tôt. */
import { useEffect, useMemo, useState } from "react";
import { CompareResult, api } from "../api";
import { formatCents } from "../format";
import { CategoryIcon, useCategories } from "./categories";
import { ACCENT, ChartFrame, CompareBars, Legend, PREV_COLOR } from "./charts";

const monthShort = new Intl.DateTimeFormat("fr-FR", { month: "short" });
const dateFr = (iso: string) => new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" });

function Diff({ cur, prev, invert = false }: { cur: number; prev: number; invert?: boolean }) {
  if (!prev) return <span className="muted text-xs">nouveau</span>;
  const d = cur - prev;
  const pct = Math.round((d / prev) * 100);
  if (Math.abs(pct) < 1) return <span className="muted text-xs">=</span>;
  const good = invert ? d > 0 : d < 0;
  return <span className={`text-xs font-medium ${good ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400"}`}>{d > 0 ? "▲" : "▼"} {Math.abs(pct)} %</span>;
}

export function YearCompare() {
  const { byId } = useCategories();
  const [mode, setMode] = useState<"ytd" | "rolling">("ytd");
  const [r, setR] = useState<CompareResult | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setR(null);
    api.get<CompareResult>(`/compare?mode=${mode}`).then((x) => { setR(x); setError(null); }, (e) => setError((e as Error).message));
  }, [mode]);
  const tops = useMemo(() => (r?.categories ?? []).filter((c) => c.parent_id === null), [r]);
  const kids = (id: number | null) => (r?.categories ?? []).filter((c) => c.parent_id === id && id !== null);
  const curLabel = mode === "ytd" ? "Cette année" : "12 derniers mois";
  const prevLabel = mode === "ytd" ? "L'an dernier" : "12 mois d'avant";
  const name = (id: number | null) => (id === null ? "À catégoriser" : byId.get(id)?.name ?? "?");

  return (
    <div className="space-y-4">
      <section className="card flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-2xl bg-slate-100 p-1 text-sm dark:bg-white/5">
          {(["ytd", "rolling"] as const).map((m) => (
            <button key={m} className={`rounded-xl px-3 py-1.5 ${mode === m ? "bg-panel font-semibold shadow-soft dark:bg-panel-dark" : "muted"}`} onClick={() => setMode(m)}>
              {m === "ytd" ? "Depuis le 1er janvier" : "12 derniers mois"}
            </button>
          ))}
        </div>
        {r && <p className="muted text-xs">{dateFr(r.current.start)} → {dateFr(r.current.end)}, contre {dateFr(r.previous.start)} → {dateFr(r.previous.end)}</p>}
      </section>
      {error && <p className="card text-sm text-red-600">{error}</p>}
      {!r && !error && <p className="muted p-2 text-sm">Chargement…</p>}
      {r && (
        <>
          <section className="grid gap-3 sm:grid-cols-2">
            <div className="card">
              <p className="muted text-xs">Dépenses</p>
              <p className="text-2xl font-bold tabular-nums">{formatCents(r.spent_cents)}</p>
              <p className="text-sm"><span className="muted">{prevLabel} : {formatCents(r.prev_spent_cents)}</span> <Diff cur={r.spent_cents} prev={r.prev_spent_cents} /></p>
            </div>
            <div className="card">
              <p className="muted text-xs">Revenus</p>
              <p className="text-2xl font-bold tabular-nums text-emerald-700 dark:text-emerald-400">{formatCents(r.income_cents)}</p>
              <p className="text-sm"><span className="muted">{prevLabel} : {formatCents(r.prev_income_cents)}</span> <Diff cur={r.income_cents} prev={r.prev_income_cents} invert /></p>
            </div>
          </section>
          <ChartFrame title="Dépenses mois par mois" controls={<Legend items={[{ label: curLabel, color: ACCENT }, { label: prevLabel, color: PREV_COLOR }]} />}
            help="Pour chaque mois : à droite la période actuelle, à gauche le même mois un an plus tôt. Le mois en cours n'est pas terminé.">
            <CompareBars curLabel={curLabel} prevLabel={prevLabel}
              data={r.months.map((m) => ({ key: m.month, label: monthShort.format(new Date(`${m.month}-01T12:00:00`)), cur: m.cur_cents, prev: m.prev_cents }))} />
          </ChartFrame>
          <section className="card space-y-1">
            <h2 className="section-title">Par catégorie</h2>
            <p className="muted text-xs">Touche une catégorie pour voir ses sous-catégories.</p>
            <ul className="divide-y divide-slate-100 dark:divide-white/5">
              {tops.map((c) => (
                <li key={c.category_id ?? "none"}>
                  <button className="flex w-full items-center gap-3 py-2 text-left" onClick={() => setOpen(open === c.category_id ? null : c.category_id)}>
                    {c.category_id !== null ? <CategoryIcon id={c.category_id} size="sm" /> : <span aria-hidden>❔</span>}
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{name(c.category_id)}</span>
                    <span className="muted hidden w-24 text-right text-xs tabular-nums sm:block">{formatCents(c.prev_cents)}</span>
                    <span className="w-24 text-right text-sm font-semibold tabular-nums">{formatCents(c.cur_cents)}</span>
                    <span className="w-14 text-right"><Diff cur={c.cur_cents} prev={c.prev_cents} /></span>
                  </button>
                  {open === c.category_id && kids(c.category_id).length > 0 && (
                    <ul className="mb-2 ml-8 space-y-1">
                      {kids(c.category_id).map((k) => (
                        <li key={k.category_id} className="flex items-center gap-3 text-xs">
                          <span className="min-w-0 flex-1 truncate">{name(k.category_id)}</span>
                          <span className="muted hidden w-24 text-right tabular-nums sm:block">{formatCents(k.prev_cents)}</span>
                          <span className="w-24 text-right font-medium tabular-nums">{formatCents(k.cur_cents)}</span>
                          <span className="w-14 text-right"><Diff cur={k.cur_cents} prev={k.prev_cents} /></span>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
            <p className="muted flex justify-end gap-3 pt-1 text-[11px]"><span className="hidden sm:inline">{prevLabel}</span><span>{curLabel}</span></p>
          </section>
        </>
      )}
    </div>
  );
}
