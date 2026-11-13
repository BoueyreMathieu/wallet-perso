import { CSSProperties, createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { Category, api } from "../api";

interface Ctx {
  categories: Category[];
  byId: Map<number, Category>;
  /** « Alimentation › Courses » */
  pathOf: (id: number | null) => string;
  /** Icône de la catégorie, ou celle de sa catégorie principale. */
  iconOf: (id: number | null) => string;
  /** Couleur de la catégorie, ou celle de sa catégorie principale. */
  colorOf: (id: number | null) => string;
  reload: () => Promise<void>;
}

export const UNCATEGORIZED_COLOR = "#94a3b8";
const FALLBACK_ICON = "🏷️";

const CategoriesContext = createContext<Ctx>({
  categories: [],
  byId: new Map(),
  pathOf: () => "",
  iconOf: () => FALLBACK_ICON,
  colorOf: () => UNCATEGORIZED_COLOR,
  reload: async () => undefined,
});

export function CategoriesProvider({ children }: { children: ReactNode }) {
  const [categories, setCategories] = useState<Category[]>([]);
  const reload = useCallback(async () => {
    setCategories(await api.get<Category[]>("/categories"));
  }, []);
  useEffect(() => {
    reload();
  }, [reload]);
  const value = useMemo(() => {
    const byId = new Map<number, Category>(categories.map((c) => [c.id, c] as [number, Category]));
    const parentOf = (c: Category) => (c.parent_id ? byId.get(c.parent_id) : undefined);
    const pathOf = (id: number | null) => {
      const c = id !== null ? byId.get(id) : undefined;
      if (!c) return "";
      const parent = parentOf(c);
      return parent ? `${parent.name} › ${c.name}` : c.name;
    };
    const iconOf = (id: number | null) => {
      const c = id !== null ? byId.get(id) : undefined;
      if (!c) return id === null ? "❔" : FALLBACK_ICON;
      return c.icon || parentOf(c)?.icon || FALLBACK_ICON;
    };
    // Une sous-catégorie qui a la couleur de sa catégorie principale reçoit une nuance légèrement différente
    // (plus claire / plus foncée, en alternance) : on distingue les sous-catégories sans perdre la famille.
    const shades = new Map<number, string>();
    for (const p of categories.filter((c) => c.parent_id === null)) {
      const base = p.color || UNCATEGORIZED_COLOR;
      const kids = categories.filter((c) => c.parent_id === p.id).sort((a, b) => a.id - b.id);
      kids.forEach((k, i) => {
        if (k.color && k.color.toLowerCase() !== base.toLowerCase()) return; // couleur choisie à part : gardée
        shades.set(k.id, shade(base, i));
      });
    }
    const colorOf = (id: number | null) => {
      const c = id !== null ? byId.get(id) : undefined;
      if (!c) return UNCATEGORIZED_COLOR;
      return shades.get(c.id) || c.color || parentOf(c)?.color || UNCATEGORIZED_COLOR;
    };
    return { categories, byId, pathOf, iconOf, colorOf, reload };
  }, [categories, reload]);
  return <CategoriesContext.Provider value={value}>{children}</CategoriesContext.Provider>;
}

export const useCategories = () => useContext(CategoriesContext);

function hexToHsl(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const sat = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, sat, l];
}

function hslToHex(h: number, sat: number, l: number): string {
  const k = (n: number) => (n + h / 30) % 12;
  const a = sat * Math.min(l, 1 - l);
  const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  return "#" + [f(0), f(8), f(4)].map((x) => Math.round(x * 255).toString(16).padStart(2, "0")).join("");
}

/** i-ème nuance d'une couleur : +6 %, −6 %, +12 %, −12 %… de luminosité, avec un léger décalage de teinte. */
export function shade(hex: string, i: number): string {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) return hex;
  const [h, sat, l] = hexToHsl(hex);
  const step = Math.floor(i / 2) + 1;
  const sign = i % 2 === 0 ? 1 : -1;
  const light = Math.min(0.8, Math.max(0.22, l + sign * step * 0.06));
  return hslToHex((h + sign * step * 4 + 360) % 360, sat, light);
}

const RECENT_KEY = "wallet-recent-categories";

function readRecent(): number[] {
  try {
    const v = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((x) => typeof x === "number") : [];
  } catch {
    return [];
  }
}

