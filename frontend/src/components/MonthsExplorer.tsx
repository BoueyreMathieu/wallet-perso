import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { ChartFrame, Legend, MonthBars, INCOME_COLOR, SPENT_COLOR } from "./charts";

interface MonthPoint {
  month: string;
  income_cents: number;
  spent_cents: number;
}

const shortMonth = new Intl.DateTimeFormat("fr-FR", { month: "short" });
const longMonth = new Intl.DateTimeFormat("fr-FR", { month: "short", year: "numeric" });
const toDate = (key: string) => {
  const [y, m] = key.split("-").map(Number);
  return new Date(y, m - 1, 1);
};
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const SIZES = [6, 12, 24];

/** Revenus / dépenses mois par mois, sur une fenêtre réglable qu'on fait défiler :
 *  glisser (souris ou doigt), molette, ou flèches ‹ ›. */
export function MonthsExplorer({
  accounts,
  categoryId,
  title,
  selected,
  onSelect,
}: {
  accounts: number[];
  categoryId: number | null;
  title: string;
  selected?: string;
  onSelect: (month: string) => void;
}) {
  const [points, setPoints] = useState<MonthPoint[]>([]);
  const [size, setSize] = useState(12);
  const [end, setEnd] = useState<number | null>(null); // index du dernier mois affiché (null = le plus récent)
  const box = useRef<HTMLDivElement | null>(null);
  const drag = useRef<{ x: number; end: number; moved: boolean } | null>(null);
  const justDragged = useRef(false);

  useEffect(() => {
    const params = new URLSearchParams();
    if (accounts.length) params.set("accounts", accounts.join(","));
    if (categoryId !== null) params.set("category_id", String(categoryId));
    api.get<MonthPoint[]>(`/dashboard/months?${params}`).then((p) => {
      setPoints(p);
      setEnd(null);
    });
  }, [accounts.join(","), categoryId]); // eslint-disable-line react-hooks/exhaustive-deps

  const last = points.length - 1;
  const minEnd = Math.min(size - 1, last);
  const clamp = (i: number) => Math.min(Math.max(i, minEnd), last);
  const endIdx = clamp(end ?? last);
  const visible = points.slice(Math.max(0, endIdx - size + 1), endIdx + 1);
  const shift = (delta: number) => setEnd(clamp(endIdx + delta));

  // Molette (et défilement horizontal du pavé tactile) : écouteur natif pour pouvoir bloquer le défilement de la page.
  const wheelState = useRef({ acc: 0, endIdx, clamp });
  wheelState.current.endIdx = endIdx;
  wheelState.current.clamp = clamp;
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      const d = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (!d) return;
      e.preventDefault();
      const st = wheelState.current;
      st.acc += d;
      const steps = Math.trunc(st.acc / 60);
      if (steps) {
        st.acc -= steps * 60;
        setEnd(st.clamp(st.endIdx + steps));
      }
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, [points.length]);

  // Glisser : vers la droite = mois plus anciens (comme on tire une frise).
  const onPointerDown = (e: { clientX: number; pointerType: string; button: number }) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    justDragged.current = false;
    drag.current = { x: e.clientX, end: endIdx, moved: false };
    const move = (ev: PointerEvent) => {
      const d = drag.current;
      if (!d || !box.current) return;
      const slot = box.current.getBoundingClientRect().width / Math.max(visible.length, 1);
      const dx = ev.clientX - d.x;
      if (Math.abs(dx) > 6) d.moved = true;
      setEnd(clamp(d.end - Math.round(dx / slot)));
    };
    const up = () => {
      justDragged.current = !!drag.current?.moved;
      drag.current = null;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  const range = visible.length ? `${cap(longMonth.format(toDate(visible[0].month)))} → ${longMonth.format(toDate(visible[visible.length - 1].month))}` : "";
  const totals = visible.reduce((t, m) => ({ income: t.income + m.income_cents, spent: t.spent + m.spent_cents }), { income: 0, spent: 0 });

  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="section-title">{title}</h2>
          <p className="muted text-xs">{range}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl bg-slate-100 p-1 text-xs dark:bg-white/5">
            {SIZES.map((n) => (
              <button
                key={n}
                onClick={() => setSize(n)}
                className={`rounded-lg px-2.5 py-1 ${size === n ? "bg-white font-semibold shadow-sm dark:bg-slate-700" : "muted"}`}
              >
                {n} mois
              </button>
            ))}
          </div>
          <div className="flex items-center">
            <button className="btn-ghost px-2" disabled={endIdx <= minEnd} onClick={() => shift(-1)} aria-label="Mois plus anciens">‹</button>
            <button className="btn-ghost px-2" disabled={endIdx >= last} onClick={() => shift(1)} aria-label="Mois plus récents">›</button>
            {endIdx < last && (
              <button className="btn-ghost px-2 text-xs" onClick={() => setEnd(null)}>Aujourd'hui</button>
            )}
          </div>
        </div>
      </div>
      <ChartFrame help="Glisse le graphique (ou utilise la molette) pour remonter dans le temps ; clique sur un mois pour l'afficher.">
      <div
        ref={box}
        className="cursor-grab touch-pan-y select-none active:cursor-grabbing"
        onPointerDown={onPointerDown}
      >
        <MonthBars
          data={visible.map((m) => ({
            key: m.month,
            // janvier porte l'année, pour se repérer en remontant le temps
            label: cap(shortMonth.format(toDate(m.month)).replace(".", "")) + (m.month.endsWith("-01") ? ` ${m.month.slice(2, 4)}` : ""),
            income: m.income_cents,
            spent: m.spent_cents,
          }))}
          selected={selected}
          onSelect={(key) => {
            if (justDragged.current) {
              justDragged.current = false; // fin d'un glisser, pas un clic
              return;
            }
            onSelect(key);
          }}
        />
      </div>
      </ChartFrame>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Legend items={[{ label: "Revenus", color: INCOME_COLOR }, { label: "Dépenses", color: SPENT_COLOR }]} />
        <p className="muted text-xs">
          Sur ces {visible.length} mois : revenus {Math.round(totals.income / 100).toLocaleString("fr-FR")} €, dépenses{" "}
          {Math.round(totals.spent / 100).toLocaleString("fr-FR")} €
        </p>
      </div>
    </section>
  );
}
