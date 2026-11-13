import { ReactNode, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Account, Dashboard, NetWorth, Pending, Transaction, api } from "../api";
import { ChartFrame, CumulativeChart, Donut, Legend, Slice, Sparkline, ACCENT, MUTED_LINE } from "../components/charts";
import { CategoryIcon, UNCATEGORIZED_COLOR, useCategories } from "../components/categories";
import { KpiPanel } from "../components/KpiPanel";
import { MonthsExplorer } from "../components/MonthsExplorer";
import { BudgetsCard, ForecastCard } from "../components/planning";
import { ACCOUNT_TYPE_LABELS, PERIODS, PeriodKey, formatCents, formatDate, isoDate, periodRange } from "../format";

const monthFmt = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" });

const monthDate = (key: string) => {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1);
};
const shiftMonth = (key: string, delta: number) => {
  const d = monthDate(key);
  d.setMonth(d.getMonth() + delta);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const pct = (a: number, b: number) => (b > 0 ? Math.round(((a - b) / b) * 100) : null);

export const ACCOUNT_ICONS: Record<string, string> = {
  courant: "💳", epargne: "🐷", investissement: "📈", paypal: "🅿️", especes: "💶", credit: "🧾", bien: "🏡",
};

// Comptes choisis pour le tableau de bord : mémorisés dans ce navigateur.
const ACCOUNTS_KEY = "wallet-dashboard-accounts";
function readAccounts(): number[] {
  try {
    const v = JSON.parse(localStorage.getItem(ACCOUNTS_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "number") : [];
  } catch {
    return [];
  }
}
function saveAccounts(ids: number[]) {
  try {
    localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(ids));
  } catch {
    /* stockage indisponible */
  }
}

function Kpi({
  title,
  icon,
  value,
  sub,
  gradient,
  children,
  active,
  onClick,
}: {
  title: string;
  icon: string;
  value: string;
  sub?: string;
  gradient: string;
  children?: ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-expanded={active}
      className={`relative overflow-hidden rounded-2xl bg-gradient-to-br p-4 text-left text-white shadow-soft transition hover:-translate-y-0.5 hover:shadow-lg ${gradient} ${
        active ? "ring-4 ring-accent-300 ring-offset-2 ring-offset-surface dark:ring-accent-500/60 dark:ring-offset-surface-dark" : ""
      }`}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-white/85">{title}</p>
        <span className="grid h-8 w-8 place-items-center rounded-full bg-white/20 text-base" aria-hidden>{icon}</span>
      </div>
      <p className="mt-2 text-2xl font-bold tabular-nums">{value}</p>
      <div className="mt-1 flex items-end justify-between gap-2">
        {sub && <p className="text-xs text-white/85">{sub}</p>}
        {children}
      </div>
      <span className="absolute bottom-2 right-3 text-xs text-white/70" aria-hidden>{active ? "▴" : "▾"}</span>
    </button>
  );
}

export default function Home() {
  const navigate = useNavigate();
  const location = useLocation();
  // Vue « une catégorie » dans l'adresse (?categorie=…) : le bouton Retour du navigateur ramène au global.
  const focusParam = new URLSearchParams(location.search).get("categorie");
  const focus = focusParam ? Number(focusParam) : null;
  const setFocus = (id: number | null) => navigate(id === null ? "/" : `/?categorie=${id}`);
  const [panel, setPanel] = useState<string | null>(null);
  const [day, setDay] = useState<number | null>(null); // carte « Rythme » : jour cliqué
  const { byId, pathOf, colorOf, iconOf } = useCategories();
  const [month, setMonth] = useState<string | null>(null);
  // « month » = un mois avec ‹ › ; sinon une période (3 mois, année…) ou des dates choisies.
  const [periodKey, setPeriodKey] = useState<PeriodKey>("month");
  const [custom, setCustom] = useState<[string, string]>(["", ""]);
  const [data, setData] = useState<Dashboard | null>(null);
  const [nw, setNw] = useState<NetWorth | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState<number[]>(readAccounts);
  const [sub, setSub] = useState<number | null>(null); // vue catégorie : sous-catégorie mise en avant
  const [active, setActive] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<NetWorth>("/accounts/net-worth").then(setNw);
    api.get<Account[]>("/accounts").then((list) => {
      setAccounts(list);
      setSelected((prev) => prev.filter((id) => list.some((a) => a.id === id))); // comptes supprimés entre-temps
    });
  }, []);
  useEffect(() => {
    const params = new URLSearchParams();
    if (periodKey === "month") {
      if (month) params.set("month", month);
    } else if (periodKey === "custom") {
      if (!custom[0] || !custom[1]) return;
      params.set("date_from", custom[0]);
      params.set("date_to", custom[1]);
    } else {
      const [from, to] = periodRange(periodKey);
      if (from) params.set("date_from", from);
      params.set("date_to", to ?? isoDate(new Date()));
    }
    if (selected.length) params.set("accounts", selected.join(","));
    if (focus !== null) params.set("category_id", String(focus));
    setError(null);
    api.get<Dashboard>(`/dashboard?${params}`).then(setData, (e) => setError((e as Error).message));
  }, [month, periodKey, custom, selected, focus]);
  useEffect(() => setSub(null), [focus, month, periodKey]);
  useEffect(() => setDay(null), [focus, month, periodKey, custom]);
  useEffect(() => setPanel(null), [focus]); // en changeant de mois, le détail ouvert reste ouvert

  const toggleAccount = (id: number | null) => {
    const next = id === null ? [] : selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    const all = next.length === accounts.filter((a) => !a.is_archived).length;
    const value = all ? [] : next;
    setSelected(value);
    saveAccounts(value);
  };

  const slices: Slice[] = useMemo(
    () =>
      (data?.by_category ?? [])
        .filter((c) => c.spent_cents > 0)
        .map((c) => ({
          key: String(c.category_id ?? "none"),
          label: c.category_id === null ? "À catégoriser" : byId.get(c.category_id)?.name ?? "?",
          value: c.spent_cents,
          color: c.category_id === null ? UNCATEGORIZED_COLOR : colorOf(c.category_id),
          icon: iconOf(c.category_id),
        })),
    [data, byId, colorOf, iconOf],
  );

  if (error) return <p className="card text-sm text-red-600">{error}</p>;
  if (!data) return <p className="muted p-4 text-sm">Chargement…</p>;

  const focusCat = focus !== null ? byId.get(focus) : undefined;
  const isMonth = data.period === "month";
  const label = isMonth ? cap(monthFmt.format(monthDate(data.month))) : `Du ${formatDate(data.start)} au ${formatDate(data.end)}`;
  const prevLabel = isMonth ? monthFmt.format(monthDate(shiftMonth(data.month, -1))).split(" ")[0] : "période précédente";
  const vsPrev = isMonth ? `vs ${prevLabel}` : "vs période précédente";
  const sameMoment = isMonth ? " à la même date" : " au même stade";
  const thanPrev = isMonth ? `qu'en ${prevLabel}` : "que sur la période précédente";
  const spentDelta = pct(data.spent_cents, data.is_current ? data.prev_spent_same_day_cents : data.prev_spent_cents);
  const incomeDelta = pct(data.income_cents, data.is_current ? data.prev_income_same_day_cents : data.prev_income_cents);
  const netHistory = data.months.map((m) => m.net_worth_cents).filter((v): v is number => v !== null);
  const activeSlice = slices.find((s) => s.key === active) ?? null;
  const maxCat = Math.max(1, ...data.by_category.map((c) => c.spent_cents));
  const range = `du=${data.start}&au=${data.end}`;
  const diffSameDay = data.spent_cents - data.prev_spent_same_day_cents;
  const todo = data.todo;
  const hasTodo =
    focus === null &&
    (todo.to_categorize_ops > 0 || todo.connections_to_renew.length > 0 || todo.connections_in_error.length > 0 || !!todo.backup_warning ||
      todo.recurring_to_confirm > 0 || todo.price_increases.length > 0 || todo.budget_alerts.length > 0);
  const visibleAccounts = accounts.filter((a) => !a.is_archived);
  const netWorth =
    selected.length === 0
      ? nw?.total_cents ?? null
      : visibleAccounts.filter((a) => selected.includes(a.id) && a.include_in_net_worth).reduce((s, a) => s + (a.balance_cents ?? 0), 0);
  const completeMonths = data.months.filter((m) => m.month < (data.is_current ? data.month : shiftMonth(data.month, 1)));
  const average = completeMonths.length ? Math.round(completeMonths.reduce((s, m) => s + m.spent_cents, 0) / completeMonths.length) : 0;
  const payments = data.transactions.filter((t) => t.amount_cents < 0);
  const biggest = payments.reduce((m, t) => Math.min(m, t.amount_cents), 0);

  const clickCategory = (id: number | null) => {
    if (focus !== null) setSub(sub === id ? null : id);
    else if (id === null) navigate(`/operations?a_categoriser=1&${range}`);
    else setFocus(id);
  };
  const togglePanel = (key: string) => setPanel(panel === key ? null : key);
  const opsLink = `/operations?categorie=${sub ?? focus}&${range}${selected.length === 1 ? `&compte=${selected[0]}` : ""}`;

  // Carte « Rythme des dépenses » (placée à côté de la roue en vue catégorie, en bas sinon).
  const rhythmCard = (className: string) => (
    <RhythmCard
      className={className}
      data={data}
      label={label}
      prevLabel={prevLabel}
      sentence={
        data.is_current ? (
          diffSameDay <= 0 ? (
            <>👏 <b>{formatCents(-diffSameDay)}</b> de moins {thanPrev}{sameMoment}.</>
          ) : (
            <>👀 <b>{formatCents(diffSameDay)}</b> de plus {thanPrev}{sameMoment}.</>
          )
        ) : (
          <>Total : <b>{formatCents(data.spent_cents)}</b> ({prevLabel} : {formatCents(data.prev_spent_cents)}).</>
        )
      }
      day={day}
      onDay={setDay}
    />
  );

  return (
    <div className="space-y-5">
      {/* En-tête + choix du mois */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {focusCat ? (
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost -ml-3" onClick={() => setFocus(null)}>← Toutes les catégories</button>
            <span className="flex items-center gap-2 text-2xl font-bold">
              <CategoryIcon id={focusCat.id} /> {focusCat.name}
            </span>
          </div>
        ) : (
          <div>
            <h1 className="text-2xl font-bold">Bonjour 👋</h1>
            <p className="muted text-sm">
              {todo.last_sync_at
                ? `Dernière synchro bancaire : ${new Date(todo.last_sync_at).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}`
                : "Voici où en est ton argent."}
            </p>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <select
            className="input w-auto py-2 text-sm"
            value={periodKey}
            onChange={(e) => {
              const k = e.target.value as PeriodKey;
              if (k === "custom" && !custom[0]) setCustom([data.start, data.end]);
              setPeriodKey(k);
            }}
            aria-label="Période"
          >
            <option value="month">Par mois</option>
            {PERIODS.filter((p) => !["month", "last_month"].includes(p.key)).map((p) => (
              <option key={p.key} value={p.key}>{p.label}</option>
            ))}
          </select>
          {periodKey === "month" ? (
            <div className="flex items-center gap-1 rounded-2xl bg-panel p-1 shadow-soft dark:bg-panel-dark">
              <button className="btn-ghost px-3" onClick={() => setMonth(shiftMonth(data.month, -1))} aria-label="Mois précédent">‹</button>
              <span className="min-w-[9rem] text-center text-sm font-semibold">{label}</span>
              <button className="btn-ghost px-3" disabled={data.is_current} onClick={() => setMonth(shiftMonth(data.month, 1))} aria-label="Mois suivant">›</button>
            </div>
          ) : periodKey === "custom" ? (
            <div className="flex items-center gap-1 text-sm">
              <input type="date" className="input w-auto py-1.5" value={custom[0]} onChange={(e) => setCustom([e.target.value, custom[1]])} aria-label="Du" />
              <span className="muted">→</span>
              <input type="date" className="input w-auto py-1.5" value={custom[1]} onChange={(e) => setCustom([custom[0], e.target.value])} aria-label="Au" />
            </div>
          ) : (
            <span className="text-sm font-semibold">{label}</span>
          )}
          {!(periodKey === "month" && data.is_current) && (
            <button
              className="btn-ghost text-sm font-medium text-accent-600 dark:text-accent-300"
              onClick={() => {
                setPeriodKey("month");
                setMonth(null);
              }}
            >
              ↺ Mois en cours
            </button>
          )}
        </div>
      </div>

      {/* Comptes pris en compte */}
      {visibleAccounts.length > 1 && (
        <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
          <button
            className={`chip shrink-0 px-3 py-1.5 text-sm ${selected.length === 0 ? "bg-accent-600 text-white" : "bg-panel text-slate-600 shadow-soft dark:bg-panel-dark dark:text-slate-300"}`}
            onClick={() => toggleAccount(null)}
          >
            Tous les comptes
          </button>
          {visibleAccounts.map((a) => {
            const on = selected.includes(a.id);
            return (
              <button
                key={a.id}
                aria-pressed={on}
                className={`chip shrink-0 px-3 py-1.5 text-sm ${on ? "bg-accent-600 text-white" : "bg-panel text-slate-600 shadow-soft dark:bg-panel-dark dark:text-slate-300"}`}
                onClick={() => toggleAccount(a.id)}
              >
                <span aria-hidden>{ACCOUNT_ICONS[a.type] ?? "🏦"}</span> {a.name}
              </button>
            );
          })}
        </div>
      )}

      {/* Chiffres clés */}
      {focusCat ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi
            title="Dépensé"
            active={panel === "spent"}
            onClick={() => togglePanel("spent")}
            icon={iconOf(focusCat.id)}
            value={formatCents(data.spent_cents)}
            gradient="from-rose-500 to-orange-400"
            sub={spentDelta === null ? `${prevLabel} : ${formatCents(data.prev_spent_cents)}` : `${spentDelta > 0 ? "▲" : "▼"} ${Math.abs(spentDelta)} % ${vsPrev}${data.is_current ? sameMoment : ""}`}
          />
          <Kpi title="Moyenne mensuelle" active={panel === "average"} onClick={() => togglePanel("average")} icon="📊" value={formatCents(average)} gradient="from-accent-600 to-fuchsia-500" sub={`sur ${completeMonths.length} mois complets`} />
          <Kpi title="Paiements" active={panel === "merchants"} onClick={() => togglePanel("merchants")} icon="🧾" value={String(payments.length)} gradient="from-sky-500 to-indigo-500" sub={payments.length ? `en moyenne ${formatCents(Math.round(data.spent_cents / payments.length))}` : undefined} />
          <Kpi title="Plus gros paiement" active={panel === "biggest"} onClick={() => togglePanel("biggest")} icon="🔝" value={formatCents(-biggest)} gradient="from-emerald-500 to-teal-400" />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi
            title={data.is_current && isMonth ? "Dépensé ce mois-ci" : "Dépensé"}
            active={panel === "spent"}
            onClick={() => togglePanel("spent")}
            icon="💸"
            value={formatCents(data.spent_cents)}
            gradient="from-rose-500 to-orange-400"
            sub={(spentDelta === null ? `${prevLabel} : ${formatCents(data.prev_spent_cents)}` : `${spentDelta > 0 ? "▲" : "▼"} ${Math.abs(spentDelta)} % ${vsPrev}${data.is_current ? sameMoment : ""}`) + (data.pending_spent_cents > 0 ? ` · ⏳ ${formatCents(data.pending_spent_cents)} à venir` : "")}
          />
          <Kpi
            title="Revenus"
            active={panel === "income"}
            onClick={() => togglePanel("income")}
            icon="💰"
            value={formatCents(data.income_cents)}
            gradient="from-emerald-500 to-teal-400"
            sub={incomeDelta === null ? `${prevLabel} : ${formatCents(data.prev_income_cents)}` : `${incomeDelta >= 0 ? "▲" : "▼"} ${Math.abs(incomeDelta)} % ${vsPrev}${data.is_current ? sameMoment : ""}`}
          />
          <Kpi title={selected.length ? "Patrimoine (comptes choisis)" : "Patrimoine net"} active={panel === "networth"} onClick={() => togglePanel("networth")} icon="🏦" value={netWorth === null ? "…" : formatCents(netWorth)} gradient="from-accent-600 to-fuchsia-500" sub="12 derniers mois">
            <Sparkline values={netHistory} />
          </Kpi>
          <Kpi title="Taux d'épargne" active={panel === "savings"} onClick={() => togglePanel("savings")} icon="🐷"
            value={data.savings_rate === null ? "—" : `${Math.round(data.savings_rate * 100)} %`}
            gradient="from-sky-500 to-indigo-500"
            sub={`${formatCents(data.saved_cents)} mis de côté${data.savings_rate_3m !== null ? ` · ${Math.round(data.savings_rate_3m * 100)} % sur 3 mois` : ""}`}
          />
        </div>
      )}

      {panel && (
        <KpiPanel
          kind={panel}
          data={data}
          focusName={focusCat?.name ?? null}
          accounts={visibleAccounts.filter((a) => a.include_in_net_worth && (selected.length === 0 || selected.includes(a.id)))}
          opsLink={`/operations?${focus !== null ? `categorie=${focus}&` : ""}${range}${selected.length === 1 ? `&compte=${selected[0]}` : ""}`}
          onClose={() => setPanel(null)}
        />
      )}

      {hasTodo && (
        <section className="card flex flex-wrap items-center gap-3 border-amber-200 bg-amber-50 dark:border-amber-500/20 dark:bg-amber-500/10">
          <span className="text-xl" aria-hidden>✨</span>
          <div className="flex flex-1 flex-wrap gap-x-4 gap-y-1 text-sm">
            {todo.to_categorize_ops > 0 && (
              <Link to="/operations?a_categoriser=1" className="font-medium underline-offset-2 hover:underline">
                {todo.to_categorize_ops} opération(s) à catégoriser ({todo.to_categorize_merchants} vendeur(s))
              </Link>
            )}
            {todo.connections_to_renew.map((c) => (
              <Link key={c} to="/parametres/connexions" className="font-medium hover:underline">🔑 Autorisation à renouveler : {c}</Link>
            ))}
            {todo.connections_in_error.map((c) => (
              <Link key={c} to="/parametres/connexions" className="font-medium text-red-600 hover:underline">⚠️ Connexion à vérifier : {c}</Link>
            ))}
            {todo.backup_warning && (
              <Link to="/parametres/securite" className="font-medium hover:underline">💾 {todo.backup_warning}</Link>
            )}
            {todo.budget_alerts.map((b) => (
              <Link key={b.category_id} to="/prevoir/budgets" className={`font-medium hover:underline ${b.level === "depasse" ? "text-red-600" : ""}`}>
                {b.level === "depasse" ? "⛔ Budget dépassé" : "⚠️ Budget à surveiller"} : {pathOf(b.category_id)}
              </Link>
            ))}
            {todo.price_increases.map((label) => (
              <Link key={label} to="/prevoir/recurrents" className="font-medium hover:underline">📈 Hausse de prix : {label}</Link>
            ))}
            {todo.recurring_to_confirm > 0 && (
              <Link to="/prevoir/recurrents" className="font-medium hover:underline">🔁 {todo.recurring_to_confirm} récurrent(s) détecté(s) à confirmer</Link>
            )}
          </div>
        </section>
      )}

      <div className="grid gap-4 lg:grid-cols-5">
        {/* Dépenses par catégorie / par sous-catégorie */}
        <section className="card space-y-4 lg:col-span-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              {focusCat && (
                <button className="btn-ghost -ml-2 px-2 py-1 text-sm" onClick={() => setFocus(null)} title="Revenir à toutes les catégories">
                  ← Toutes
                </button>
              )}
              <h2 className="section-title">{focusCat ? `${focusCat.name} par sous-catégorie` : "Dépenses par catégorie"}</h2>
            </div>
            <span className="muted text-xs">{focusCat ? "clic = filtrer les paiements" : `clic = détail · ${vsPrev}`}</span>
          </div>
          {slices.length === 0 ? (
            <p className="muted text-sm">Aucune dépense ce mois-ci.</p>
          ) : (
            <div className="grid items-center gap-4 sm:grid-cols-[220px_1fr]">
              <Donut
                slices={slices}
                active={active ?? (sub !== null ? String(sub) : null)}
                onActive={setActive}
                onSelect={(key) => clickCategory(key === "none" ? null : Number(key))}
                center={
                  activeSlice ? (
                    <div>
                      <p className="text-2xl" aria-hidden>{activeSlice.icon}</p>
                      <p className="text-xs muted">{activeSlice.label}</p>
                      <p className="font-bold tabular-nums">{formatCents(activeSlice.value)}</p>
                      <p className="text-xs muted">{Math.round((activeSlice.value / Math.max(data.spent_cents, 1)) * 100)} %</p>
                    </div>
                  ) : (
                    <div>
                      <p className="text-xs muted">Total</p>
                      <p className="text-lg font-bold tabular-nums">{formatCents(data.spent_cents)}</p>
                    </div>
                  )
                }
              />
              <ul className="space-y-1">
                {data.by_category.slice(0, focusCat ? 20 : 8).map((c) => {
                  const key = String(c.category_id ?? "none");
                  const delta = c.spent_cents - c.prev_spent_cents;
                  const name =
                    c.category_id === null ? "À catégoriser" : focusCat && c.category_id === focusCat.id ? `${focusCat.name} (général)` : focusCat ? byId.get(c.category_id)?.name ?? "?" : pathOf(c.category_id);
                  return (
                    <li key={key}>
                      <button
                        className={`flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left transition hover:bg-slate-50 dark:hover:bg-white/5 ${
                          active === key || (sub !== null && sub === c.category_id) ? "bg-slate-50 dark:bg-white/5" : ""
                        }`}
                        onMouseEnter={() => setActive(key)}
                        onMouseLeave={() => setActive(null)}
                        onClick={() => clickCategory(c.category_id)}
                      >
                        <CategoryIcon id={c.category_id} size="sm" />
                        <div className="min-w-0 flex-1">
                          <div className="flex justify-between gap-2 text-sm">
                            <span className="truncate">{name}</span>
                            <span className="font-semibold tabular-nums">{formatCents(c.spent_cents)}</span>
                          </div>
                          <div className="mt-1 flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-slate-100 dark:bg-white/5">
                              <div className="h-1.5 rounded-full" style={{ width: `${(c.spent_cents / maxCat) * 100}%`, background: c.category_id === null ? UNCATEGORIZED_COLOR : colorOf(c.category_id) }} />
                            </div>
                            <span className={`w-20 text-right text-[11px] tabular-nums ${delta > 0 ? "text-rose-600 dark:text-rose-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                              {delta > 0 ? "+" : delta < 0 ? "−" : ""}
                              {formatCents(Math.abs(delta))}
                            </span>
                          </div>
                        </div>
                        {!focusCat && c.category_id !== null && <span className="muted text-xs" aria-hidden>›</span>}
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </section>

        {/* À côté de la roue : derniers mouvements (vue globale) ou rythme des dépenses (vue catégorie) */}
        {focusCat ? rhythmCard("lg:col-span-2") : <LatestMoves accounts={selected} className="lg:col-span-2" />}
      </div>

      {/* Ce mois-ci : fin de mois prévue et budgets */}
      {!focusCat && data.is_current && (
        <div className="grid gap-4 md:grid-cols-2">
          <ForecastCard />
          <BudgetsCard />
        </div>
      )}

      {/* Vue catégorie : les paiements du mois, par sous-catégorie */}
      {focusCat && (
        <section className="card space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="section-title">
              Paiements {isMonth ? `de ${label.toLowerCase()}` : "de la période"}
              {sub !== null && <> · {sub === focusCat.id ? "général" : byId.get(sub)?.name}</>}
            </h2>
            <div className="flex gap-2">
              {sub !== null && <button className="btn-ghost" onClick={() => setSub(null)}>Toutes les sous-catégories</button>}
              <Link to={opsLink} className="btn-ghost text-accent-600 dark:text-accent-300">Ouvrir dans Opérations →</Link>
            </div>
          </div>
          {data.by_category
            .filter((g) => sub === null || g.category_id === sub)
            .map((g) => {
              const rows = data.transactions.filter((t) => t.category_id === g.category_id);
              if (!rows.length) return null;
              return (
                <details key={String(g.category_id)} open className="rounded-xl bg-slate-50 p-3 dark:bg-white/5">
                  <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium">
                    <CategoryIcon id={g.category_id} size="sm" />
                    <span className="flex-1">{g.category_id === focusCat.id ? `${focusCat.name} (général)` : byId.get(g.category_id ?? -1)?.name}</span>
                    <span className="muted text-xs">{rows.length} op.</span>
                    <span className="tabular-nums">{formatCents(g.spent_cents)}</span>
                  </summary>
                  <ul className="mt-2 divide-y divide-slate-200/70 dark:divide-white/5">
                    {rows.map((t) => (
                      <li key={t.id} className="flex items-center gap-3 py-1.5 text-sm">
                        <span className="muted w-20 shrink-0 text-xs">{formatDate(t.booked_at)}</span>
                        <span className="min-w-0 flex-1 truncate">{t.label}</span>
                        <span className="muted hidden text-xs sm:inline">{t.account_name}</span>
                        <span className={`w-24 text-right font-semibold tabular-nums ${t.amount_cents > 0 ? "text-emerald-600" : ""}`}>{formatCents(t.amount_cents)}</span>
                      </li>
                    ))}
                  </ul>
                </details>
              );
            })}
          {data.transactions.length === 0 && <p className="muted text-sm">Aucun paiement ce mois-ci.</p>}
        </section>
      )}

      {/* Historique mois par mois (fenêtre réglable, qu'on fait défiler) */}
      <MonthsExplorer
        accounts={selected}
        categoryId={focus}
        title={focusCat ? `${focusCat.name} mois par mois` : "Revenus et dépenses mois par mois"}
        selected={isMonth ? data.month : undefined}
        onSelect={(key) => {
          setPeriodKey("month");
          setMonth(key);
        }}
      />

      <div className={`grid gap-4 ${focusCat ? "lg:grid-cols-3" : "md:grid-cols-2"}`}>
        {!focusCat && rhythmCard("")}
        {!focusCat && (
          <section className="card space-y-2">
            <h2 className="section-title">Plus grosses dépenses</h2>
            <ul className="divide-y divide-slate-100 dark:divide-white/5">
              {data.top_expenses.map((t) => (
                <li key={t.id} className="flex items-center gap-3 py-2">
                  <CategoryIcon id={t.category_id} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{t.label}</p>
                    <p className="muted text-xs">{formatDate(t.booked_at)} · {t.account_name}</p>
                  </div>
                  <span className="text-sm font-semibold tabular-nums">{formatCents(t.amount_cents)}</span>
                </li>
              ))}
              {data.top_expenses.length === 0 && <li className="muted py-2 text-sm">Rien pour l'instant.</li>}
            </ul>
          </section>
        )}

        <section className="card space-y-2">
          <h2 className="section-title">Vendeurs du mois</h2>
          <ul className="divide-y divide-slate-100 dark:divide-white/5">
            {data.top_merchants.map((m, i) => (
              <li key={m.merchant_id ?? i} className="flex items-center gap-3 py-2">
                <span className="grid h-6 w-6 place-items-center rounded-full bg-accent-100 text-xs font-bold text-accent-700 dark:bg-accent-500/20 dark:text-accent-200">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{m.name}</p>
                  <p className="muted text-xs">{m.count} achat(s)</p>
                </div>
                <span className="text-sm font-semibold tabular-nums">{formatCents(m.spent_cents)}</span>
              </li>
            ))}
            {data.top_merchants.length === 0 && <li className="muted py-2 text-sm">Rien pour l'instant.</li>}
          </ul>
          <Link to="/vendeurs" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-300">Tous les vendeurs →</Link>
        </section>

        {!focusCat && (
          <section className="card space-y-2">
            <h2 className="section-title">Mes comptes</h2>
            <ul className="divide-y divide-slate-100 dark:divide-white/5">
              {visibleAccounts.map((a) => (
                <li key={a.id} className={`flex items-center gap-3 py-2 ${selected.length && !selected.includes(a.id) ? "opacity-40" : ""}`}>
                  <span className="grid h-8 w-8 place-items-center rounded-full bg-slate-100 dark:bg-white/5" aria-hidden>{ACCOUNT_ICONS[a.type] ?? "🏦"}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{a.name}</p>
                    <p className="muted text-xs">{ACCOUNT_TYPE_LABELS[a.type]}</p>
                  </div>
                  <span className={`text-sm font-semibold tabular-nums ${(a.balance_cents ?? 0) < 0 ? "text-rose-600" : ""}`}>
                    {a.balance_cents === null ? "—" : formatCents(a.balance_cents)}
                  </span>
                </li>
              ))}
              {accounts.length === 0 && (
                <li className="muted py-2 text-sm">
                  Aucun compte. <Link to="/comptes" className="underline">Ajoute ton premier compte</Link>.
                </li>
              )}
            </ul>
          </section>
        )}
      </div>
    </div>
  );
}

const dayFmt = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "short" });
const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + n);
  return d;
};

/** Carte « Rythme des dépenses » : courbe cumulée + chiffres du rythme ; clic sur un jour = ses dépenses. */
function RhythmCard({
  className = "",
  data,
  label,
  prevLabel,
  sentence,
  day,
  onDay,
}: {
  className?: string;
  data: Dashboard;
  label: string;
  prevLabel: string;
  sentence: ReactNode;
  day: number | null;
  onDay: (d: number | null) => void;
}) {
  const cum = data.daily_cumulative;
  const totalDays = Math.max(data.prev_daily_cumulative.length, Math.round((new Date(data.end).getTime() - new Date(data.start).getTime()) / 86_400_000) + 1);
  const daily = cum.map((v, i) => v - (i > 0 ? cum[i - 1] : 0));
  const elapsed = Math.max(cum.length, 1);
  const perDay = Math.round(data.spent_cents / elapsed);
  const projection = data.is_current ? Math.round(perDay * totalDays) : null;
  const maxDay = daily.reduce((best, v, i) => (v > daily[best] ? i : best), 0);
  const quietDays = daily.filter((v) => v === 0).length;
  const dayIso = (i: number) => {
    const d = addDays(data.start, i);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  };
  const dayRows = day === null ? [] : data.transactions.filter((t) => t.amount_cents < 0 && t.booked_at === dayIso(day));

  return (
    <section className={`card flex flex-col gap-3 ${className}`}>
      <ChartFrame
        title="Rythme des dépenses"
        help="Touche la courbe pour voir les dépenses d'un jour."
        controls={<p className="text-sm">{sentence}</p>}
      >
      <CumulativeChart
        current={cum}
        previous={data.prev_daily_cumulative}
        days={totalDays}
        height={250}
        selected={day}
        onSelectDay={onDay}
        dayLabel={(i) => cap(dayFmt.format(addDays(data.start, i)))}
      />
      </ChartFrame>
      <Legend items={[{ label, color: ACCENT }, { label: cap(prevLabel), color: MUTED_LINE, dashed: true }]} />
      {day === null ? (
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="rounded-xl bg-slate-50 p-2 dark:bg-white/5">
            <p className="muted text-xs">Moyenne par jour</p>
            <p className="font-semibold tabular-nums">{formatCents(perDay)}</p>
          </div>
          <div className="rounded-xl bg-slate-50 p-2 dark:bg-white/5">
            <p className="muted text-xs">{projection !== null ? "À ce rythme, en fin de période" : "Total"}</p>
            <p className="font-semibold tabular-nums">{formatCents(projection ?? data.spent_cents)}</p>
          </div>
          <button className="rounded-xl bg-slate-50 p-2 text-left hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10" onClick={() => daily[maxDay] > 0 && onDay(maxDay)}>
            <p className="muted text-xs">Plus grosse journée</p>
            <p className="font-semibold tabular-nums">
              {daily[maxDay] > 0 ? <>{formatCents(daily[maxDay])} <span className="muted text-xs font-normal">· {dayFmt.format(addDays(data.start, maxDay))}</span></> : "—"}
            </p>
          </button>
          <div className="rounded-xl bg-slate-50 p-2 dark:bg-white/5">
            <p className="muted text-xs">Jours sans dépense</p>
            <p className="font-semibold tabular-nums">{quietDays} / {cum.length}</p>
          </div>
        </div>
      ) : (
        <div className="space-y-2 rounded-xl bg-slate-50 p-3 dark:bg-white/5">
          <div className="flex items-center justify-between gap-2 text-sm">
            <p className="font-semibold">
              {cap(dayFmt.format(addDays(data.start, day)))} · {formatCents(daily[day] ?? 0)}
            </p>
            <button className="btn-ghost px-2 py-1" onClick={() => onDay(null)} aria-label="Fermer">✕</button>
          </div>
          <ul className="divide-y divide-slate-200/70 text-sm dark:divide-white/5">
            {dayRows.map((t) => (
              <li key={t.id} className="flex items-center gap-2 py-1.5">
                <CategoryIcon id={t.category_id} size="sm" />
                <span className="min-w-0 flex-1 truncate">{t.label}</span>
                <span className="font-semibold tabular-nums">{formatCents(t.amount_cents)}</span>
              </li>
            ))}
            {dayRows.length === 0 && <li className="muted py-1.5">Aucune dépense ce jour-là.</li>}
          </ul>
        </div>
      )}
    </section>
  );
}

/** Carte « Derniers mouvements » : opérations à venir puis les dernières opérations ; clic → Opérations. */
function LatestMoves({ accounts, className = "" }: { accounts: number[]; className?: string }) {
  const navigate = useNavigate();
  const [items, setItems] = useState<Transaction[]>([]);
  const [pending, setPending] = useState<Pending[]>([]);
  const key = accounts.join(",");
  useEffect(() => {
    const one = accounts.length === 1 ? `&account_id=${accounts[0]}` : "";
    api.get<{ items: Transaction[] }>(`/transactions?limit=40${one}`).then((p) =>
      setItems(p.items.filter((t) => accounts.length === 0 || accounts.includes(t.account_id)).slice(0, 8)),
    );
    api.get<Pending[]>(`/pending${accounts.length === 1 ? `?account_id=${accounts[0]}` : ""}`).then((p) =>
      setPending(p.filter((t) => accounts.length === 0 || accounts.includes(t.account_id)).slice(0, 3)),
    );
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  const open = () => navigate(accounts.length === 1 ? `/operations?compte=${accounts[0]}` : "/operations");

  return (
    <section className={`card space-y-2 ${className}`}>
      <div className="flex items-center justify-between">
        <h2 className="section-title">Derniers mouvements</h2>
        <Link to="/operations" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-300">Toutes les opérations →</Link>
      </div>
      <ul className="divide-y divide-slate-100 dark:divide-white/5">
        {pending.map((p) => (
          <li key={`p${p.id}`}>
            <button className="flex w-full items-center gap-3 py-2 text-left opacity-80 hover:opacity-100" onClick={open}>
              <CategoryIcon id={p.category_id} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{p.label}</p>
                <p className="muted text-xs">⏳ à venir · {p.account_name}</p>
              </div>
              <span className="text-sm font-semibold tabular-nums">{formatCents(p.amount_cents)}</span>
            </button>
          </li>
        ))}
        {items.map((t) => (
          <li key={t.id}>
            <button className="flex w-full items-center gap-3 py-2 text-left hover:bg-slate-50 dark:hover:bg-white/5" onClick={open}>
              <CategoryIcon id={t.category_id} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{t.label}</p>
                <p className="muted text-xs">{formatDate(t.booked_at)} · {t.account_name}</p>
              </div>
              <span className={`text-sm font-semibold tabular-nums ${t.amount_cents > 0 ? "text-emerald-600 dark:text-emerald-400" : ""} ${t.counted && !t.is_transfer ? "" : "opacity-60"}`}>
                {formatCents(t.amount_cents)}
              </span>
            </button>
          </li>
        ))}
        {items.length === 0 && pending.length === 0 && <li className="muted py-2 text-sm">Aucune opération pour l'instant.</li>}
      </ul>
    </section>
  );
}
