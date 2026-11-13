import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";
import {
  Account,
  api,
  BudgetItem,
  BudgetsOverview,
  Forecast,
  ForecastCategory,
  ModelView,
  Frequency,
  FREQUENCY_LABELS,
  Nature,
  NATURE_LABELS,
  Projection,
  Recurring,
  RecurringSummary,
  ScenarioIn,
} from "../api";
import { CategoryIcon, CategorySelect, useCategories } from "../components/categories";
import { ACCENT, ChartFrame, LAYER_COLORS, Legend, LineChart, ProjectionBars, TreasuryChart, TreasuryShow } from "../components/charts";
import { BudgetBar, LEVELS, shortDate } from "../components/planning";
import { formatCents, isoDate, parseEuros } from "../format";

const TABS = [
  { to: "tresorerie", label: "Trésorerie", icon: "🔮" },
  { to: "projection", label: "Projection", icon: "📈" },
  { to: "budgets", label: "Budgets", icon: "🎯" },
  { to: "recurrents", label: "Récurrents", icon: "🔁" },
];

export default function Planning() {
  // Le scénario « et si » est commun à Trésorerie et Projection (on le garde en changeant d'onglet).
  const [sc, setSc] = useState<ScenarioState>(NO_SCENARIO);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Prévoir</h1>
      <nav className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={`/prevoir/${t.to}`}
            className={({ isActive }) =>
              `chip shrink-0 px-3 py-1.5 text-sm ${isActive ? "bg-accent-600 text-white" : "bg-panel text-slate-600 shadow-soft dark:bg-panel-dark dark:text-slate-300"}`
            }
          >
            <span aria-hidden>{t.icon}</span> {t.label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route path="tresorerie" element={<Treasury sc={sc} setSc={setSc} />} />
        <Route path="projection" element={<ProjectionPage sc={sc} setSc={setSc} />} />
        <Route path="budgets" element={<Budgets />} />
        <Route path="recurrents" element={<RecurringPage />} />
        <Route path="*" element={<Navigate to="/prevoir/tresorerie" replace />} />
      </Routes>
    </div>
  );
}

const longDate = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "long" });
const fmtLong = (iso: string) => longDate.format(new Date(`${iso}T12:00:00`));
const KIND_ICONS: Record<string, string> = { depense: "▼", revenu: "▲", virement: "↔", a_venir: "⏳" };

// --- Scénario partagé (Trésorerie et Projection) ---------------------------------------------------

interface ScenarioState {
  plaisirPct: number;
  applyBudgets: boolean;
  targets: Record<string, number>;
  extra: string;
  /** Catégories retirées des prévisions (touchées dans les listes Essentiels / Plaisirs). */
  off: number[];
}
const NO_SCENARIO: ScenarioState = { plaisirPct: 100, applyBudgets: false, targets: {}, extra: "", off: [] };

function scenarioBody(sc: ScenarioState): ScenarioIn {
  const targets = { ...sc.targets, ...Object.fromEntries(sc.off.map((id) => [String(id), 0])) };
  return { plaisir_pct: sc.plaisirPct, apply_budgets: sc.applyBudgets, targets, extra_saving_cents: Math.max(parseEuros(sc.extra) ?? 0, 0) };
}
const scenarioActive = (sc: ScenarioState) =>
  sc.plaisirPct !== 100 || sc.applyBudgets || Object.keys(sc.targets).length > 0 || sc.off.length > 0 || (parseEuros(sc.extra) ?? 0) > 0;

const NATURES: Nature[] = ["fixe", "essentiel", "plaisir"];
const ARROWS: Record<string, string> = { hausse: "↗", baisse: "↘", stable: "" };

function AccountChips({ selected, onToggle }: { selected: number[]; onToggle: (id: number) => void }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  useEffect(() => {
    api.get<Account[]>("/accounts").then((list) => setAccounts(list.filter((a) => !a.is_archived)));
  }, []);
  return (
    <div className="flex flex-wrap gap-2">
      {accounts.map((a) => (
        <button
          key={a.id}
          className={`chip px-3 py-1 text-xs ${selected.includes(a.id) ? "bg-accent-50 font-semibold text-accent-700 ring-1 ring-accent-300 dark:bg-accent-500/15 dark:text-accent-200" : "muted bg-slate-100 dark:bg-white/5"}`}
          onClick={() => onToggle(a.id)}
        >
          {a.name}
        </button>
      ))}
    </div>
  );
}

function useAccountsChoice(defaults: number[] | undefined) {
  const [chosen, setChosen] = useState<number[] | null>(null);
  const selected = chosen ?? defaults ?? [];
  const toggle = (id: number) => {
    const next = selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
    if (next.length) setChosen(next);
  };
  return { chosen, selected, toggle };
}

