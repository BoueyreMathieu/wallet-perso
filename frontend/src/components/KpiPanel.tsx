import { ReactNode, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Account, Dashboard } from "../api";
import { ACCOUNT_TYPE_LABELS, formatCents, formatDate } from "../format";
import { CategoryIcon, useCategories } from "./categories";
import { LineChart } from "./charts";

const shortMonth = new Intl.DateTimeFormat("fr-FR", { month: "short", year: "2-digit" });
const monthLabel = (key: string) => {
  const [y, m] = key.split("-").map(Number);
  return shortMonth.format(new Date(y, m - 1, 1)).replace(".", "");
};

type Tx = Dashboard["transactions"][number];

function TxList({ rows, limit = 40 }: { rows: Tx[]; limit?: number }) {
  return (
    <ul className="divide-y divide-slate-100 dark:divide-white/5">
      {rows.slice(0, limit).map((t) => (
        <li key={t.id} className="flex items-center gap-3 py-2 text-sm">
          <CategoryIcon id={t.category_id} size="sm" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium">{t.label}</p>
            <p className="muted text-xs">{formatDate(t.booked_at)} · {t.account_name}</p>
          </div>
          <span className={`font-semibold tabular-nums ${t.amount_cents > 0 ? "text-emerald-600 dark:text-emerald-400" : ""}`}>{formatCents(t.amount_cents)}</span>
        </li>
      ))}
      {rows.length === 0 && <li className="muted py-2 text-sm">Rien sur cette période.</li>}
      {rows.length > limit && <li className="muted py-2 text-xs">… et {rows.length - limit} autre(s).</li>}
    </ul>
  );
}

