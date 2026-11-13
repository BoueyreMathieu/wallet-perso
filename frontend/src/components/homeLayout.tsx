import { ReactNode, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { isNative } from "../native";

/** Une carte de l'accueil : `span` = largeur souhaitée sur ordinateur (sur 6 colonnes) ; `node` null = rien à montrer. */
export interface HomeCardDef {
  id: string;
  title: string;
  span: number;
  node: ReactNode | null;
}
interface Saved {
  id: string;
  hidden: boolean;
}

// Classes écrites en entier (Tailwind ne génère que les classes qu'il voit dans le code).
const SPAN: Record<number, string> = {
  1: "lg:col-span-1", 2: "lg:col-span-2", 3: "lg:col-span-3", 4: "lg:col-span-4", 5: "lg:col-span-5", 6: "lg:col-span-6",
};

/** Taille ajustée automatiquement : une ligne qui n'est pas pleine (carte masquée, carte vide…) est complétée en
 *  élargissant sa dernière carte. */
export function pack(spans: number[]): number[] {
  const out = [...spans];
  let row = 0;
  let last = -1;
  for (let i = 0; i < out.length; i++) {
    const s = Math.min(Math.max(out[i], 1), 6);
    out[i] = s;
    if (row + s > 6) {
      if (last >= 0) out[last] += 6 - row;
      row = 0;
    }
    row += s;
    last = i;
    if (row === 6) row = 0;
  }
  if (row > 0 && last >= 0) out[last] += 6 - row;
  return out;
}

/** Téléphone (appli ou petit écran) et ordinateur ont chacun leur disposition. */
export const homePlatform = () => (isNative() || window.matchMedia?.("(max-width: 767px)").matches ? "mobile" : "web");

function merge(cards: HomeCardDef[], saved: Saved[] | null): Saved[] {
  const known = new Set(cards.map((c) => c.id));
  const kept = (saved ?? []).filter((s) => known.has(s.id));
  const seen = new Set(kept.map((s) => s.id));
  return [...kept, ...cards.filter((c) => !seen.has(c.id)).map((c) => ({ id: c.id, hidden: false }))];
}

export function HomeGrid({ cards, editing, onCloseEditor }: { cards: HomeCardDef[]; editing: boolean; onCloseEditor: () => void }) {
  const [platform] = useState(homePlatform);
  const [saved, setSaved] = useState<Saved[] | null | undefined>(undefined);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    api.get<{ cards: Saved[] | null }>(`/settings/home-layout?platform=${platform}`).then((r) => setSaved(r.cards), () => setSaved(null));
  }, [platform]);
  if (saved === undefined) return null;

  const order = merge(cards, saved);
  const byId = new Map(cards.map((c) => [c.id, c]));
  const change = (next: Saved[]) => {
    setSaved(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      api.put(`/settings/home-layout?platform=${platform}`, { cards: next }).catch(() => undefined);
    }, 500);
  };
  const reset = async () => {
    await api.del(`/settings/home-layout?platform=${platform}`).catch(() => undefined);
    setSaved(null);
  };

  const visible = order.filter((s) => !s.hidden && byId.get(s.id)?.node);
  const spans = pack(visible.map((s) => byId.get(s.id)!.span));
  return (
    <>
      {editing && <LayoutEditor order={order} cards={byId} platform={platform} onChange={change} onReset={reset} onClose={onCloseEditor} />}
      <div className="grid gap-4 lg:grid-cols-6">
        {visible.map((s, i) => (
          <div key={s.id} className={`min-w-0 empty:hidden ${SPAN[spans[i]]} [&>*]:h-full`}>
            {byId.get(s.id)!.node}
          </div>
        ))}
      </div>
    </>
  );
}

