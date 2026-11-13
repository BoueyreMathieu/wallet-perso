/** Petits graphiques SVG sans dépendance (donut, barres mensuelles, courbes cumulées, sparkline).
 *  Règles : traits fins, extrémités arrondies, un seul axe, légende dès 2 séries,
 *  textes en couleurs de texte (jamais la couleur de la série), info-bulle au survol. */
import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { formatCents } from "../format";
import { isNative } from "../native";

const compact = new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 });
export const compactEuros = (cents: number) => `${compact.format(cents / 100)} €`;

export const INCOME_COLOR = "#10b981";
export const SPENT_COLOR = "#f43f5e";
export const ACCENT = "#7552f5";
export const MUTED_LINE = "#94a3b8";

function niceMax(v: number): number {
  if (v <= 0) return 100;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  for (const m of [1, 2, 2.5, 5, 10]) if (m * p >= v) return m * p;
  return 10 * p;
}

function Tooltip({ x, y, children }: { x: number; y: number; children: ReactNode }) {
  // x, y en % de la zone du graphique
  const left = Math.min(Math.max(x, 12), 88);
  return (
    <div
      className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-xl bg-slate-900 px-3 py-2 text-xs text-white shadow-lg dark:bg-slate-700"
      style={{ left: `${left}%`, top: `${y}%` }}
    >
      {children}
    </div>
  );
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="flex flex-wrap gap-3 text-xs muted">
      {items.map((i) => (
        <span key={i.label} className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded" style={{ background: i.dashed ? `repeating-linear-gradient(90deg, ${i.color} 0 3px, transparent 3px 5px)` : i.color, height: 3 }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}

// --- Taille réelle et plein écran ---------------------------------------------------------

/** Hauteur disponible quand le graphique est affiché en plein écran (null sinon). */
const FullHeight = createContext<number | null>(null);

/** Largeur réelle du conteneur (le dessin se fait en pixels réels : textes lisibles même sur téléphone)
 *  et hauteur (celle par défaut, ou toute la hauteur disponible en plein écran). */
function useChartBox(defaultH: number) {
  const [el, ref] = useState<HTMLDivElement | null>(null);
  const [w, setW] = useState(640);
  const full = useContext(FullHeight);
  useEffect(() => {
    if (!el) return;
    const update = () => el.clientWidth > 0 && setW(el.clientWidth);
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [el]);
  return { ref, W: Math.max(280, w), H: full ?? defaultH, full: full !== null };
}

/** Nombre d'étiquettes qui tiennent sur l'axe horizontal (une tous les `k` points). */
const labelEvery = (n: number, plotWidth: number, minGap = 46) => Math.max(1, Math.ceil(n / Math.max(2, Math.floor(plotWidth / minGap))));

/** Cadre d'un graphique : titre, bouton « ? » (explications repliées) et bouton plein écran.
 *  En plein écran, `controls` (pastilles, légende…) restent accessibles en haut. */
export function ChartFrame({
  title,
  help,
  controls,
  children,
}: {
  title?: ReactNode;
  help?: ReactNode;
  controls?: ReactNode;
  children: ReactNode;
}) {
  const [full, setFull] = useState(false);
  const [showHelp, setShowHelp] = useState(false);
  const [box, setBox] = useState<HTMLDivElement | null>(null);
  const [height, setHeight] = useState<number | null>(null);
  const [portrait, setPortrait] = useState(false);
  const [inline, setInline] = useState<HTMLDivElement | null>(null);
  const [placeholder, setPlaceholder] = useState(0);

  useEffect(() => {
    if (!box) return;
    const update = () => {
      setHeight(Math.max(160, box.clientHeight));
      setPortrait(window.innerHeight > window.innerWidth && window.innerWidth < 640);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(box);
    return () => ro.disconnect();
  }, [box]);

  useEffect(() => {
    if (!full) return;
    // Bouton « retour » d'Android / du navigateur : ferme le plein écran au lieu de quitter la page.
    history.pushState({ ...(history.state ?? {}), wpChart: true }, "");
    const onPop = () => setFull(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("popstate", onPop);
    window.addEventListener("keydown", onKey);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("popstate", onPop);
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
    };
  }, [full]); // eslint-disable-line react-hooks/exhaustive-deps

  const open = () => {
    // Le graphique n'est dessiné qu'une fois (dans la fenêtre plein écran) : sa place est gardée sur la page.
    setPlaceholder(inline?.offsetHeight ?? 0);
    setFull(true);
    // Navigateur sur téléphone : vrai plein écran + paysage si possible (l'appli Android suit la rotation du téléphone).
    if (!isNative() && window.matchMedia?.("(pointer: coarse)").matches) {
      const el = document.documentElement as HTMLElement & { requestFullscreen?: () => Promise<void> };
      el.requestFullscreen?.()
        .then(() => (screen.orientation as ScreenOrientation & { lock?: (o: string) => Promise<void> })?.lock?.("landscape"))
        .catch(() => undefined);
    }
  };
  function close() {
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => undefined);
    if (history.state?.wpChart) history.back();
    else setFull(false);
  }

  const btn = "grid h-7 w-7 shrink-0 place-items-center rounded-lg text-sm text-slate-500 transition hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-white/10";
  return (
    <>
      <div className="flex items-start gap-2">
        {title && <h2 className="section-title min-w-0 flex-1">{title}</h2>}
        <div className={`flex shrink-0 gap-1 ${title ? "" : "ml-auto"}`}>
          {help && (
            <button type="button" className={`${btn} ${showHelp ? "bg-slate-100 dark:bg-white/10" : ""}`} onClick={() => setShowHelp(!showHelp)} aria-label="Comment lire ce graphique" aria-pressed={showHelp}>
              ?
            </button>
          )}
          <button type="button" className={btn} onClick={open} aria-label="Plein écran" title="Plein écran">
            ⛶
          </button>
        </div>
      </div>
      {showHelp && <div className="muted rounded-xl bg-slate-50 p-3 text-xs dark:bg-white/5">{help}</div>}
      {!full && controls}
      {full ? <div style={{ height: placeholder }} /> : <div ref={setInline}>{children}</div>}
      {full &&
        createPortal(
          <div
            className="fixed inset-0 z-[80] flex flex-col gap-2 bg-panel p-3 dark:bg-panel-dark sm:p-6"
            style={{ paddingTop: "max(0.75rem, env(safe-area-inset-top))", paddingBottom: "max(0.75rem, env(safe-area-inset-bottom))" }}
            role="dialog"
            aria-modal="true"
          >
            <div className="flex flex-wrap items-center gap-2">
              {title && <h2 className="section-title min-w-0 flex-1 truncate">{title}</h2>}
              {portrait && <span className="muted text-xs">↻ tourne le téléphone</span>}
              <button type="button" className={`${btn} ml-auto h-9 w-9 text-base`} onClick={close} aria-label="Fermer le plein écran">
                ✕
              </button>
            </div>
            {controls}
            <div ref={setBox} className="min-h-0 flex-1 overflow-hidden">
              {height !== null && <FullHeight.Provider value={height}>{children}</FullHeight.Provider>}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

// --- Donut -----------------------------------------------------------------------------

export interface Slice {
  key: string;
  label: string;
  value: number;
  color: string;
  icon?: string;
}

export function Donut({
  slices,
  center,
  active,
  onActive,
  onSelect,
}: {
  slices: Slice[];
  center: ReactNode;
  active: string | null;
  onActive: (key: string | null) => void;
  onSelect?: (key: string) => void;
}) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  const r = 70;
  const circ = 2 * Math.PI * r;
  const gap = slices.length > 1 ? 3 : 0;
  let offset = 0;
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[220px]">
      <svg viewBox="0 0 180 180" className="h-full w-full -rotate-90" role="img" aria-label="Répartition des dépenses par catégorie">
        <circle cx="90" cy="90" r={r} fill="none" strokeWidth="18" className="stroke-slate-100 dark:stroke-white/5" />
        {total > 0 &&
          slices.map((s) => {
            const len = (s.value / total) * circ;
            const dash = Math.max(len - gap, 0.5);
            const el = (
              <circle
                key={s.key}
                cx="90"
                cy="90"
                r={r}
                fill="none"
                stroke={s.color}
                strokeWidth={active === s.key ? 24 : 18}
                strokeDasharray={`${dash} ${circ - dash}`}
                strokeDashoffset={-offset}
                strokeLinecap="butt"
                opacity={active && active !== s.key ? 0.35 : 1}
                className="cursor-pointer transition-all"
                onMouseEnter={() => onActive(s.key)}
                onMouseLeave={() => onActive(null)}
                onClick={() => (onSelect ? onSelect(s.key) : onActive(active === s.key ? null : s.key))}
              />
            );
            offset += len;
            return el;
          })}
      </svg>
      <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">{center}</div>
    </div>
  );
}

// --- Barres revenus / dépenses par mois ---------------------------------------------------

export function MonthBars({
  data,
  onSelect,
  selected,
}: {
  data: { key: string; label: string; income: number; spent: number }[];
  onSelect?: (key: string) => void;
  selected?: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const { ref, W, H } = useChartBox(220);
  const L = 44, B = 24, T = 10;
  const max = niceMax(Math.max(1, ...data.map((d) => Math.max(d.income, d.spent))));
  const every = labelEvery(data.length, W - L, 40);
  const slot = (W - L) / Math.max(data.length, 1);
  const bw = Math.min(14, slot / 3);
  const y = (v: number) => T + (H - T - B) * (1 - v / max);
  const ticks = [0, max / 2, max];
  const h = hover !== null ? data[hover] : null;

  return (
    <div className="relative" ref={ref}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Revenus et dépenses par mois">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W} y1={y(t)} y2={y(t)} className="stroke-slate-200 dark:stroke-white/10" strokeWidth="1" />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" className="fill-slate-400 text-[11px]">{compactEuros(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          const cx = L + slot * i + slot / 2;
          const bar = (v: number, x: number, color: string) => {
            const top = y(v);
            const height = Math.max(H - B - top, v > 0 ? 2 : 0);
            const rr = Math.min(4, height / 2, bw / 2);
            // extrémité arrondie en haut, carrée sur la ligne de base
            const path = `M${x},${H - B} V${top + rr} Q${x},${top} ${x + rr},${top} H${x + bw - rr} Q${x + bw},${top} ${x + bw},${top + rr} V${H - B} Z`;
            return height > 0 ? <path d={path} fill={color} /> : null;
          };
          const isSel = selected === d.key;
          return (
            <g key={d.key} opacity={hover !== null && hover !== i ? 0.5 : 1}>
              {isSel && <rect x={cx - slot / 2 + 2} y={T} width={slot - 4} height={H - B - T} rx="8" className="fill-accent-500/10" />}
              {bar(d.income, cx - bw - 1, INCOME_COLOR)}
              {bar(d.spent, cx + 1, SPENT_COLOR)}
              {(isSel || (data.length - 1 - i) % every === 0) && (
                <text x={cx} y={H - 6} textAnchor="middle" className={`text-[11px] ${isSel ? "fill-slate-700 font-semibold dark:fill-slate-200" : "fill-slate-400"}`}>
                  {d.label}
                </text>
              )}
              {/* Zone cliquable : les barres (et le nom du mois) seulement — au-dessus, on peut faire glisser le graphique. */}
              <rect
                x={cx - Math.max(bw * 2 + 6, 18) / 2}
                y={Math.min(y(Math.max(d.income, d.spent)), H - B - 14) - 4}
                width={Math.max(bw * 2 + 6, 18)}
                height={H - Math.min(y(Math.max(d.income, d.spent)), H - B - 14) + 4}
                fill="transparent"
                className={onSelect ? "cursor-pointer" : ""}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onClick={() => onSelect?.(d.key)}
              />
            </g>
          );
        })}
      </svg>
      {h && hover !== null && (
        <Tooltip x={((L + slot * hover + slot / 2) / W) * 100} y={(y(Math.max(h.income, h.spent)) / H) * 100 - 2}>
          <p className="font-semibold">{h.label}</p>
          <p>Revenus : {formatCents(h.income)}</p>
          <p>Dépenses : {formatCents(h.spent)}</p>
          <p>Solde : {formatCents(h.income - h.spent)}</p>
        </Tooltip>
      )}
    </div>
  );
}

// --- Dépenses cumulées sur le mois (mois choisi vs mois précédent) -------------------------

export function CumulativeChart({
  current,
  previous,
  days,
  height = 200,
  selected = null,
  onSelectDay,
  dayLabel = (i: number) => `Jour ${i + 1}`,
}: {
  current: number[];
  previous: number[];
  days: number;
  height?: number;
  selected?: number | null;
  onSelectDay?: (i: number | null) => void;
  dayLabel?: (i: number) => string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const { ref, W, H } = useChartBox(height);
  const L = 44, B = 22, T = 10, R = 10;
  const n = Math.max(days, previous.length, 1);
  const max = niceMax(Math.max(1, ...current, ...previous));
  const x = (i: number) => L + ((W - L - R) * i) / Math.max(n - 1, 1);
  const y = (v: number) => T + (H - T - B) * (1 - v / max);
  const line = (vals: number[]) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = current.length ? `${line(current)} L${x(current.length - 1)},${H - B} L${x(0)},${H - B} Z` : "";
  const last = current.length - 1;

  return (
    <div className="relative" ref={ref}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="Dépenses cumulées comparées à la période précédente"
        className={`w-full ${onSelectDay ? "cursor-pointer" : ""}`}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - box.left) / box.width) * W;
          const i = Math.round(((px - L) / (W - L - R)) * (n - 1));
          setHover(Math.min(Math.max(i, 0), n - 1));
        }}
        onClick={(e) => {
          if (!onSelectDay) return;
          const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - box.left) / box.width) * W;
          const i = Math.min(Math.max(Math.round(((px - L) / (W - L - R)) * (n - 1)), 0), n - 1);
          onSelectDay(i === selected || i >= current.length ? null : i);
        }}
      >
        {[0, max / 2, max].map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="stroke-slate-200 dark:stroke-white/10" strokeWidth="1" />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" className="fill-slate-400 text-[11px]">{compactEuros(t)}</text>
          </g>
        ))}
        {[1, 10, 20, n].map((d) => (
          <text key={d} x={x(d - 1)} y={H - 4} textAnchor="middle" className="fill-slate-400 text-[11px]">{d}</text>
        ))}
        {previous.length > 0 && (
          <path d={line(previous)} fill="none" stroke={MUTED_LINE} strokeWidth="2" strokeDasharray="4 4" strokeLinecap="round" strokeLinejoin="round" />
        )}
        {area && <path d={area} fill={ACCENT} opacity="0.1" />}
        {current.length > 0 && <path d={line(current)} fill="none" stroke={ACCENT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />}
        {last >= 0 && <circle cx={x(last)} cy={y(current[last])} r="5" fill={ACCENT} className="stroke-panel dark:stroke-panel-dark" strokeWidth="2" />}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} className="stroke-slate-300 dark:stroke-white/20" strokeWidth="1" />}
        {selected !== null && selected < current.length && (
          <g>
            <line x1={x(selected)} x2={x(selected)} y1={T} y2={H - B} stroke={ACCENT} strokeWidth="1.5" />
            <circle cx={x(selected)} cy={y(current[selected])} r="5" fill={ACCENT} className="stroke-panel dark:stroke-panel-dark" strokeWidth="2" />
          </g>
        )}
      </svg>
      {hover !== null && (
        <Tooltip x={(x(hover) / W) * 100} y={(T / H) * 100 + 4}>
          <p className="font-semibold">{dayLabel(hover)}</p>
          {hover < current.length && (
            <p>
              Cumul : {formatCents(current[hover])}
              {current[hover] - (hover > 0 ? current[hover - 1] : 0) > 0 ? ` (+${formatCents(current[hover] - (hover > 0 ? current[hover - 1] : 0))} ce jour)` : ""}
            </p>
          )}
          {hover < previous.length && <p>Période précédente : {formatCents(previous[hover])}</p>}
          {onSelectDay && hover < current.length && <p className="text-white/70">Clic : les dépenses de ce jour</p>}
        </Tooltip>
      )}
    </div>
  );
}

