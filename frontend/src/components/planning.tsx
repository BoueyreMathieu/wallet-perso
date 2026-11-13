import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, BudgetItem, BudgetsOverview, Forecast } from "../api";
import { formatCents } from "../format";
import { CategoryIcon, useCategories } from "./categories";

export const LEVELS: Record<BudgetItem["level"], { icon: string; label: string; bar: string; text: string }> = {
  ok: { icon: "✅", label: "Dans les clous", bar: "bg-emerald-500", text: "text-emerald-700 dark:text-emerald-300" },
  alerte: { icon: "⚠️", label: "Attention", bar: "bg-amber-500", text: "text-amber-700 dark:text-amber-300" },
  depasse: { icon: "⛔", label: "Dépassé", bar: "bg-rose-500", text: "text-rose-700 dark:text-rose-300" },
};

const dayFmt = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
export const shortDate = (iso: string) => dayFmt.format(new Date(`${iso}T12:00:00`));

/** Barre de budget : dépensé (couleur selon l'état, + icône et texte), repère « où on devrait en être ». */
export function BudgetBar({ item, showPace = true }: { item: BudgetItem; showPace?: boolean }) {
  const lv = LEVELS[item.level];
  const pct = Math.min(100, (item.spent_cents / Math.max(item.budget_cents, 1)) * 100);
  const pace = Math.min(100, (item.pace_cents / Math.max(item.budget_cents, 1)) * 100);
  return (
    <div className="relative h-2.5 rounded-full bg-slate-100 dark:bg-white/10" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={lv.label}>
      <div className={`h-full rounded-full ${lv.bar}`} style={{ width: `${Math.max(pct, item.spent_cents > 0 ? 2 : 0)}%` }} />
      {showPace && pace < 100 && (
        <span className="absolute -top-1 h-[18px] w-0.5 rounded bg-slate-500/70 dark:bg-white/60" style={{ left: `${pace}%` }} title="Où tu devrais en être à cette date" />
      )}
    </div>
  );
}

/** Accueil : « Fin du mois » (solde prévu, point bas, prochaines échéances). */
export function ForecastCard({ className = "" }: { className?: string }) {
  const [f, setF] = useState<Forecast | null>(null);
  useEffect(() => {
    api.get<Forecast>("/forecast").then(setF, () => setF(null));
  }, []);
  if (!f) return null;
  const next = f.events.filter((e) => e.date >= f.today).slice(0, 4);
  const low = f.lowest && f.lowest.balance_cents < 0 ? f.lowest : null;
  return (
    <section className={`card space-y-3 ${className}`}>
      <div className="flex items-center justify-between">
        <h2 className="section-title">🔮 Fin du mois</h2>
        <Link to="/prevoir/tresorerie" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-300">Détail →</Link>
      </div>
      <div>
        <p className="muted text-xs">Solde prévu le {shortDate(f.horizon)} ({f.accounts.join(", ") || "aucun compte courant"})</p>
        <p className={`text-2xl font-bold tabular-nums ${f.end_balance_cents < 0 ? "text-rose-600" : ""}`}>{formatCents(f.end_balance_cents)}</p>
        <p className="muted text-xs">
          Aujourd'hui {formatCents(f.start_balance_cents)} · revenus {formatCents(f.totals.income_cents)} · charges fixes {formatCents(-f.totals.fixe_cents)} ·
          essentiels et plaisirs ≈ {formatCents(-(f.totals.essentiel_cents + f.totals.plaisir_cents))}
        </p>
      </div>
      {low && (
        <p className="rounded-xl bg-rose-50 px-3 py-2 text-sm font-medium text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
          ⚠️ Découvert possible le {shortDate(low.date)} ({formatCents(low.balance_cents)})
        </p>
      )}
      <ul className="divide-y divide-slate-100 text-sm dark:divide-white/5">
        {next.map((e, i) => (
          <li key={i} className="flex items-center justify-between gap-2 py-1.5">
            <span className="min-w-0 truncate">
              <span className="muted tabular-nums">{e.late ? "en retard" : shortDate(e.date)}</span> · {e.label}
            </span>
            <span className={`shrink-0 font-semibold tabular-nums ${e.amount_cents > 0 ? "text-emerald-600 dark:text-emerald-400" : ""}`}>{formatCents(e.amount_cents)}</span>
          </li>
        ))}
        {next.length === 0 && <li className="muted py-1.5">Aucune échéance connue d'ici là.</li>}
      </ul>
    </section>
  );
}

/** Accueil : budgets du mois (les plus tendus d'abord). */
export function BudgetsCard({ className = "" }: { className?: string }) {
  const { pathOf } = useCategories();
  const [b, setB] = useState<BudgetsOverview | null>(null);
  useEffect(() => {
    api.get<BudgetsOverview>("/budgets").then(setB, () => setB(null));
  }, []);
  if (!b) return null;
  return (
    <section className={`card space-y-3 ${className}`}>
      <div className="flex items-center justify-between">
        <h2 className="section-title">🎯 Budgets du mois</h2>
        <Link to="/prevoir/budgets" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-300">
          {b.items.length ? "Tous →" : "Définir →"}
        </Link>
      </div>
      {b.items.length === 0 ? (
        <p className="muted text-sm">
          Aucun budget pour l'instant.{" "}
          {b.suggestions.length > 0 && `D'après tes 3 derniers mois, on peut t'en proposer ${b.suggestions.length}.`}
        </p>
      ) : (
        <>
          <p className="muted text-xs">
            {formatCents(b.total_spent_cents)} dépensés sur {formatCents(b.total_budget_cents)} · fin de mois ≈ {formatCents(b.total_projected_cents)}
          </p>
          <ul className="space-y-3">
            {b.items.slice(0, 5).map((it) => (
              <li key={it.category_id} className="space-y-1">
                <div className="flex items-center justify-between gap-2 text-sm">
                  <span className="flex min-w-0 items-center gap-2">
                    <CategoryIcon id={it.category_id} size="sm" />
                    <span className="truncate">{pathOf(it.category_id)}</span>
                  </span>
                  <span className="shrink-0 tabular-nums">
                    <span className={`font-semibold ${LEVELS[it.level].text}`}>{formatCents(it.spent_cents)}</span>
                    <span className="muted"> / {formatCents(it.budget_cents)}</span>
                    {it.level !== "ok" && <span className="ml-1" title={LEVELS[it.level].label}>{LEVELS[it.level].icon}</span>}
                  </span>
                </div>
                <BudgetBar item={it} />
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