/** « Et si… » : plaisirs, budgets appliqués, objectifs par catégorie, épargne en plus. */
function ScenarioPanel({ sc, setSc, model }: { sc: ScenarioState; setSc: (s: ScenarioState) => void; model: ModelView | null }) {
  const { pathOf } = useCategories();
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<number | null>>(new Set());
  const [msg, setMsg] = useState<string | null>(null);
  const active = scenarioActive(sc);
  const setTarget = (cid: number | null, value: string) => {
    if (cid === null) return;
    const cents = parseEuros(value);
    const targets = { ...sc.targets };
    if (value.trim() === "" || cents === null || cents < 0) delete targets[String(cid)];
    else targets[String(cid)] = cents;
    setSc({ ...sc, targets });
  };
  const saveAsBudgets = async () => {
    const entries = Object.entries(sc.targets);
    for (const [cid, cents] of entries) {
      try {
        await api.put(`/budgets/${cid}`, { monthly_amount_cents: Math.max(cents, 100) });
      } catch {
        /* catégorie qui n'est pas une dépense : ignorée */
      }
    }
    setMsg(`${entries.length} objectif(s) enregistré(s) comme budgets.`);
  };
  const toggleGroup = (cid: number | null) => {
    const next = new Set(expanded);
    if (next.has(cid)) next.delete(cid);
    else next.add(cid);
    setExpanded(next);
  };

  return (
    <section className={`card space-y-3 ${active ? "ring-2 ring-accent-200 dark:ring-accent-800" : ""}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-title">🎛️ Et si… {active && <span className="chip ml-1 bg-accent-50 text-accent-700 dark:bg-accent-500/15 dark:text-accent-200">scénario actif</span>}</h2>
        {active && <button className="btn-ghost text-xs" onClick={() => setSc(NO_SCENARIO)}>↺ Revenir à mes habitudes</button>}
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="space-y-1 text-sm">
          <span className="flex justify-between">
            <span>Mes plaisirs à…</span>
            <b className="tabular-nums">{sc.plaisirPct} %</b>
          </span>
          <input type="range" min={0} max={150} step={10} value={sc.plaisirPct} onChange={(e) => setSc({ ...sc, plaisirPct: Number(e.target.value) })} className="w-full accent-accent-600" />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={sc.applyBudgets} onChange={(e) => setSc({ ...sc, applyBudgets: e.target.checked })} />
          Je respecte mes budgets
        </label>
        <label className="space-y-1 text-sm">
          <span>Épargne en plus chaque mois</span>
          <input className="input" inputMode="decimal" placeholder="0 €" value={sc.extra} onChange={(e) => setSc({ ...sc, extra: e.target.value })} />
        </label>
      </div>
      <button className="btn-ghost -ml-3 text-sm" onClick={() => setOpen(!open)}>
        {open ? "▾" : "▸"} Objectifs par catégorie {Object.keys(sc.targets).length > 0 && `(${Object.keys(sc.targets).length})`}
      </button>
      {open && model && (
        <div className="space-y-2">
          <Help>
            Tendance = ce que tu dépenses d'habitude chaque mois (moyenne pondérée de tes {model.months_used} derniers mois, les plus récents comptant plus ;
            hors récurrents). Fixe un objectif pour voir l'effet sur ton solde. Charges récurrentes : à gérer dans 🔁 Récurrents. La couche de
            chaque catégorie (fixe, essentiel, plaisir) se règle dans <Link to="/categories" className="underline">Catégories</Link>.
          </Help>
          <div className="divide-y divide-slate-100 text-sm dark:divide-white/5">
            {model.groups.map((g) => (
              <div key={g.category_id ?? 0} className="py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <button className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => toggleGroup(g.category_id)}>
                    <span className="muted w-3 text-xs">{g.children.length > 1 || g.children[0]?.category_id !== g.category_id ? (expanded.has(g.category_id) ? "▾" : "▸") : ""}</span>
                    <CategoryIcon id={g.category_id} size="sm" />
                    <span className="truncate font-medium">{g.category_id === null ? "À catégoriser" : pathOf(g.category_id)}</span>
                    {g.layers.map((n) => <span key={n} className="inline-block h-2.5 w-2.5 shrink-0 rounded" style={{ background: LAYER_COLORS[n] }} title={NATURE_LABELS[n]} />)}
                  </button>
                  <span className="muted shrink-0 text-xs tabular-nums">tendance {formatCents(g.trend_cents)}</span>
                  {g.budget_cents !== null && <span className="muted shrink-0 text-xs tabular-nums">· budget {formatCents(g.budget_cents)}</span>}
                  {g.category_id !== null && (
                    <input
                      className="input w-24 py-1 text-right text-xs"
                      inputMode="decimal"
                      placeholder="objectif"
                      defaultValue={sc.targets[String(g.category_id)] !== undefined ? String(sc.targets[String(g.category_id)] / 100).replace(".", ",") : ""}
                      onBlur={(e) => setTarget(g.category_id, e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                      aria-label="Objectif mensuel"
                    />
                  )}
                  {g.scenario_cents !== g.trend_cents && <span className="shrink-0 text-xs font-semibold tabular-nums text-accent-700 dark:text-accent-300">→ {formatCents(g.scenario_cents)}</span>}
                </div>
                {expanded.has(g.category_id) && (
                  <ul className="ml-8 mt-1 space-y-1">
                    {g.children.map((ch) => (
                      <li key={ch.category_id ?? 0} className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="inline-block h-2 w-2 shrink-0 rounded" style={{ background: LAYER_COLORS[ch.layer] }} />
                        <span className="min-w-0 flex-1 truncate">{ch.category_id === null ? "À catégoriser" : pathOf(ch.category_id)}</span>
                        <span className="muted tabular-nums">
                          {formatCents(ch.trend_cents)} / mois {ARROWS[ch.direction]}
                          {ch.budget_cents !== null && ` · budget ${formatCents(ch.budget_cents)}`}
                        </span>
                        {ch.category_id !== null && ch.category_id !== g.category_id && (
                          <input
                            className="input w-20 py-0.5 text-right text-xs"
                            inputMode="decimal"
                            placeholder="objectif"
                            defaultValue={sc.targets[String(ch.category_id)] !== undefined ? String(sc.targets[String(ch.category_id)] / 100).replace(".", ",") : ""}
                            onBlur={(e) => setTarget(ch.category_id, e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                            aria-label="Objectif mensuel"
                          />
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            {model.groups.length === 0 && <p className="muted py-2">Pas encore assez d'historique (il faut au moins un mois complet).</p>}
          </div>
          {Object.keys(sc.targets).length > 0 && (
            <button className="btn-ghost text-sm" onClick={saveAsBudgets}>💾 Enregistrer ces objectifs comme budgets</button>
          )}
          {msg && <p className="muted text-sm">{msg}</p>}
        </div>
      )}
    </section>
  );
}

/** Pastilles qui montrent / retirent une couche du calcul (les charges fixes restent toujours). */
function LayerToggles({ show, setShow }: { show: TreasuryShow; setShow: (s: TreasuryShow) => void }) {
  const chip = (on: boolean) =>
    `chip gap-2 border px-3 py-1 text-xs ${on ? "border-slate-200 bg-panel dark:border-white/10 dark:bg-panel-dark" : "border-transparent bg-slate-100 line-through opacity-50 dark:bg-white/5"}`;
  const items: { key: keyof TreasuryShow; label: string; color: string }[] = [
    { key: "revenu", label: "Revenus", color: "#0f9f6e" },
    { key: "essentiel", label: "Essentiels", color: LAYER_COLORS.essentiel },
    { key: "plaisir", label: "Plaisirs", color: LAYER_COLORS.plaisir },
  ];
  return (
    <div className="flex flex-wrap gap-2">
      <span className={chip(true)} title="Toujours comptées">
        <span className="inline-block h-1 w-4 rounded" style={{ background: LAYER_COLORS.fixe }} />
        Charges fixes 🔒
      </span>
      {items.map((it) => (
        <button key={it.key} className={chip(show[it.key])} aria-pressed={show[it.key]} onClick={() => setShow({ ...show, [it.key]: !show[it.key] })}>
          <span className="inline-block h-1 w-4 rounded" style={{ background: it.color }} />
          {it.label}
        </button>
      ))}
    </div>
  );
}

// --- Trésorerie ---------------------------------------------------------------------------------

const HORIZONS = [
  { key: "fin_du_mois", label: "Fin du mois" },
  { key: "fin_mois_prochain", label: "Fin du mois prochain" },
  { key: "30", label: "30 jours" },
  { key: "90", label: "3 mois" },
  { key: "182", label: "6 mois" },
  { key: "365", label: "1 an" },
];

function Treasury({ sc, setSc }: { sc: ScenarioState; setSc: (s: ScenarioState) => void }) {
  const [horizon, setHorizon] = useState("fin_du_mois");
  const [show, setShow] = useState<TreasuryShow>({ revenu: true, essentiel: true, plaisir: true });
  const [endDate, setEndDate] = useState("");
  const [f, setF] = useState<Forecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const acc = useAccountsChoice(f?.account_ids);
  const body = JSON.stringify(scenarioBody(sc));

  useEffect(() => {
    const t = setTimeout(() => {
      const params = new URLSearchParams(endDate ? { end_date: endDate } : { horizon });
      if (acc.chosen) params.set("accounts", acc.chosen.join(","));
      api.post<Forecast>(`/forecast?${params}`, JSON.parse(body)).then((r) => {
        setF(r);
        setError(null);
      }, (e) => setError((e as Error).message));
    }, 250);
    return () => clearTimeout(t);
  }, [horizon, endDate, acc.chosen?.join(","), body]); // eslint-disable-line react-hooks/exhaustive-deps

  const low = f?.lowest && f.lowest.balance_cents < 0 ? f.lowest : null;
  const active = f?.scenario.active ?? false;
  const delta = f ? f.end_balance_cents - f.baseline_end_cents : 0;

  return (
    <div className="space-y-4">
      <section className="card space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {HORIZONS.map((h) => (
            <button
              key={h.key}
              className={`chip px-3 py-1 text-sm ${!endDate && horizon === h.key ? "bg-accent-600 text-white" : "bg-slate-100 dark:bg-white/5"}`}
              onClick={() => { setHorizon(h.key); setEndDate(""); }}
            >
              {h.label}
            </button>
          ))}
          <label className={`chip gap-2 px-3 py-1 text-sm ${endDate ? "bg-accent-600 text-white" : "bg-slate-100 dark:bg-white/5"}`}>
            Jusqu'au
            <input type="date" className="bg-transparent text-sm outline-none" value={endDate} min={isoDate(new Date(Date.now() + 864e5))} onChange={(e) => setEndDate(e.target.value)} />
          </label>
        </div>
        <AccountChips selected={acc.selected} onToggle={acc.toggle} />
      </section>

      <ScenarioPanel sc={sc} setSc={setSc} model={f?.model ?? null} />

      {error && <p className="text-sm text-red-600">{error}</p>}
      {f && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Aujourd'hui" value={formatCents(f.start_balance_cents)} />
            <Stat
              label={`Prévu le ${shortDate(f.horizon)}`}
              value={formatCents(f.end_balance_cents)}
              sub={active ? `${delta >= 0 ? "+" : ""}${formatCents(delta)} grâce au scénario` : undefined}
              tone={f.end_balance_cents < 0 ? "bad" : undefined}
            />
            <Stat label="Point le plus bas" value={f.lowest ? formatCents(f.lowest.balance_cents) : "—"} sub={f.lowest ? shortDate(f.lowest.date) : undefined} tone={low ? "bad" : undefined} />
            <div className="card space-y-0.5 p-3 text-xs">
              <p className="flex justify-between"><span className="muted">Revenus</span><b className="tabular-nums text-emerald-700 dark:text-emerald-400">{formatCents(f.totals.income_cents)}</b></p>
              <p className="flex justify-between"><span className="muted">Charges fixes</span><span className="tabular-nums">{formatCents(-f.totals.fixe_cents)}</span></p>
              <p className="flex justify-between"><span className="muted">Essentiels</span><span className="tabular-nums">{formatCents(-f.totals.essentiel_cents)}</span></p>
              <p className="flex justify-between"><span className="muted">Plaisirs</span><span className="tabular-nums">{formatCents(-f.totals.plaisir_cents)}</span></p>
              {f.totals.epargne_cents !== 0 && <p className="flex justify-between"><span className="muted">Épargne</span><span className="tabular-nums">{formatCents(-f.totals.epargne_cents)}</span></p>}
            </div>
          </div>
          {low && (
            <p className="card border-rose-200 bg-rose-50 text-sm font-medium text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
              ⚠️ Découvert possible à partir du {fmtLong(low.date)} ({formatCents(low.balance_cents)}). Pense à approvisionner le compte avant.
            </p>
          )}
          <section className="card space-y-3">
            <ChartFrame
              title="Solde prévu jour par jour"
              help={
                <>
                  En haut, ton solde prévu (violet) et, en pointillé, ce qu'il serait si tu ne payais que tes charges fixes : l'écart montre ce
                  que coûtent tes dépenses courantes. Pastilles : échéances (vert : revenu, bleu : charge fixe). En bas, ce qui entre et sort
                  chaque jour : les gros montants (salaire, loyer) sont écrêtés, leur montant est écrit. Essentiels et plaisirs suivent tes
                  habitudes (tendance de chaque catégorie, répartie selon les jours où tu dépenses d'habitude). Comptes pris par défaut :
                  comptes courants et PayPal.
                </>
              }
              controls={
                <div className="space-y-2">
                  <LayerToggles show={show} setShow={setShow} />
                  <Legend
                    items={[
                      { label: "Charges fixes seulement", color: LAYER_COLORS.fixe, dashed: true },
                      ...(show.essentiel && show.plaisir ? [{ label: "+ essentiels", color: LAYER_COLORS.essentiel }] : []),
                      { label: "Solde prévu", color: ACCENT },
                      ...(active ? [{ label: "sans scénario", color: "#94a3b8", dashed: true }] : []),
                    ]}
                  />
                </div>
              }
            >
              <TreasuryChart points={f.points} start={f.start_balance_cents} events={f.events} show={show} showBaseline={active} />
            </ChartFrame>
          </section>
          <div className="grid gap-4 lg:grid-cols-3">
          <section className="card space-y-2">
            <h2 className="section-title">📅 Échéances d'ici le {shortDate(f.horizon)}</h2>
            <ul className="divide-y divide-slate-100 text-sm dark:divide-white/5">
              {f.events.map((e, i) => (
                <li key={i} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="truncate font-medium">
                      <span aria-hidden className={e.amount_cents > 0 ? "text-emerald-600" : "muted"}>{KIND_ICONS[e.kind]}</span> {e.label}
                      {e.status === "suggere" && <span className="chip ml-2 bg-slate-100 text-[11px] dark:bg-white/10">à confirmer</span>}
                      {e.status === "tendance" && <span className="chip ml-2 bg-slate-100 text-[11px] dark:bg-white/10">d'habitude</span>}
                    </p>
                    <p className="muted text-xs">{e.late ? "attendu (en retard)" : fmtLong(e.date)}{e.account_name ? ` · ${e.account_name}` : ""}</p>
                  </div>
                  <span className={`shrink-0 font-semibold tabular-nums ${e.amount_cents > 0 ? "text-emerald-600 dark:text-emerald-400" : ""}`}>{formatCents(e.amount_cents)}</span>
                </li>
              ))}
              {f.events.length === 0 && <li className="muted py-2">Aucune échéance connue : confirme ou ajoute tes récurrents dans l'onglet 🔁 Récurrents.</li>}
            </ul>
          </section>
          <LayerList layer="essentiel" title="🛒 Essentiels prévus" cats={f.categories} sc={sc} setSc={setSc} />
          <LayerList layer="plaisir" title="🎉 Plaisirs prévus" cats={f.categories} sc={sc} setSc={setSc} />
          </div>
        </>
      )}
    </div>
  );
}

/** Explications repliées derrière un petit « ? ». */
function Help({ children }: { children: ReactNode }) {
  return (
    <details className="group text-xs">
      <summary className="muted inline-flex cursor-pointer list-none items-center gap-1 rounded-lg px-1.5 py-0.5 hover:bg-slate-100 dark:hover:bg-white/10">
        <span className="grid h-4 w-4 place-items-center rounded-full border border-current text-[10px]">?</span> Comment ça marche
      </summary>
      <div className="muted mt-1 rounded-xl bg-slate-50 p-3 dark:bg-white/5">{children}</div>
    </details>
  );
}

/** Essentiels ou plaisirs prévus d'ici l'horizon, par catégorie. Toucher une catégorie la retire des prévisions
 *  (graphique, totaux, projection) ; la toucher à nouveau la remet. */
function LayerList({
  layer,
  title,
  cats,
  sc,
  setSc,
}: {
  layer: Nature;
  title: string;
  cats: ForecastCategory[];
  sc: ScenarioState;
  setSc: (s: ScenarioState) => void;
}) {
  const { byId, pathOf } = useCategories();
  const [open, setOpen] = useState<Set<number | null>>(new Set());
  const off = new Set(sc.off);
  const items = cats.filter((c) => c.layer === layer && c.base_amount_cents > 0);
  const groups = new Map<number | null, ForecastCategory[]>();
  for (const c of items) {
    const top = c.category_id === null ? null : byId.get(c.category_id)?.parent_id ?? c.category_id;
    groups.set(top, [...(groups.get(top) ?? []), c]);
  }
  const shown = (c: ForecastCategory) => (c.category_id !== null && off.has(c.category_id) ? 0 : c.amount_cents);
  const sorted = [...groups.entries()].sort((a, b) => b[1].reduce((s, c) => s + c.base_amount_cents, 0) - a[1].reduce((s, c) => s + c.base_amount_cents, 0));
  const total = items.reduce((s, c) => s + shown(c), 0);
  const setOff = (ids: number[], value: boolean) => {
    const next = new Set(sc.off);
    for (const id of ids) {
      if (value) next.add(id);
      else next.delete(id);
    }
    setSc({ ...sc, off: [...next] });
  };
  const layerOff = items.filter((c) => c.category_id !== null && off.has(c.category_id)).map((c) => c.category_id as number);
  const row = "flex w-full items-center gap-2 rounded-lg px-1 py-1.5 text-left transition hover:bg-slate-50 dark:hover:bg-white/5";

  return (
    <section className="card space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="section-title">{title}</h2>
        <span className="font-semibold tabular-nums">{formatCents(-total)}</span>
      </div>
      <p className="muted flex items-center justify-between gap-2 text-xs">
        <span>Touche une catégorie pour la retirer</span>
        {layerOff.length > 0 && (
          <button className="font-medium text-accent-600 hover:underline dark:text-accent-300" onClick={() => setOff(layerOff, false)}>
            ↺ tout remettre
          </button>
        )}
      </p>
      <ul className="text-sm">
        {sorted.map(([top, list]) => {
          const ids = list.map((c) => c.category_id).filter((id): id is number => id !== null);
          const allOff = ids.length > 0 && ids.every((id) => off.has(id));
          const sum = list.reduce((s, c) => s + shown(c), 0);
          const base = list.reduce((s, c) => s + c.base_amount_cents, 0);
          const expandable = list.length > 1 || (list[0].category_id !== null && list[0].category_id !== top);
          return (
            <li key={top ?? 0}>
              <div className="flex items-center gap-1">
                <button
                  className="muted w-5 shrink-0 text-xs"
                  onClick={() => {
                    const next = new Set(open);
                    if (next.has(top)) next.delete(top);
                    else next.add(top);
                    setOpen(next);
                  }}
                  aria-label="Détail"
                  disabled={!expandable}
                >
                  {expandable ? (open.has(top) ? "▾" : "▸") : ""}
                </button>
                <button className={`${row} ${allOff ? "opacity-45" : ""}`} disabled={!ids.length} aria-pressed={!allOff} onClick={() => setOff(ids, !allOff)}>
                  <CategoryIcon id={top} size="sm" />
                  <span className={`min-w-0 flex-1 truncate ${allOff ? "line-through" : ""}`}>{top === null ? "À catégoriser" : pathOf(top)}</span>
                  <span className={`shrink-0 tabular-nums ${allOff ? "line-through" : ""}`}>{formatCents(-(allOff ? base : sum))}</span>
                </button>
              </div>
              {expandable && open.has(top) && (
                <ul className="mb-1 ml-7 border-l border-slate-100 pl-2 text-xs dark:border-white/10">
                  {list.map((c) => {
                    const isOff = c.category_id !== null && off.has(c.category_id);
                    return (
                      <li key={c.category_id ?? 0}>
                        <button className={`${row} ${isOff ? "opacity-45" : ""}`} disabled={c.category_id === null} aria-pressed={!isOff} onClick={() => c.category_id !== null && setOff([c.category_id], !isOff)}>
                          <span className={`min-w-0 flex-1 truncate ${isOff ? "line-through" : ""}`}>
                            {c.category_id === null ? "À catégoriser" : c.category_id === top ? "(sans sous-catégorie)" : byId.get(c.category_id)?.name}
                          </span>
                          <span className="muted shrink-0 tabular-nums">≈ {formatCents(c.monthly_cents)}/mois {ARROWS[c.direction]}</span>
                          <span className={`w-20 shrink-0 text-right tabular-nums ${isOff ? "line-through" : ""}`}>{formatCents(-(isOff ? c.base_amount_cents : c.amount_cents))}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
        {sorted.length === 0 && <li className="muted py-1.5">Rien de prévu d'ici là.</li>}
      </ul>
    </section>
  );
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: "bad" }) {
  return (
    <div className="card space-y-0.5 p-3">
      <p className="muted text-xs">{label}</p>
      <p className={`text-lg font-bold tabular-nums ${tone === "bad" ? "text-rose-600" : ""}`}>{value}</p>
      {sub && <p className="muted text-xs">{sub}</p>}
    </div>
  );
}

// --- Projection ---------------------------------------------------------------------------------

const monthShort = new Intl.DateTimeFormat("fr-FR", { month: "short" });
const monthLabel = (key: string) => {
  const d = new Date(`${key}-01T12:00:00`);
  const m = monthShort.format(d).replace(".", "");
  return (m.charAt(0).toUpperCase() + m.slice(1)) + (key.endsWith("-01") ? ` ${key.slice(2, 4)}` : "");
};

function ProjectionPage({ sc, setSc }: { sc: ScenarioState; setSc: (s: ScenarioState) => void }) {
  const [months, setMonths] = useState(12);
  const [until, setUntil] = useState("");
  const [p, setP] = useState<Projection | null>(null);
  const [error, setError] = useState<string | null>(null);
  const acc = useAccountsChoice(p?.account_ids);
  const body = JSON.stringify(scenarioBody(sc));

  useEffect(() => {
    const t = setTimeout(() => {
      const params = new URLSearchParams(until ? { until } : { months: String(months) });
      if (acc.chosen) params.set("accounts", acc.chosen.join(","));
      api.post<Projection>(`/projection?${params}`, JSON.parse(body)).then((r) => {
        setP(r);
        setError(null);
      }, (e) => setError((e as Error).message));
    }, 250);
    return () => clearTimeout(t);
  }, [months, until, acc.chosen?.join(","), body]); // eslint-disable-line react-hooks/exhaustive-deps

  const active = p?.scenario.active ?? false;
  const model = p?.model;
  const nextMonth = isoDate(new Date(new Date().getFullYear(), new Date().getMonth() + 2, 1)).slice(0, 7);

  return (
    <div className="space-y-4">
      <section className="card space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          {[3, 6, 12, 24, 36].map((n) => (
            <button key={n} className={`chip px-3 py-1 text-sm ${!until && months === n ? "bg-accent-600 text-white" : "bg-slate-100 dark:bg-white/5"}`} onClick={() => { setMonths(n); setUntil(""); }}>
              {n} mois
            </button>
          ))}
          <label className={`chip gap-2 px-3 py-1 text-sm ${until ? "bg-accent-600 text-white" : "bg-slate-100 dark:bg-white/5"}`}>
            Jusqu'à
            <input type="month" className="bg-transparent text-sm outline-none" value={until} min={nextMonth} onChange={(e) => setUntil(e.target.value)} />
          </label>
        </div>
        <AccountChips selected={acc.selected} onToggle={acc.toggle} />
      </section>

      <ScenarioPanel sc={sc} setSc={setSc} model={model ?? null} />

      {error && <p className="text-sm text-red-600">{error}</p>}
      {p && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat
              label={`Solde fin ${monthLabel(p.months[p.months.length - 1]?.month ?? "")}`}
              value={formatCents(p.end_balance_cents)}
              sub={active ? `${p.end_balance_cents >= p.baseline_end_cents ? "+" : ""}${formatCents(p.end_balance_cents - p.baseline_end_cents)} grâce au scénario` : `aujourd'hui ${formatCents(p.start_balance_cents)}`}
              tone={p.end_balance_cents < 0 ? "bad" : undefined}
            />
            <Stat label="Reste chaque mois" value={formatCents(p.avg_net_cents)} sub="revenus − toutes les dépenses − épargne" tone={p.avg_net_cents < 0 ? "bad" : undefined} />
            <Stat label="Épargne programmée" value={`${formatCents(p.avg_saving_cents)} / mois`} sub="virements réguliers + en plus" />
            <Stat
              label="Mois le plus serré"
              value={p.lowest ? formatCents(p.lowest.balance_cents) : "—"}
              sub={p.lowest ? `fin ${monthLabel(p.lowest.month)}` : undefined}
              tone={p.lowest && p.lowest.balance_cents < 0 ? "bad" : undefined}
            />
          </div>
          {p.first_negative_month && (
            <p className="card border-rose-200 bg-rose-50 text-sm font-medium text-rose-700 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300">
              ⚠️ À ce rythme, le solde passe sous zéro fin {monthLabel(p.first_negative_month)}.
            </p>
          )}

          <section className="card space-y-3">
            <ChartFrame
              title="Entrées et sorties prévues, mois par mois"
              help="Barres : ce qui sort (le mois en cours, plus pâle, ne compte que ce qui reste à venir). Trait : les revenus attendus."
              controls={
                <Legend
                  items={[
                    { label: "Revenus", color: "currentColor" },
                    { label: NATURE_LABELS.fixe, color: LAYER_COLORS.fixe },
                    { label: NATURE_LABELS.essentiel, color: LAYER_COLORS.essentiel },
                    { label: NATURE_LABELS.plaisir, color: LAYER_COLORS.plaisir },
                    { label: "Épargne", color: LAYER_COLORS.epargne },
                  ]}
                />
              }
            >
              <ProjectionBars
                data={p.months.map((m) => ({
                  key: m.month, label: monthLabel(m.month), income: m.income_cents, fixe: m.fixe_cents, essentiel: m.essentiel_cents,
                  plaisir: m.plaisir_cents, epargne: m.epargne_cents, net: m.net_cents, partial: m.partial,
                }))}
              />
            </ChartFrame>
          </section>

          <section className="card space-y-2">
            <ChartFrame title={`Solde prévu en fin de mois${active ? " (avec le scénario)" : ""}`}>
              <LineChart label="Solde prévu en fin de mois" points={p.months.map((m) => ({ label: monthLabel(m.month), value: m.end_balance_cents }))} />
            </ChartFrame>
          </section>

          <section className="card space-y-2 overflow-x-auto">
            <h2 className="section-title">Le détail</h2>
            <table className="w-full min-w-[640px] text-right text-sm tabular-nums">
              <thead className="muted text-xs">
                <tr>
                  <th className="py-1 text-left font-medium">Mois</th>
                  <th className="font-medium">Revenus</th>
                  <th className="font-medium">Fixes</th>
                  <th className="font-medium">Essentiels</th>
                  <th className="font-medium">Plaisirs</th>
                  <th className="font-medium">Épargne</th>
                  <th className="font-medium">Reste</th>
                  <th className="font-medium">Solde fin</th>
                  {active && <th className="font-medium">Sans scénario</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                {p.months.map((m) => (
                  <tr key={m.month} className={m.partial ? "muted" : ""}>
                    <td className="py-1.5 text-left">{monthLabel(m.month)}{m.partial ? " (reste)" : ""}</td>
                    <td className="text-emerald-700 dark:text-emerald-400">{formatCents(m.income_cents)}</td>
                    <td>{formatCents(-m.fixe_cents)}</td>
                    <td>{formatCents(-m.essentiel_cents)}</td>
                    <td>{formatCents(-m.plaisir_cents)}</td>
                    <td>{formatCents(-m.epargne_cents)}</td>
                    <td className={m.net_cents < 0 ? "text-rose-600" : "font-medium"}>{formatCents(m.net_cents)}</td>
                    <td className={m.end_balance_cents < 0 ? "font-semibold text-rose-600" : "font-semibold"}>{formatCents(m.end_balance_cents)}</td>
                    {active && <td className="muted">{formatCents(m.baseline_end_cents)}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {model && (
            <section className="card space-y-2">
              <h2 className="section-title">Sur quoi repose la projection</h2>
              <ul className="space-y-1 text-sm">
                <li>💶 Revenus : tes revenus récurrents (salaire…) à leur date{model.other_income_cents > 0 && ` + ${formatCents(model.other_income_cents)} / mois d'autres revenus habituels`}.</li>
                {NATURES.map((n) => (
                  <li key={n}>
                    <span className="mr-1 inline-block h-2.5 w-2.5 rounded" style={{ background: LAYER_COLORS[n] }} />
                    {NATURE_LABELS[n]} : {n === "fixe" ? "tes récurrents à leur date (les annuels tombent le bon mois)" : "ta tendance"}
                    {model.layers[n].trend_cents > 0 && ` + ${formatCents(model.layers[n].trend_cents)} / mois`}
                    {n !== "fixe" && " (répartis selon tes habitudes)"}
                    {model.layers[n].scenario_cents !== model.layers[n].trend_cents && `, ici ${formatCents(model.layers[n].scenario_cents)}`}.
                  </li>
                ))}
              </ul>
              <p className="muted text-xs">
                Tendances calculées sur {model.months_used} mois (les plus récents comptent plus, un mois exceptionnel est écrêté) : elles
                s'affinent chaque mois. Comptes : {p.accounts.join(", ")}. Les récurrents à confirmer sont comptés : valide-les dans 🔁 Récurrents.
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}

// --- Budgets ------------------------------------------------------------------------------------

const monthFmt = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" });
const shiftMonth = (key: string, delta: number) => {
  const [y, m] = key.split("-").map(Number);
  const d = new Date(y, m - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
};

function Budgets() {
  const { pathOf, byId } = useCategories();
  const current = isoDate(new Date()).slice(0, 7);
  const [month, setMonth] = useState(current);
  const [b, setB] = useState<BudgetsOverview | null>(null);
  const [newCat, setNewCat] = useState<number | null>(null);
  const [newAmount, setNewAmount] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => api.get<BudgetsOverview>(`/budgets?month=${month}`).then(setB);
  useEffect(() => {
    load();
  }, [month]); // eslint-disable-line react-hooks/exhaustive-deps

  const save = async (categoryId: number, cents: number, threshold = 80) => {
    try {
      await api.put(`/budgets/${categoryId}`, { monthly_amount_cents: cents, alert_threshold_pct: threshold });
      setMsg(null);
      await load();
    } catch (e) {
      setMsg((e as Error).message);
    }
  };
  const add = async (e: FormEvent) => {
    e.preventDefault();
    const cents = parseEuros(newAmount);
    if (newCat === null || !cents || cents <= 0) return setMsg("Choisis une catégorie et un montant.");
    await save(newCat, cents);
    setNewCat(null);
    setNewAmount("");
  };
  const budgeted = new Set(b?.items.map((i) => i.category_id));
  const nonExpense = useMemo(() => [...byId.values()].filter((c) => c.kind !== "depense").map((c) => c.id), [byId]);
  const name = (d: string) => monthFmt.format(new Date(`${d}-01T12:00:00`));

  return (
    <div className="space-y-4">
      <section className="card flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-1">
          <button className="btn-ghost px-2" onClick={() => setMonth(shiftMonth(month, -1))} aria-label="Mois précédent">‹</button>
          <span className="min-w-[9rem] text-center font-semibold capitalize">{name(month)}</span>
          <button className="btn-ghost px-2" onClick={() => setMonth(shiftMonth(month, 1))} disabled={month >= current} aria-label="Mois suivant">›</button>
          {month !== current && <button className="btn-ghost text-xs" onClick={() => setMonth(current)}>↺ Mois en cours</button>}
        </div>
        {b && b.items.length > 0 && (
          <p className="text-sm tabular-nums">
            <b>{formatCents(b.total_spent_cents)}</b> <span className="muted">sur {formatCents(b.total_budget_cents)}</span>
            {b.is_current && <span className="muted"> · fin de mois ≈ {formatCents(b.total_projected_cents)}</span>}
          </p>
        )}
      </section>

      {b && b.items.length > 0 && (
        <section className="card space-y-4">
          {b.is_current && (
            <p className="muted text-xs">
              Jour {b.elapsed_days} sur {b.days_in_month}. Le petit trait indique où tu devrais en être à cette date ; la
              projection de fin de mois ajoute les prélèvements encore attendus et ta tendance habituelle pour les jours restants.
              Pour voir l'effet de tes budgets sur ton solde : 🔮 Trésorerie ou 📈 Projection › « Je respecte mes budgets ».
            </p>
          )}
          <ul className="space-y-4">
            {b.items.map((it) => (
              <BudgetRow key={it.category_id} item={it} label={pathOf(it.category_id)} current={b.is_current} onSave={save} onDelete={async () => {
                await api.del(`/budgets/${it.category_id}`);
                load();
              }} />
            ))}
          </ul>
        </section>
      )}

      <section className="card space-y-3">
        <h2 className="section-title">Nouveau budget</h2>
        <form className="flex flex-wrap items-end gap-2" onSubmit={add}>
          <div className="min-w-[14rem] flex-1">
            <CategorySelect value={newCat} onChange={setNewCat} emptyLabel="— Catégorie de dépenses —" exclude={[...nonExpense, ...budgeted]} />
          </div>
          <input className="input w-32" inputMode="decimal" placeholder="€ / mois" value={newAmount} onChange={(e) => setNewAmount(e.target.value)} />
          <button className="btn" type="submit">Ajouter</button>
        </form>
        <p className="muted text-xs">Un budget sur une catégorie principale compte aussi ses sous-catégories. Alerte à 80 % (réglable).</p>
        {msg && <p className="text-sm text-red-600">{msg}</p>}
      </section>

      {b && b.suggestions.length > 0 && (
        <section className="card space-y-2">
          <h2 className="section-title">💡 Suggestions d'après tes 3 derniers mois</h2>
          <ul className="divide-y divide-slate-100 text-sm dark:divide-white/5">
            {b.suggestions.map((s) => (
              <li key={s.category_id} className="flex items-center justify-between gap-3 py-2">
                <span className="flex min-w-0 items-center gap-2">
                  <CategoryIcon id={s.category_id} size="sm" />
                  <span className="truncate">{pathOf(s.category_id)}</span>
                  <span className="muted shrink-0 text-xs">moyenne {formatCents(s.average_cents)}</span>
                </span>
                <button className="btn-ghost shrink-0 text-sm" onClick={() => save(s.category_id, s.suggested_cents)}>
                  + {formatCents(s.suggested_cents)} / mois
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function BudgetRow({
  item,
  label,
  current,
  onSave,
  onDelete,
}: {
  item: BudgetItem;
  label: string;
  current: boolean;
  onSave: (id: number, cents: number, threshold: number) => Promise<void>;
  onDelete: () => void;
}) {
  const [edit, setEdit] = useState(false);
  const [amount, setAmount] = useState(String(item.budget_cents / 100).replace(".", ","));
  const [threshold, setThreshold] = useState(item.alert_threshold_pct);
  const lv = LEVELS[item.level];
  return (
    <li className="space-y-1.5">
      <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
        <button className="flex min-w-0 items-center gap-2 text-left" onClick={() => setEdit(!edit)} title="Modifier">
          <CategoryIcon id={item.category_id} size="sm" />
          <span className="truncate font-medium">{label}</span>
        </button>
        <span className="tabular-nums">
          <span className={`font-semibold ${lv.text}`}>{formatCents(item.spent_cents)}</span>
          <span className="muted"> / {formatCents(item.budget_cents)}</span>
          <span className="ml-2 text-xs">{lv.icon} {lv.label}</span>
        </span>
      </div>
      <BudgetBar item={item} showPace={current} />
      <p className="muted text-xs">
        {item.remaining_cents >= 0 ? `Reste ${formatCents(item.remaining_cents)}` : `Dépassé de ${formatCents(-item.remaining_cents)}`}
        {current && ` · fin de mois ≈ ${formatCents(item.projected_cents)}`}
        {current && item.expected_recurring_cents > 0 && ` (dont ${formatCents(item.expected_recurring_cents)} de prélèvements à venir)`}
        {item.trend_cents > 0 && ` · d'habitude ≈ ${formatCents(item.trend_cents)} / mois`}
      </p>
      {edit && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 p-2 dark:bg-white/5">
          <input className="input w-28" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Budget mensuel" />
          <label className="muted flex items-center gap-1 text-xs">
            alerte à
            <select className="input w-20 py-1" value={threshold} onChange={(e) => setThreshold(Number(e.target.value))}>
              {[50, 70, 80, 90, 100].map((v) => <option key={v} value={v}>{v} %</option>)}
            </select>
          </label>
          <button
            className="btn"
            onClick={async () => {
              const cents = parseEuros(amount);
              if (cents && cents > 0) {
                await onSave(item.category_id, cents, threshold);
                setEdit(false);
              }
            }}
          >
            Enregistrer
          </button>
          <button className="btn-ghost text-red-600" onClick={onDelete}>Supprimer</button>
        </div>
      )}
    </li>
  );
}

// --- Récurrents ---------------------------------------------------------------------------------

const KIND_TITLES: Record<Recurring["kind"], string> = {
  depense: "Abonnements et prélèvements",
  revenu: "Revenus réguliers",
  virement: "Virements programmés",
};

function RecurringPage() {
  const [data, setData] = useState<RecurringSummary | null>(null);
  const [archived, setArchived] = useState<Recurring[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = async () => {
    setData(await api.get<RecurringSummary>("/recurring"));
    if (archived) setArchived((await api.get<RecurringSummary>("/recurring?all=true")).items.filter((i) => i.status === "termine" || i.status === "ignore"));
  };
  useEffect(() => {
    load();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = async () => {
    setBusy(true);
    try {
      const r = await api.post<{ created: number }>("/recurring/refresh");
      setMsg(r.created ? `${r.created} nouvelle(s) opération(s) récurrente(s) détectée(s).` : "Rien de nouveau.");
      await load();
    } finally {
      setBusy(false);
    }
  };
  const patch = async (r: Recurring, body: Record<string, unknown>) => {
    await api.patch(`/recurring/${r.id}`, body);
    await load();
  };
  const remove = async (r: Recurring) => {
    const what = r.source === "manuel" ? "Supprimer ce récurrent ?" : "Ce n'est pas un récurrent ? Il ne sera plus proposé.";
    if (!confirm(what)) return;
    await api.del(`/recurring/${r.id}`);
    await load();
  };
  const showArchived = async () => {
    const all = await api.get<RecurringSummary>("/recurring?all=true");
    setArchived(all.items.filter((i) => i.status === "termine" || i.status === "ignore"));
  };

  if (!data) return null;
  const toConfirm = data.items.filter((i) => i.status === "suggere");
  const confirmed = data.items.filter((i) => i.status === "actif");
  const byKind = (k: Recurring["kind"]) => confirmed.filter((i) => i.kind === k);

  return (
    <div className="space-y-4">
      <section className="card flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="muted text-xs">Abonnements et prélèvements</p>
          <p className="text-xl font-bold tabular-nums">
            {formatCents(data.monthly_out_cents)} <span className="muted text-sm font-normal">/ mois · {formatCents(data.yearly_out_cents)} / an</span>
          </p>
          {data.monthly_in_cents > 0 && <p className="muted text-xs">Revenus réguliers : {formatCents(data.monthly_in_cents)} / mois</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={refresh} disabled={busy}>{busy ? "Détection…" : "↻ Relancer la détection"}</button>
          <button className="btn" onClick={() => setAdding(!adding)}>+ Ajouter</button>
        </div>
      </section>
      {msg && <p className="muted text-sm">{msg}</p>}
      {adding && <ManualRecurringForm onDone={() => { setAdding(false); load(); }} />}

      {toConfirm.length > 0 && (
        <section className="card space-y-2 border-accent-200 dark:border-accent-500/20">
          <h2 className="section-title">✨ À confirmer ({toConfirm.length})</h2>
          <p className="muted text-sm">Détectés dans ton historique. Ils comptent déjà dans les prévisions ; confirme-les ou écarte ceux qui n'en sont pas.</p>
          <ul className="divide-y divide-slate-100 dark:divide-white/5">
            {toConfirm.map((r) => (
              <RecurringRow key={r.id} r={r} onPatch={patch} onRemove={remove}>
                <button className="btn-ghost text-sm" onClick={() => patch(r, { status: "actif" })}>✓ Confirmer</button>
                <button className="btn-ghost muted text-sm" onClick={() => remove(r)}>✕ Pas récurrent</button>
              </RecurringRow>
            ))}
          </ul>
        </section>
      )}

      {(["depense", "revenu", "virement"] as const).map((k) =>
        byKind(k).length > 0 ? (
          <section key={k} className="card space-y-2">
            <h2 className="section-title">{KIND_TITLES[k]}</h2>
            <ul className="divide-y divide-slate-100 dark:divide-white/5">
              {byKind(k).map((r) => <RecurringRow key={r.id} r={r} onPatch={patch} onRemove={remove} />)}
            </ul>
          </section>
        ) : null,
      )}
      {confirmed.length === 0 && toConfirm.length === 0 && (
        <p className="card muted text-sm">Aucun récurrent pour l'instant : lance la détection ou ajoute-en un à la main.</p>
      )}

      {archived === null ? (
        <button className="btn-ghost muted text-sm" onClick={showArchived}>Voir les récurrents terminés ou écartés</button>
      ) : (
        <section className="card space-y-2">
          <h2 className="section-title">Terminés et écartés</h2>
          <ul className="divide-y divide-slate-100 dark:divide-white/5">
            {archived.map((r) => (
              <RecurringRow key={r.id} r={r} onPatch={patch} onRemove={remove}>
                <button className="btn-ghost text-sm" onClick={async () => { await patch(r, { status: "actif" }); await showArchived(); }}>Réactiver</button>
              </RecurringRow>
            ))}
            {archived.length === 0 && <li className="muted py-2 text-sm">Aucun.</li>}
          </ul>
        </section>
      )}
    </div>
  );
}

function RecurringRow({
  r,
  onPatch,
  onRemove,
  children,
}: {
  r: Recurring;
  onPatch: (r: Recurring, body: Record<string, unknown>) => Promise<void>;
  onRemove: (r: Recurring) => void;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const since = r.first_date ? new Date(`${r.first_date}T12:00:00`).toLocaleDateString("fr-FR", { month: "short", year: "numeric" }) : null;
  let when = r.next_date ? `prochain : ${shortDate(r.next_date)}` : "";
  if (r.maybe_ended) when = `pas vu depuis le ${r.last_date ? shortDate(r.last_date) : "?"} — résilié ?`;
  else if (r.late_days > 0) when = `attendu le ${shortDate(r.next_date!)} (en retard de ${r.late_days} j)`;
  return (
    <li className="py-2">
      <div className="flex items-center gap-3">
        <CategoryIcon id={r.category_id} size="sm" />
        <button className="min-w-0 flex-1 text-left" onClick={() => setOpen(!open)}>
          <p className="truncate text-sm font-medium">
            {r.label}
            {r.price_increase && r.previous_amount_cents !== null && (
              <span className="chip ml-2 bg-rose-50 text-[11px] text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
                ↑ +{formatCents(Math.abs(r.amount_cents) - Math.abs(r.previous_amount_cents))}
              </span>
            )}
          </p>
          <p className={`text-xs ${r.maybe_ended ? "text-amber-700 dark:text-amber-300" : "muted"}`}>
            {FREQUENCY_LABELS[r.frequency] ?? r.frequency_label} · {when}
            {r.account_name ? ` · ${r.account_name}` : ""}
          </p>
        </button>
        <div className="shrink-0 text-right">
          <p className={`text-sm font-semibold tabular-nums ${r.amount_cents > 0 ? "text-emerald-600 dark:text-emerald-400" : ""}`}>{formatCents(r.amount_cents)}</p>
          {r.frequency !== "mensuel" && <p className="muted text-[11px] tabular-nums">≈ {formatCents(r.monthly_cents)} / mois</p>}
        </div>
      </div>
      {children && <div className="mt-1 flex flex-wrap justify-end gap-1">{children}</div>}
      {open && <RecurringDetail r={r} since={since} onPatch={onPatch} onRemove={onRemove} />}
    </li>
  );
}

function RecurringDetail({
  r,
  since,
  onPatch,
  onRemove,
}: {
  r: Recurring;
  since: string | null;
  onPatch: (r: Recurring, body: Record<string, unknown>) => Promise<void>;
  onRemove: (r: Recurring) => void;
}) {
  const [txs, setTxs] = useState<{ id: number; booked_at: string; amount_cents: number }[]>([]);
  const [label, setLabel] = useState(r.label);
  const [amount, setAmount] = useState(String(Math.abs(r.amount_cents) / 100).replace(".", ","));
  const [freq, setFreq] = useState<Frequency>(r.frequency);
  const [next, setNext] = useState(r.next_date ?? "");
  const [cat, setCat] = useState<number | null>(r.category_id);
  useEffect(() => {
    api.get<typeof txs>(`/recurring/${r.id}/transactions`).then(setTxs);
  }, [r.id]);
  const save = () => {
    const cents = parseEuros(amount);
    onPatch(r, {
      label,
      frequency: freq,
      category_id: cat,
      ...(cents ? { amount_cents: r.amount_cents < 0 ? -Math.abs(cents) : Math.abs(cents) } : {}),
      ...(next ? { next_date: next } : {}),
    });
  };
  return (
    <div className="mt-2 space-y-3 rounded-xl bg-slate-50 p-3 text-sm dark:bg-white/5">
      {r.occurrences > 0 && (
        <p className="muted text-xs">
          {r.occurrences} fois{since ? ` depuis ${since}` : ""} · total {formatCents(r.total_cents)} · {formatCents(r.yearly_cents)} / an
          {r.previous_amount_cents !== null && r.price_changed_on && ` · ${formatCents(r.previous_amount_cents)} avant le ${shortDate(r.price_changed_on)}`}
        </p>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} aria-label="Nom" />
        <input className="input" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} aria-label="Montant" />
        <select className="input" value={freq} onChange={(e) => setFreq(e.target.value as Frequency)}>
          {Object.entries(FREQUENCY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input className="input" type="date" value={next} onChange={(e) => setNext(e.target.value)} aria-label="Prochaine échéance" />
        <div className="sm:col-span-2">
          <CategorySelect value={cat} onChange={setCat} />
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <button className="btn" onClick={save}>Enregistrer</button>
        {r.status !== "termine" && <button className="btn-ghost" onClick={() => onPatch(r, { status: "termine" })}>Résilié / terminé</button>}
        <button className="btn-ghost text-red-600" onClick={() => onRemove(r)}>{r.source === "manuel" ? "Supprimer" : "Pas récurrent"}</button>
      </div>
      {txs.length > 0 && (
        <ul className="muted space-y-0.5 text-xs">
          {txs.slice(0, 12).map((t) => (
            <li key={t.id} className="flex justify-between tabular-nums">
              <span>{new Date(`${t.booked_at}T12:00:00`).toLocaleDateString("fr-FR")}</span>
              <span>{formatCents(t.amount_cents)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ManualRecurringForm({ onDone }: { onDone: () => void }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [sign, setSign] = useState<-1 | 1>(-1);
  const [freq, setFreq] = useState<Frequency>("mensuel");
  const [next, setNext] = useState(isoDate(new Date()));
  const [account, setAccount] = useState<number | null>(null);
  const [cat, setCat] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.get<Account[]>("/accounts").then((list) => {
      const open = list.filter((a) => !a.is_archived);
      setAccounts(open);
      setAccount(open.find((a) => a.type === "courant")?.id ?? open[0]?.id ?? null);
    });
  }, []);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const cents = parseEuros(amount);
    if (!label.trim() || !cents || account === null) return setError("Nom, montant et compte sont nécessaires.");
    try {
      await api.post("/recurring", { label, amount_cents: sign * Math.abs(cents), frequency: freq, next_date: next, account_id: account, category_id: cat });
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <form className="card space-y-3" onSubmit={submit}>
      <h2 className="section-title">Nouveau récurrent</h2>
      <p className="muted text-xs">Pour ce qui n'est pas encore dans ton historique (assurance annuelle, nouvel abonnement, impôts…).</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <input className="input" placeholder="Nom (ex. Assurance auto)" value={label} onChange={(e) => setLabel(e.target.value)} />
        <div className="flex gap-2">
          <select className="input w-32" value={sign} onChange={(e) => setSign(Number(e.target.value) as -1 | 1)}>
            <option value={-1}>Dépense</option>
            <option value={1}>Revenu</option>
          </select>
          <input className="input flex-1" inputMode="decimal" placeholder="Montant €" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </div>
        <select className="input" value={freq} onChange={(e) => setFreq(e.target.value as Frequency)}>
          {Object.entries(FREQUENCY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <label className="flex items-center gap-2 text-sm">
          <span className="muted shrink-0">Prochaine échéance</span>
          <input className="input" type="date" value={next} onChange={(e) => setNext(e.target.value)} />
        </label>
        <select className="input" value={account ?? ""} onChange={(e) => setAccount(Number(e.target.value))}>
          {accounts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
        </select>
        <CategorySelect value={cat} onChange={setCat} />
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button className="btn" type="submit">Ajouter</button>
        <button className="btn-ghost" type="button" onClick={onDone}>Annuler</button>
      </div>
    </form>
  );
}