// --- Sparkline (tendance du patrimoine) ----------------------------------------------------

export function Sparkline({ values, color = "#ffffff" }: { values: number[]; color?: string }) {
  if (values.length < 2) return null;
  const W = 120, H = 36;
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const pts = values.map((v, i) => `${((W - 4) * i) / (values.length - 1) + 2},${H - 4 - ((H - 8) * (v - min)) / span}`);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-9 w-28" aria-hidden>
      <polyline points={pts.join(" ")} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" opacity="0.9" />
    </svg>
  );
}

// --- Courbe simple (une série) : patrimoine sur 12 mois ------------------------------------

export function LineChart({ points, color = ACCENT, label }: { points: { label: string; value: number }[]; color?: string; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const { ref, W, H } = useChartBox(200);
  const L = 52, B = 22, T = 12, R = 12;
  if (points.length < 2) return <p className="muted text-sm">Pas encore assez d'historique.</p>;
  const vals = points.map((p) => p.value);
  const lo = Math.min(0, ...vals), hi = niceMax(Math.max(1, ...vals));
  const x = (i: number) => L + ((W - L - R) * i) / (points.length - 1);
  const y = (v: number) => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const last = points.length - 1;
  const every = labelEvery(points.length, W - L - R, 44);
  return (
    <div className="relative" ref={ref}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label={label}
        onMouseLeave={() => setHover(null)}
        onMouseMove={(e) => {
          const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - box.left) / box.width) * W;
          setHover(Math.min(Math.max(Math.round(((px - L) / (W - L - R)) * last), 0), last));
        }}
      >
        {[lo, (lo + hi) / 2, hi].map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="stroke-slate-200 dark:stroke-white/10" strokeWidth="1" />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" className="fill-slate-400 text-[11px]">{compactEuros(t)}</text>
          </g>
        ))}
        {points.map((p, i) => ((last - i) % every === 0 ? <text key={p.label} x={x(i)} y={H - 4} textAnchor="middle" className="fill-slate-400 text-[11px]">{p.label}</text> : null))}
        <path d={`${d} L${x(last)},${y(lo)} L${x(0)},${y(lo)} Z`} fill={color} opacity="0.1" />
        <path d={d} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx={x(hover ?? last)} cy={y(points[hover ?? last].value)} r="5" fill={color} className="stroke-panel dark:stroke-panel-dark" strokeWidth="2" />
      </svg>
      {hover !== null && (
        <Tooltip x={(x(hover) / W) * 100} y={(y(points[hover].value) / H) * 100 - 3}>
          <p className="font-semibold">{points[hover].label}</p>
          <p>{formatCents(points[hover].value)}</p>
        </Tooltip>
      )}
    </div>
  );
}

