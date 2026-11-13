import { useEffect, useState } from "react";
import { api, Frequency, Recurring } from "../api";
import { formatCents } from "../format";

const monthFmt = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" });
const STEP_MONTHS: Partial<Record<Frequency, number>> = { mensuel: 1, bimestriel: 2, trimestriel: 3, semestriel: 6, annuel: 12 };

/** Échéances d'un récurrent dans un mois (à partir de sa prochaine date, sans dépasser sa date de fin). */
function datesIn(r: Recurring, y: number, m: number): Date[] {
  if (!r.next_date) return [];
  const out: Date[] = [];
  const end = r.end_date ? new Date(`${r.end_date}T12:00:00`) : null;
  const first = new Date(`${r.next_date}T12:00:00`);
  const day = first.getDate();
  const step = STEP_MONTHS[r.frequency];
  for (let k = 0; k < 400; k++) {
    let d: Date;
    if (step) {
      d = new Date(first.getFullYear(), first.getMonth() + step * k, 1, 12);
      d.setDate(Math.min(day, new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()));
    } else d = new Date(first.getTime() + 7 * k * 864e5);
    if (end && d > end) break;
    if (d.getFullYear() > y || (d.getFullYear() === y && d.getMonth() > m)) break;
    if (d.getFullYear() === y && d.getMonth() === m) out.push(d);
  }
  return out;
}

/** Calendrier des prélèvements et revenus récurrents, mois par mois. */
export function RecurringCalendar({ items }: { items: Recurring[] }) {
  const today = new Date();
  const [cursor, setCursor] = useState({ y: today.getFullYear(), m: today.getMonth() });
  const [picked, setPicked] = useState<number | null>(null);
  const active = items.filter((r) => r.status === "actif" || r.status === "suggere");
  const byDay = new Map<number, Recurring[]>();
  for (const r of active) for (const d of datesIn(r, cursor.y, cursor.m)) byDay.set(d.getDate(), [...(byDay.get(d.getDate()) ?? []), r]);
  const days = new Date(cursor.y, cursor.m + 1, 0).getDate();
  const lead = (new Date(cursor.y, cursor.m, 1).getDay() + 6) % 7; // lundi en premier
  const out = [...byDay.values()].flat().filter((r) => r.amount_cents < 0 && r.kind !== "virement").reduce((s, r) => s + r.amount_cents, 0);
  const inc = [...byDay.values()].flat().filter((r) => r.amount_cents > 0).reduce((s, r) => s + r.amount_cents, 0);
  const go = (n: number) => {
    const d = new Date(cursor.y, cursor.m + n, 1);
    setCursor({ y: d.getFullYear(), m: d.getMonth() });
    setPicked(null);
  };
  const isToday = (d: number) => cursor.y === today.getFullYear() && cursor.m === today.getMonth() && d === today.getDate();
  const list = picked !== null ? byDay.get(picked) ?? [] : [];
  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-title">🗓️ Calendrier des prélèvements</h2>
        <div className="flex items-center gap-1">
          <button className="btn-ghost px-2" onClick={() => go(-1)} aria-label="Mois précédent">‹</button>
          <span className="min-w-[9rem] text-center text-sm font-semibold capitalize">{monthFmt.format(new Date(cursor.y, cursor.m, 1))}</span>
          <button className="btn-ghost px-2" onClick={() => go(1)} aria-label="Mois suivant">›</button>
        </div>
      </div>
      <p className="text-sm">
        Prélèvements <b className="tabular-nums">{formatCents(out)}</b>
        {inc > 0 && <> · revenus <b className="tabular-nums text-emerald-600 dark:text-emerald-400">{formatCents(inc)}</b></>}
      </p>
      <div className="grid grid-cols-7 gap-1 text-center text-xs">
        {["L", "M", "M", "J", "V", "S", "D"].map((d, i) => <span key={i} className="muted py-1">{d}</span>)}
        {Array.from({ length: lead }, (_, i) => <span key={`x${i}`} />)}
        {Array.from({ length: days }, (_, i) => {
          const d = i + 1;
          const evs = byDay.get(d) ?? [];
          const sum = evs.reduce((s, r) => s + r.amount_cents, 0);
          return (
            <button
              key={d}
              className={`flex min-h-[3.25rem] flex-col items-center gap-0.5 rounded-lg p-1 transition ${evs.length ? "bg-slate-50 hover:bg-slate-100 dark:bg-white/5 dark:hover:bg-white/10" : ""} ${
                picked === d ? "ring-2 ring-accent-400" : ""
              } ${isToday(d) ? "font-bold text-accent-700 dark:text-accent-300" : ""}`}
              onClick={() => setPicked(evs.length ? (picked === d ? null : d) : null)}
              disabled={!evs.length}
            >
              <span>{d}</span>
              {evs.length > 0 && (
                <span className={`text-[10px] tabular-nums leading-tight ${sum > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-slate-600 dark:text-slate-300"}`}>
                  {Math.round(Math.abs(sum) / 100)}€
                </span>
              )}
            </button>
          );
        })}
      </div>
      {list.length > 0 && (
        <ul className="divide-y divide-slate-100 text-sm dark:divide-white/5">
          {list.map((r) => (
            <li key={r.id} className="flex justify-between gap-2 py-1.5">
              <span className="truncate">{r.label}{r.status === "suggere" && <span className="muted text-xs"> · à confirmer</span>}</span>
              <span className={`tabular-nums ${r.amount_cents > 0 ? "text-emerald-600 dark:text-emerald-400" : ""}`}>{formatCents(r.amount_cents)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Jour de paie : automatique (d'après l'historique) ou réglé à la main. */
export function PaydaySetting() {
  const [day, setDay] = useState<number | null | undefined>(undefined);
  useEffect(() => {
    api.get<{ day: number | null }>("/settings/payday").then((r) => setDay(r.day), () => setDay(null));
  }, []);
  if (day === undefined) return null;
  const save = async (v: number | null) => {
    setDay(v);
    await api.put("/settings/payday", { day: v });
  };
  return (
    <label className="flex flex-wrap items-center gap-2 text-sm">
      <span>💶 Jour de paie</span>
      <select className="input w-auto py-1.5" value={day ?? ""} onChange={(e) => save(e.target.value ? Number(e.target.value) : null)}>
        <option value="">Automatique (d'après l'historique)</option>
        {Array.from({ length: 31 }, (_, i) => <option key={i + 1} value={i + 1}>le {i + 1}</option>)}
      </select>
      <span className="muted text-xs">utilisé pour placer ton salaire dans les prévisions</span>
    </label>
  );
}