/** Personnaliser : glisser ⠿ (ou ↑ ↓) pour réordonner, 👁 pour cacher / afficher. */
function LayoutEditor({
  order,
  cards,
  platform,
  onChange,
  onReset,
  onClose,
}: {
  order: Saved[];
  cards: Map<string, HomeCardDef>;
  platform: string;
  onChange: (next: Saved[]) => void;
  onReset: () => void;
  onClose: () => void;
}) {
  const list = useRef<HTMLUListElement | null>(null);
  const [drag, setDrag] = useState<{ id: string; y: number; startY: number } | null>(null);
  const move = (from: number, to: number) => {
    if (to < 0 || to >= order.length || from === to) return;
    const next = [...order];
    const [it] = next.splice(from, 1);
    next.splice(to, 0, it);
    onChange(next);
  };
  const onDown = (id: string, e: { clientY: number; pointerId: number; currentTarget: unknown }) => {
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    setDrag({ id, y: e.clientY, startY: e.clientY });
  };
  const onMove = (e: { clientY: number }) => {
    if (!drag || !list.current) return;
    const rows = [...list.current.querySelectorAll<HTMLElement>("[data-row]")];
    const from = order.findIndex((s) => s.id === drag.id);
    // Ligne survolée : celle dont le milieu est le plus proche du doigt / de la souris.
    let to = from;
    rows.forEach((r, i) => {
      const box = r.getBoundingClientRect();
      if (e.clientY > box.top && e.clientY < box.bottom) to = i;
    });
    if (to !== from) move(from, to);
    setDrag({ ...drag, y: e.clientY });
  };
  return (
    <section className="card space-y-3 ring-2 ring-accent-200 dark:ring-accent-800">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-title">✏️ Personnaliser l'accueil {platform === "mobile" ? "(téléphone)" : "(ordinateur)"}</h2>
        <div className="flex gap-2">
          <button className="btn-ghost text-sm" onClick={onReset}>↺ Par défaut</button>
          <button className="btn px-3 py-1.5 text-sm" onClick={onClose}>Terminé</button>
        </div>
      </div>
      <p className="muted text-xs">
        Glisse ⠿ pour déplacer une carte, 👁 pour la cacher. La largeur s'ajuste toute seule. Le téléphone et l'ordinateur ont chacun leur disposition.
      </p>
      <ul ref={list} className="space-y-1 touch-none select-none" onPointerMove={onMove} onPointerUp={() => setDrag(null)} onPointerCancel={() => setDrag(null)}>
        {order.map((s, i) => {
          const c = cards.get(s.id);
          if (!c) return null;
          return (
            <li
              key={s.id}
              data-row
              className={`flex items-center gap-2 rounded-xl border px-2 py-1.5 text-sm transition ${
                drag?.id === s.id ? "border-accent-300 bg-accent-50 shadow-md dark:border-accent-500/40 dark:bg-accent-500/10" : "border-slate-100 dark:border-white/10"
              } ${s.hidden ? "opacity-50" : ""}`}
            >
              <button className="cursor-grab touch-none px-1 text-lg leading-none text-slate-400 active:cursor-grabbing" onPointerDown={(e) => onDown(s.id, e)} aria-label={`Déplacer ${c.title}`}>⠿</button>
              <span className={`min-w-0 flex-1 truncate ${s.hidden ? "line-through" : ""}`}>
                {c.title}
                {!c.node && <span className="muted ml-2 text-xs">(rien à montrer en ce moment)</span>}
              </span>
              <button className="btn-ghost px-2 py-1" onClick={() => move(i, i - 1)} disabled={i === 0} aria-label="Monter">↑</button>
              <button className="btn-ghost px-2 py-1" onClick={() => move(i, i + 1)} disabled={i === order.length - 1} aria-label="Descendre">↓</button>
              <button
                className="btn-ghost px-2 py-1"
                onClick={() => onChange(order.map((x) => (x.id === s.id ? { ...x, hidden: !x.hidden } : x)))}
                aria-pressed={!s.hidden}
                aria-label={s.hidden ? "Afficher" : "Cacher"}
              >
                {s.hidden ? "🙈" : "👁"}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