export interface ForecastPoint {
  date: string; // AAAA-MM-JJ
  balance_cents: number;
}
export interface ForecastEvent {
  date: string;
  label: string;
  amount_cents: number;
  kind: string;
}

const dayShort = new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" });
const dayLong = new Intl.DateTimeFormat("fr-FR", { weekday: "short", day: "numeric", month: "long" });
const asDate = (iso: string) => new Date(`${iso}T12:00:00`);

/** Couleurs des couches de dépenses (variables CSS : une valeur en clair, une en sombre). */
export const LAYER_COLORS = {
  fixe: "var(--layer-fixe)",
  essentiel: "var(--layer-essentiel)",
  plaisir: "var(--layer-plaisir)",
  epargne: "var(--layer-epargne)",
} as const;
export const LAYER_NAMES = { fixe: "Charges fixes", essentiel: "Essentiels", plaisir: "Plaisirs", epargne: "Épargne" } as const;

export interface ProjectionBar {
  key: string;
  label: string;
  income: number;
  fixe: number;
  essentiel: number;
  plaisir: number;
  epargne: number;
  net?: number;
  partial?: boolean;
}

/** Projection mois par mois : sorties empilées (fixes, essentiels, plaisirs, épargne) et revenus en trait. */
export function ProjectionBars({ data, height = 240 }: { data: ProjectionBar[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const { ref, W, H } = useChartBox(height);
  const L = 56, B = 22, T = 14, R = 12;
  if (!data.length) return null;
  const every = labelEvery(data.length, W - L - R, 40);
  const stack: (keyof ProjectionBar & ("fixe" | "essentiel" | "plaisir" | "epargne"))[] = ["fixe", "essentiel", "plaisir", "epargne"];
  const outTotal = (d: ProjectionBar) => stack.reduce((s, k) => s + Math.max(d[k], 0), 0);
  const hi = niceMax(Math.max(1, ...data.map((d) => Math.max(outTotal(d), d.income))));
  const slot = (W - L - R) / data.length;
  const bw = Math.min(36, slot * 0.6);
  const cx = (i: number) => L + slot * i + slot / 2;
  const y = (v: number) => T + (H - T - B) * (1 - v / hi);
  const hd = hover !== null ? data[hover] : null;
  return (
    <div className="relative" ref={ref} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Projection des entrées et sorties, mois par mois">
        {[0, hi / 2, hi].map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="stroke-slate-200 dark:stroke-white/10" strokeWidth="1" />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" className="fill-slate-400 text-[11px]">{compactEuros(t)}</text>
          </g>
        ))}
        {data.map((d, i) => {
          let acc = 0;
          const visible = stack.filter((k) => d[k] > 0);
          return (
            <g key={d.key} opacity={d.partial ? 0.55 : 1}>
              {visible.map((k, j) => {
                const y0 = y(acc), y1 = y(acc + d[k]);
                acc += d[k];
                const top = j === visible.length - 1;
                const h = Math.max(y0 - y1 - 2, 1); // 2 px d'écart entre segments
                return <rect key={k} x={cx(i) - bw / 2} y={y1} width={bw} height={h} rx={top ? 4 : 0} fill={LAYER_COLORS[k]} />;
              })}
              {d.income > 0 && (
                <line x1={cx(i) - bw / 2 - 4} x2={cx(i) + bw / 2 + 4} y1={y(d.income)} y2={y(d.income)} className="stroke-slate-800 dark:stroke-slate-100" strokeWidth="2.5" strokeLinecap="round" />
              )}
              {(data.length - 1 - i) % every === 0 && <text x={cx(i)} y={H - 4} textAnchor="middle" className="fill-slate-400 text-[11px]">{d.label}</text>}
              {/* zone de survol plus large que la barre */}
              <rect x={cx(i) - slot / 2} y={T} width={slot} height={H - T - B} fill="transparent" onMouseEnter={() => setHover(i)} onClick={() => setHover(i)} />
            </g>
          );
        })}
      </svg>
      {hd && hover !== null && (
        <Tooltip x={(cx(hover) / W) * 100} y={(y(Math.max(outTotal(hd), hd.income)) / H) * 100 - 3}>
          <p className="font-semibold">{hd.label}{hd.partial ? " (reste du mois)" : ""}</p>
          <p>Revenus : {formatCents(hd.income)}</p>
          {[...stack].reverse().filter((k) => hd[k] !== 0).map((k) => (
            <p key={k} className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: LAYER_COLORS[k] }} />
              {LAYER_NAMES[k]} : {formatCents(-hd[k])}
            </p>
          ))}
          <p className="font-semibold">Reste : {formatCents(hd.net ?? hd.income - outTotal(hd))}</p>
        </Tooltip>
      )}
    </div>
  );
}