function pushRecent(id: number) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify([id, ...readRecent().filter((x) => x !== id)].slice(0, 6)));
  } catch {
    /* stockage indisponible */
  }
}

/** Sans accents, en minuscules : « Électricité » ≈ « electricite ». */
const fold = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();

interface Option {
  id: number | null;
  label: string;
}

interface Group {
  parent: Category;
  children: Category[];
}

/** Choix d'une catégorie : grand panneau avec toutes les catégories d'un coup (groupées), recherche
 *  (« resto », « carbu »…), flèches + Entrée, catégories récentes en tête. */
export function CategorySelect({
  value,
  onChange,
  emptyLabel = "— Non catégorisé —",
  className = "input",
  exclude = [],
}: {
  value: number | null;
  onChange: (id: number | null) => void;
  emptyLabel?: string;
  className?: string;
  exclude?: number[];
}) {
  const { categories, iconOf, pathOf, colorOf } = useCategories();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [pos, setPos] = useState<CSSProperties>({});
  const [mobile, setMobile] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);
  const wrap = useRef<HTMLDivElement | null>(null);
  const panel = useRef<HTMLDivElement | null>(null);

  const excludeKey = exclude.join(",");
  const { groups, recent, flat } = useMemo(() => {
    const q = fold(query.trim());
    const excluded = excludeKey ? excludeKey.split(",").map(Number) : [];
    const visible = categories.filter((c) => !excluded.includes(c.id));
    const groups: Group[] = [];
    for (const p of visible.filter((c) => c.parent_id === null)) {
      const kids = visible.filter((c) => c.parent_id === p.id);
      if (!q || fold(p.name).includes(q)) groups.push({ parent: p, children: kids });
      else {
        const hits = kids.filter((c) => fold(c.name).includes(q));
        if (hits.length) groups.push({ parent: p, children: hits });
      }
    }
    const recent = q ? [] : readRecent().filter((id) => visible.some((c) => c.id === id));
    // Ordre de navigation au clavier = ordre d'affichage.
    const flat: Option[] = [];
    if (!q) flat.push({ id: null, label: emptyLabel });
    for (const id of recent) flat.push({ id, label: pathOf(id) });
    for (const g of groups) {
      flat.push({ id: g.parent.id, label: g.parent.name });
      for (const c of g.children) flat.push({ id: c.id, label: c.name });
    }
    return { groups, recent, flat };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories, excludeKey, query, emptyLabel, pathOf, open]);

  // Pendant une recherche, le curseur part sur le premier résultat qui n'est pas une catégorie principale.
  useEffect(() => {
    if (!open) return;
    const firstChild = query.trim() ? flat.findIndex((o) => o.id !== null && categories.find((c) => c.id === o.id)?.parent_id !== null) : -1;
    setCursor(firstChild >= 0 ? firstChild : 0);
  }, [query, open, flat, categories]);
  useEffect(() => {
    panel.current?.querySelector(`[data-index="${cursor}"]`)?.scrollIntoView({ block: "nearest" });
  }, [cursor]);
  useEffect(() => {
    // Ordinateur seulement : le panneau, placé sous le champ, se ferme si la page bouge.
    // (Sur téléphone, le clavier qui s'ouvre redimensionne et fait défiler la page : le panneau se fermait aussitôt.)
    if (!open || mobile) return;
    const close = (e: Event) => {
      if (panel.current && e.target instanceof Node && panel.current.contains(e.target)) return;
      setOpen(false);
    };
    window.addEventListener("resize", close);
    window.addEventListener("scroll", close, true);
    return () => {
      window.removeEventListener("resize", close);
      window.removeEventListener("scroll", close, true);
    };
  }, [open, mobile]);

  const show = () => {
    const box = wrap.current?.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight;
    const phone = !box || vw < 640;
    setMobile(phone);
    if (phone) {
      setPos({ left: 0, right: 0, bottom: 0, maxHeight: "85dvh", paddingBottom: "env(safe-area-inset-bottom)" }); // téléphone : panneau en bas d'écran
      const parent = value !== null ? categories.find((c) => c.id === value)?.parent_id ?? value : null;
      setExpanded(parent);
    } else {
      const width = Math.min(780, vw - 16);
      const left = Math.min(Math.max(box.left, 8), vw - width - 8);
      const below = vh - box.bottom, above = box.top;
      setPos(below >= 360 || below >= above ? { left, width, top: box.bottom + 4, maxHeight: below - 12 } : { left, width, bottom: vh - box.top + 4, maxHeight: above - 12 });
    }
    setQuery("");
    setOpen(true);
  };
  const choose = (id: number | null) => {
    if (id !== null) pushRecent(id);
    onChange(id);
    setOpen(false);
  };
  const onKey = (e: { key: string; preventDefault: () => void }) => {
    if (e.key === "ArrowDown" || e.key === "ArrowRight") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, flat.length - 1));
    } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (flat[cursor]) choose(flat[cursor].id);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  let index = 0;
  const item = (id: number | null, content: ReactNode, cls: string) => {
    const i = index++;
    return (
      <button
        type="button"
        key={`${id}-${i}`}
        data-index={i}
        onMouseEnter={() => !mobile && setCursor(i)}
        onClick={() => choose(id)}
        className={`${cls} ${!mobile && i === cursor ? "ring-2 ring-accent-400" : ""} ${id === value ? "bg-accent-100 text-accent-800 dark:bg-accent-500/25 dark:text-accent-100" : ""}`}
      >
        {content}
      </button>
    );
  };
  const chip = "inline-flex max-w-full items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-left text-[13px] transition hover:bg-slate-200 dark:bg-white/5 dark:hover:bg-white/10";
  const searching = query.trim() !== "";

  // Téléphone : catégories principales en liste ; on en touche une pour déplier ses sous-catégories.
  const mobileList = (
    <div className="overflow-auto overscroll-contain px-3 pb-3" role="listbox">
      {!searching && (
        <div className="flex flex-wrap gap-1.5 py-2">
          {item(null, <><span aria-hidden className="muted">∅</span> {emptyLabel}</>, chip)}
          {recent.map((id) => item(id, <><span aria-hidden>{iconOf(id)}</span> <span className="truncate">{pathOf(id)}</span></>, chip))}
        </div>
      )}
      <ul className="divide-y divide-slate-100 dark:divide-white/5">
        {groups.map((g) => {
          const isOpen = searching || expanded === g.parent.id;
          const inside = value !== null && (value === g.parent.id || g.children.some((c) => c.id === value));
          return (
            <li key={g.parent.id}>
              <button
                type="button"
                className="flex w-full items-center gap-3 py-3 text-left"
                onClick={() => (g.children.length === 0 ? choose(g.parent.id) : setExpanded(expanded === g.parent.id ? null : g.parent.id))}
              >
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full text-lg" style={{ background: `${colorOf(g.parent.id)}26` }} aria-hidden>
                  {iconOf(g.parent.id)}
                </span>
                <span className={`min-w-0 flex-1 truncate font-medium ${inside ? "text-accent-700 dark:text-accent-300" : ""}`}>{g.parent.name}</span>
                {g.children.length > 0 && <span className="muted text-xs">{g.children.length}</span>}
                <span className="muted w-4 text-center" aria-hidden>{g.children.length === 0 ? "" : isOpen ? "▾" : "›"}</span>
              </button>
              {isOpen && g.children.length > 0 && (
                <div className="grid grid-cols-2 gap-1.5 pb-3 pl-12">
                  {item(g.parent.id, <><span className="truncate">Tout « {g.parent.name} »</span></>, `${chip} col-span-2 justify-center py-2`)}
                  {g.children.map((c) => item(c.id, <><span aria-hidden>{iconOf(c.id)}</span> <span className="truncate">{c.name}</span></>, `${chip} py-2`))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {groups.length === 0 && <p className="muted px-1 py-3 text-sm">Aucune catégorie ne correspond.</p>}
    </div>
  );

  return (
    <div ref={wrap} className={`relative min-w-0 ${className.includes("w-") ? "" : "w-full"}`}>
      <button type="button" className={`${className} flex min-w-0 items-center gap-2 text-left`} onClick={() => (open ? setOpen(false) : show())}>
        {value !== null ? (
          <>
            <span aria-hidden>{iconOf(value)}</span>
            <span className="min-w-0 flex-1 truncate">{pathOf(value)}</span>
          </>
        ) : (
          <span className="min-w-0 flex-1 truncate muted">{emptyLabel}</span>
        )}
        <span className="muted text-xs" aria-hidden>▾</span>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40 bg-black/30 sm:bg-transparent" onClick={() => setOpen(false)} />
          <div
            ref={panel}
            style={pos}
            className={`fixed z-50 flex flex-col overflow-hidden border border-slate-200 bg-panel shadow-2xl dark:border-white/10 dark:bg-panel-dark ${mobile ? "rounded-t-3xl" : "rounded-2xl"}`}
          >
            {mobile && (
              <div className="flex items-center gap-2 px-4 pt-3">
                <span className="mx-auto h-1 w-10 rounded-full bg-slate-300 dark:bg-white/20" aria-hidden />
              </div>
            )}
            <div className={`flex items-center gap-2 ${mobile ? "px-3 py-2" : ""}`}>
              <input
                autoFocus={!mobile}
                className={mobile ? "input flex-1 py-2 text-sm" : "w-full border-b border-slate-100 bg-transparent px-4 py-3 text-sm outline-none dark:border-white/10"}
                placeholder={mobile ? "🔍 Rechercher (resto, carbu…)" : "Rechercher une catégorie… (Entrée pour choisir)"}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKey}
                enterKeyHint="search"
              />
              {mobile && (
                <button type="button" className="btn-ghost px-3 py-2" onClick={() => setOpen(false)} aria-label="Fermer">
                  ✕
                </button>
              )}
            </div>
            {mobile ? (
              mobileList
            ) : (
              <div className="space-y-3 overflow-auto overscroll-contain p-3" role="listbox">
                {!searching && (
                  <div className="flex flex-wrap gap-1.5">
                    {item(null, <><span aria-hidden className="muted">∅</span> {emptyLabel}</>, chip)}
                    {recent.map((id) => item(id, <><span aria-hidden>{iconOf(id)}</span> <span className="truncate">{pathOf(id)}</span><span className="muted text-[10px]">récent</span></>, chip))}
                  </div>
                )}
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {groups.map((g) => (
                    <div key={g.parent.id} className="rounded-xl border border-slate-100 p-2 dark:border-white/5" style={{ borderTopColor: colorOf(g.parent.id), borderTopWidth: 3 }}>
                      {item(
                        g.parent.id,
                        <>
                          <span aria-hidden>{iconOf(g.parent.id)}</span>
                          <span className="min-w-0 flex-1 truncate">{g.parent.name}</span>
                          <span className="muted text-[10px] font-normal">général</span>
                        </>,
                        "mb-1 flex w-full items-center gap-1.5 rounded-lg px-2 py-1 text-left text-sm font-semibold hover:bg-slate-100 dark:hover:bg-white/5",
                      )}
                      <div className="flex flex-wrap gap-1">
                        {g.children.map((c) => item(c.id, <><span aria-hidden>{iconOf(c.id)}</span> <span className="truncate">{c.name}</span></>, chip))}
                      </div>
                    </div>
                  ))}
                </div>
                {groups.length === 0 && <p className="muted px-1 text-sm">Aucune catégorie ne correspond.</p>}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/** Pastille ronde colorée avec l'icône de la catégorie. */
export function CategoryIcon({ id, size = "md" }: { id: number | null; size?: "sm" | "md" | "lg" }) {
  const { iconOf, colorOf } = useCategories();
  const dims = size === "sm" ? "h-6 w-6 text-xs" : size === "lg" ? "h-11 w-11 text-xl" : "h-9 w-9 text-base";
  const color = colorOf(id);
  return (
    <span className={`grid shrink-0 place-items-center rounded-full ${dims}`} style={{ background: `${color}26` }} aria-hidden>
      {iconOf(id)}
    </span>
  );
}

export function CategoryBadge({ id }: { id: number | null }) {
  const { byId, pathOf, iconOf, colorOf } = useCategories();
  const c = id !== null ? byId.get(id) : undefined;
  if (!c) return <span className="chip bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-200">❔ À catégoriser</span>;
  return (
    <span className="chip bg-slate-100 text-slate-700 dark:bg-white/5 dark:text-slate-200">
      <span className="h-2 w-2 rounded-full" style={{ background: colorOf(id) }} />
      <span aria-hidden>{iconOf(id)}</span>
      {pathOf(id)}
    </span>
  );
}