/** Détail affiché sous les cartes du haut de l'accueil quand on clique dessus. */
export function KpiPanel({
  kind,
  data,
  focusName,
  accounts,
  opsLink,
  onClose,
}: {
  kind: string;
  data: Dashboard;
  focusName: string | null;
  accounts: Account[];
  opsLink: string;
  onClose: () => void;
}) {
  const { pathOf } = useCategories();
  const [sort, setSort] = useState<"amount" | "date">("amount");
  const [big, setBig] = useState(false);

  const expenses = useMemo(() => {
    const rows = data.transactions.filter((t) => t.amount_cents < 0 && (!big || t.amount_cents <= -5000));
    return sort === "amount" ? [...rows].sort((a, b) => a.amount_cents - b.amount_cents) : rows;
  }, [data, sort, big]);
  const incomes = data.transactions.filter((t) => t.amount_cents > 0).sort((a, b) => b.amount_cents - a.amount_cents);

  const byKey = (rows: Tx[], key: (t: Tx) => string) => {
    const m = new Map<string, { label: string; total: number; count: number; category_id: number | null }>();
    for (const t of rows) {
      const k = key(t);
      const e = m.get(k) ?? { label: k, total: 0, count: 0, category_id: t.category_id };
      e.total += Math.abs(t.amount_cents);
      e.count += 1;
      m.set(k, e);
    }
    return [...m.values()].sort((a, b) => b.total - a.total);
  };

  const title: Record<string, string> = {
    spent: focusName ? `Paiements en ${focusName}` : "Où part l'argent ce mois-ci",
    income: "D'où vient l'argent ce mois-ci",
    networth: "Patrimoine",
    savings: "Épargne mois par mois (versé net vers tes comptes d'épargne et d'investissement)",
    average: `${focusName ?? ""} mois par mois`,
    merchants: `${focusName ?? ""} : par vendeur`,
    biggest: "Plus gros paiements",
  };

  let body: ReactNode;
  if (kind === "spent") {
    body = (
      <>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button className={`chip px-3 py-1 ${sort === "amount" ? "bg-accent-600 text-white" : "bg-slate-100 dark:bg-white/5"}`} onClick={() => setSort("amount")}>Par montant</button>
          <button className={`chip px-3 py-1 ${sort === "date" ? "bg-accent-600 text-white" : "bg-slate-100 dark:bg-white/5"}`} onClick={() => setSort("date")}>Par date</button>
          <button className={`chip px-3 py-1 ${big ? "bg-accent-600 text-white" : "bg-slate-100 dark:bg-white/5"}`} onClick={() => setBig(!big)}>Plus de 50 €</button>
          <span className="muted ml-auto">{expenses.length} dépense(s) · {formatCents(expenses.reduce((s, t) => s + t.amount_cents, 0))}</span>
        </div>
        <TxList rows={expenses} />
      </>
    );
  } else if (kind === "income") {
    const groups = byKey(incomes, (t) => (t.category_id === null ? "À catégoriser" : pathOf(t.category_id)));
    body = (
      <div className="grid gap-4 md:grid-cols-2">
        <ul className="space-y-2">
          {groups.map((g) => (
            <li key={g.label} className="flex items-center gap-3 text-sm">
              <CategoryIcon id={g.category_id} size="sm" />
              <span className="min-w-0 flex-1 truncate">{g.label}</span>
              <span className="muted text-xs">{g.count} op.</span>
              <span className="font-semibold tabular-nums">{formatCents(g.total)}</span>
            </li>
          ))}
          {groups.length === 0 && <li className="muted text-sm">Aucun revenu ce mois-ci.</li>}
          {data.prev_income_cents > 0 && (
            <li className="muted border-t border-slate-100 pt-2 text-xs dark:border-white/5">Mois précédent : {formatCents(data.prev_income_cents)}</li>
          )}
        </ul>
        <TxList rows={incomes} limit={15} />
      </div>
    );
  } else if (kind === "networth") {
    const total = accounts.reduce((s, a) => s + (a.balance_cents ?? 0), 0);
    const points = data.months.filter((m) => m.net_worth_cents !== null).map((m) => ({ label: monthLabel(m.month), value: m.net_worth_cents as number }));
    body = (
      <div className="grid gap-4 md:grid-cols-2">
        <LineChart points={points} label="Patrimoine sur 12 mois" />
        <ul className="space-y-2">
          {[...accounts]
            .sort((a, b) => (b.balance_cents ?? 0) - (a.balance_cents ?? 0))
            .map((a) => (
              <li key={a.id} className="text-sm">
                <div className="flex justify-between gap-2">
                  <span className="truncate">{a.name} <span className="muted text-xs">· {ACCOUNT_TYPE_LABELS[a.type]}</span></span>
                  <span className="font-semibold tabular-nums">{a.balance_cents === null ? "—" : formatCents(a.balance_cents)}</span>
                </div>
                <div className="mt-1 h-1.5 rounded-full bg-slate-100 dark:bg-white/5">
                  <div className="h-1.5 rounded-full bg-accent-500" style={{ width: `${total > 0 ? Math.max(0, ((a.balance_cents ?? 0) / total) * 100) : 0}%` }} />
                </div>
              </li>
            ))}
        </ul>
      </div>
    );
  } else if (kind === "savings" || kind === "average") {
    const rows = [...data.months].reverse();
    body = (
      <div className="space-y-2 overflow-x-auto">
        {kind === "savings" && (
          <p className="muted text-xs">
            Virements de tes comptes courants vers tes livrets / comptes d'investissement (et ceux rangés en « Transferts ›
            Épargne / investissement »), moins ce que tu en retires. Taux = mis de côté ÷ revenus.
          </p>
        )}
        <table className="w-full text-sm tabular-nums">
          <thead className="muted text-xs">
            <tr>
              <th className="py-1 text-left font-medium">Mois</th>
              {kind === "savings" && <th className="py-1 text-right font-medium">Revenus</th>}
              <th className="py-1 text-right font-medium">Dépenses</th>
              {kind === "savings" && <th className="py-1 text-right font-medium">Mis de côté</th>}
              {kind === "savings" && <th className="py-1 text-right font-medium">Taux</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-white/5">
            {rows.map((m) => {
              const saved = m.saved_cents;
              const rate = m.income_cents > 0 ? Math.round((saved / m.income_cents) * 100) : null;
              return (
                <tr key={m.month}>
                  <td className="py-1.5">{monthLabel(m.month)}</td>
                  {kind === "savings" && <td className="py-1.5 text-right">{formatCents(m.income_cents)}</td>}
                  <td className="py-1.5 text-right">{formatCents(m.spent_cents)}</td>
                  {kind === "savings" && <td className={`py-1.5 text-right ${saved < 0 ? "text-rose-600" : "text-emerald-600 dark:text-emerald-400"}`}>{formatCents(saved)}</td>}
                  {kind === "savings" && (
                    <td className="py-1.5 text-right">
                      {rate === null ? "—" : (
                        <span className="inline-flex items-center gap-2">
                          <span className="hidden h-1.5 w-16 rounded-full bg-slate-100 sm:inline-block dark:bg-white/5">
                            <span className="block h-1.5 rounded-full bg-emerald-500" style={{ width: `${Math.min(Math.max(rate, 0), 100)}%` }} />
                          </span>
                          {rate} %
                        </span>
                      )}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  } else if (kind === "merchants") {
    const groups = byKey(data.transactions.filter((t) => t.amount_cents < 0), (t) => t.label);
    body = (
      <ul className="space-y-2">
        {groups.map((g) => (
          <li key={g.label} className="flex items-center gap-3 text-sm">
            <span className="min-w-0 flex-1 truncate">{g.label}</span>
            <span className="muted text-xs">{g.count} paiement(s)</span>
            <span className="font-semibold tabular-nums">{formatCents(g.total)}</span>
          </li>
        ))}
      </ul>
    );
  } else {
    body = <TxList rows={[...data.transactions].filter((t) => t.amount_cents < 0).sort((a, b) => a.amount_cents - b.amount_cents)} limit={5} />;
  }

  return (
    <section className="card space-y-3 ring-2 ring-accent-200 dark:ring-accent-500/30">
      <div className="flex items-center justify-between gap-2">
        <h2 className="section-title">{title[kind] ?? ""}</h2>
        <div className="flex items-center gap-1">
          {(kind === "spent" || kind === "income" || kind === "biggest") && (
            <Link to={opsLink} className="btn-ghost text-xs text-accent-600 dark:text-accent-300">Ouvrir dans Opérations →</Link>
          )}
          <button className="btn-ghost px-2" onClick={onClose} aria-label="Fermer">✕</button>
        </div>
      </div>
      {body}
    </section>
  );
}