export interface TreasuryPoint {
  date: string;
  balance_cents: number;
  baseline_cents: number;
  income_cum: number;
  fixed_cum: number;
  essentiel_cum: number;
  plaisir_cum: number;
  transfer_cum: number;
}
export interface DayEvent {
  date: string;
  label: string;
  amount_cents: number;
  kind: string;
}
export type TreasuryShow = { revenu: boolean; essentiel: boolean; plaisir: boolean };

const INCOME_DOT = "#0f9f6e";

/** Trésorerie jour par jour.
 *  En haut : trois soldes — « charges fixes seulement » (pointillé), « + essentiels », et le solde prévu (épais) —,
 *  avec les échéances en pastilles sur le solde prévu. En bas, plus petit : les entrées et sorties de chaque jour ;
 *  un très gros montant (salaire, loyer) est écrêté, avec son montant écrit, pour ne pas écraser les autres jours. */
export function TreasuryChart({
  points,
  start,
  events,
  show,
  showBaseline = false,
}: {
  points: TreasuryPoint[];
  start: number;
  events: DayEvent[];
  show: TreasuryShow;
  showBaseline?: boolean;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const H2 = 104;
  const box = useChartBox(230 + H2 + 4);
  if (points.length < 2) return <p className="muted text-sm">Pas assez de jours à afficher.</p>;
  const W = box.W, L = 56, R = 12;
  const n = points.length, last = n - 1;
  const x = (i: number) => L + ((W - L - R) * i) / last;

  // Courbes recalculées selon les couches affichées.
  const lines = points.map((p) => {
    const fixedOnly = start + (show.revenu ? p.income_cum : 0) - p.fixed_cum + p.transfer_cum;
    const withEss = fixedOnly - (show.essentiel ? p.essentiel_cum : 0);
    return { fixedOnly, withEss, balance: withEss - (show.plaisir ? p.plaisir_cum : 0) };
  });
  // Mouvements de chaque jour (différence des cumuls).
  const day = points.map((p, i) => {
    const prev = i ? points[i - 1] : { income_cum: 0, fixed_cum: 0, essentiel_cum: 0, plaisir_cum: 0, transfer_cum: 0 };
    const tr = p.transfer_cum - prev.transfer_cum;
    return {
      income: show.revenu ? p.income_cum - prev.income_cum : 0,
      fixe: p.fixed_cum - prev.fixed_cum + Math.max(-tr, 0),
      essentiel: show.essentiel ? p.essentiel_cum - prev.essentiel_cum : 0,
      plaisir: show.plaisir ? p.plaisir_cum - prev.plaisir_cum : 0,
    };
  });

  // --- Graphique du haut : soldes ---
  const H = Math.max(140, box.H - H2 - 4), T = 14, B = 22;
  const vals = lines.flatMap((l) => [l.fixedOnly, l.balance, ...(show.essentiel ? [l.withEss] : [])]).concat(showBaseline ? points.map((p) => p.baseline_cents) : []);
  // Axe resserré sur les valeurs réelles (les courbes remplissent la hauteur), avec une petite marge.
  const vMin = Math.min(...vals), vMax = Math.max(...vals);
  const pad = Math.max((vMax - vMin) * 0.06, 1000);
  const lo = vMin - pad, hi = vMax + pad;
  const y = (v: number) => T + (H - T - B) * (1 - (v - lo) / (hi - lo || 1));
  const path = (get: (i: number) => number) => lines.map((_, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(get(i)).toFixed(1)}`).join(" ");
  const tStep = niceMax((hi - lo) / 4);
  const ticks: number[] = [];
  for (let t = Math.ceil(lo / tStep) * tStep; t <= hi; t += tStep) ticks.push(Math.round(t));
  if (lo < 0 && hi > 0 && !ticks.includes(0)) ticks.push(0);
  const step = labelEvery(n, W - L - R, 62);
  const dateLabels = (yy: number) =>
    points.map((p, i) =>
      (i % step === 0 && x(last) - x(i) >= 54) || i === last ? (
        <text key={p.date} x={x(i)} y={yy} textAnchor={i === 0 ? "start" : i === last ? "end" : "middle"} className="fill-slate-400 text-[11px]">
          {dayShort.format(asDate(p.date))}
        </text>
      ) : null,
    );

  const index = new Map(points.map((p, i) => [p.date, i]));
  const byDay = new Map<string, DayEvent[]>();
  for (const e of events) {
    if (!show.revenu && e.amount_cents > 0) continue;
    byDay.set(e.date, [...(byDay.get(e.date) ?? []), e]);
  }
  const maxEvent = Math.max(1, ...events.map((e) => Math.abs(e.amount_cents)));

  // --- Bande du bas : entrées / sorties du jour (écrêtées) ---
  const T2 = 16, B2 = 6;
  const sizes = day.flatMap((d) => [d.income, d.fixe + d.essentiel + d.plaisir]).filter((v) => v > 0).sort((a, b) => a - b);
  // Seuls les montants hors norme (salaire, loyer…) sont écrêtés : au-delà de 1,2 × le 90e centile ou 3 × la médiane.
  const pct = (q: number) => (sizes.length ? sizes[Math.min(sizes.length - 1, Math.floor(sizes.length * q))] : 1);
  const cap = Math.max(pct(0.9) * 1.2, pct(0.5) * 3, 1);
  const maxUp = Math.min(Math.max(0, ...day.map((d) => d.income)), cap);
  const maxDown = Math.min(Math.max(1, ...day.map((d) => d.fixe + d.essentiel + d.plaisir)), cap);
  const unit = (H2 - T2 - B2) / (maxUp + maxDown || 1);
  const zero = T2 + maxUp * unit;
  const slot = (W - L - R) / n;
  const bw = Math.max(1.5, Math.min(slot * 0.7, 14));

  const onMove = (e: { clientX: number; currentTarget: unknown }) => {
    const box = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    setHover(Math.min(Math.max(Math.round(((px - L) / (W - L - R)) * last), 0), last));
  };
  const hp = hover !== null ? points[hover] : null;
  const hl = hover !== null ? lines[hover] : null;
  const hd = hover !== null ? day[hover] : null;
  const dayEvents = hp ? byDay.get(hp.date) ?? [] : [];

  return (
    <div className="relative" ref={box.ref} onMouseLeave={() => setHover(null)}>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full touch-pan-y" role="img" aria-label="Solde prévu jour par jour" onPointerMove={onMove}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className={t === 0 && lo < 0 ? "stroke-slate-400 dark:stroke-slate-500" : "stroke-slate-200 dark:stroke-white/10"} strokeWidth="1" strokeDasharray={t === 0 && lo < 0 ? "4 3" : undefined} />
            <text x={L - 6} y={y(t) + 4} textAnchor="end" className="fill-slate-400 text-[11px]">{compactEuros(t)}</text>
          </g>
        ))}
        {dateLabels(H - 4)}
        {lo < 0 && <rect x={L} y={y(Math.min(0, hi))} width={W - L - R} height={y(lo) - y(Math.min(0, hi))} fill={SPENT_COLOR} opacity="0.05" />}
        {showBaseline && <path d={path((i) => points[i].baseline_cents)} fill="none" stroke={MUTED_LINE} strokeWidth="1.5" strokeDasharray="2 3" />}
        <path d={path((i) => lines[i].fixedOnly)} fill="none" stroke={LAYER_COLORS.fixe} strokeWidth="2" strokeDasharray="6 4" strokeLinejoin="round" />
        {show.essentiel && show.plaisir && <path d={path((i) => lines[i].withEss)} fill="none" stroke={LAYER_COLORS.essentiel} strokeWidth="2" strokeLinejoin="round" />}
        <path d={path((i) => lines[i].balance)} fill="none" stroke={ACCENT} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {[...byDay.entries()].map(([d, evs]) => {
          const i = index.get(d);
          if (i === undefined) return null;
          const net = evs.reduce((s, e) => s + e.amount_cents, 0);
          const big = evs.find((e) => Math.abs(e.amount_cents) >= maxEvent * 0.3);
          return (
            <g key={d}>
              <circle cx={x(i)} cy={y(lines[i].balance)} r="5" fill={net > 0 ? INCOME_DOT : LAYER_COLORS.fixe} className="stroke-panel dark:stroke-panel-dark" strokeWidth="2" />
              {big && (
                <text x={x(i)} y={y(lines[i].balance) + (net > 0 ? -10 : 18)} textAnchor="middle" className="fill-slate-500 stroke-panel text-[11px] dark:fill-slate-400 dark:stroke-panel-dark" strokeWidth="3" paintOrder="stroke">
                  {big.label.length > 16 ? `${big.label.slice(0, 15)}…` : big.label}
                </text>
              )}
            </g>
          );
        })}
        {hover !== null && (
          <>
            <line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} className="stroke-slate-300 dark:stroke-white/20" strokeWidth="1" />
            <circle cx={x(hover)} cy={y(lines[hover].balance)} r="5" fill={ACCENT} className="stroke-panel dark:stroke-panel-dark" strokeWidth="2" />
          </>
        )}
      </svg>

      <svg viewBox={`0 0 ${W} ${H2}`} className="mt-1 w-full touch-pan-y" role="img" aria-label="Entrées et sorties prévues chaque jour" onPointerMove={onMove}>
        <line x1={L} x2={W - R} y1={zero} y2={zero} className="stroke-slate-200 dark:stroke-white/10" strokeWidth="1" />
        <text x={L - 6} y={zero - 4} textAnchor="end" className="fill-slate-400 text-[10px]">entrées</text>
        <text x={L - 6} y={zero + 11} textAnchor="end" className="fill-slate-400 text-[10px]">sorties</text>
        {day.map((d, i) => {
          const cx = L + slot * i + slot / 2;
          const up = Math.min(d.income, cap) * unit;
          let acc = 0;
          const outTotal = d.fixe + d.essentiel + d.plaisir;
          const scale = outTotal > cap ? cap / outTotal : 1;
          return (
            <g key={i}>
              {d.income > 0 && <rect x={cx - bw / 2} y={zero - up} width={bw} height={up} rx="1.5" fill={INCOME_DOT} />}
              {d.income > cap && <text x={cx} y={Math.max(zero - up - 3, 10)} textAnchor="middle" className="fill-slate-500 text-[10px] dark:fill-slate-400">+{compactEuros(d.income)}</text>}
              {(["fixe", "essentiel", "plaisir"] as const).map((k) => {
                const v = d[k] * scale * unit;
                if (v <= 0) return null;
                const r = <rect key={k} x={cx - bw / 2} y={zero + acc + 1} width={bw} height={Math.max(v - 1, 0.8)} fill={LAYER_COLORS[k]} />;
                acc += v;
                return r;
              })}
              {outTotal > cap && <text x={cx} y={Math.min(zero + acc + 10, H2 - 1)} textAnchor="middle" className="fill-slate-500 text-[10px] dark:fill-slate-400">−{compactEuros(outTotal)}</text>}
            </g>
          );
        })}
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={0} y2={H2} className="stroke-slate-300 dark:stroke-white/20" strokeWidth="1" />}
      </svg>

      {hp && hl && hd && hover !== null && (
        <Tooltip x={(x(hover) / W) * 100} y={(y(hl.balance) / (H + H2)) * 100 - 2}>
          <p className="font-semibold">{dayLong.format(asDate(hp.date))}</p>
          <p className="text-white/80">Charges fixes seulement : {formatCents(hl.fixedOnly)}</p>
          {show.essentiel && show.plaisir && <p className="text-white/80">+ essentiels : {formatCents(hl.withEss)}</p>}
          <p className="font-semibold">Solde prévu : {formatCents(hl.balance)}</p>
          {showBaseline && <p className="text-white/70">Sans scénario : {formatCents(hp.baseline_cents)}</p>}
          {dayEvents.slice(0, 4).map((e, k) => (
            <p key={k} className="text-white/90">{e.amount_cents > 0 ? "▲" : "▼"} {e.label} {formatCents(e.amount_cents)}</p>
          ))}
          {dayEvents.length > 4 && <p className="text-white/80">+ {dayEvents.length - 4} autre(s)</p>}
          {(hd.essentiel > 0 || hd.plaisir > 0) && (
            <p className="text-white/80">
              Ce jour-là, d'habitude : {hd.essentiel > 0 && `essentiels ${formatCents(-hd.essentiel)}`}
              {hd.essentiel > 0 && hd.plaisir > 0 && " · "}
              {hd.plaisir > 0 && `plaisirs ${formatCents(-hd.plaisir)}`}
            </p>
          )}
        </Tooltip>
      )}
    </div>
  );
}
