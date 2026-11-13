import { useEffect, useState } from "react";
import { api, SplitSummary } from "../api";
import { formatCents, parseEuros } from "../format";
import { CategorySelect } from "./categories";

interface Row {
  amount: string;
  category_id: number | null;
  person: string;
  shared: boolean;
}
const euros = (cents: number) => (Math.abs(cents) / 100).toFixed(2).replace(".", ",");

/** Découper une opération en plusieurs catégories, ou en partager une partie (avancée pour quelqu'un : « On me doit »). */
export function SplitEditor({ txId, category, onDone }: { txId: number; category: number | null; onDone: () => void }) {
  const [s, setS] = useState<SplitSummary | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [people, setPeople] = useState(2);
  useEffect(() => {
    api.get<SplitSummary>(`/transactions/${txId}/split`).then((r) => {
      setS(r);
      setRows(
        r.parts.length
          ? r.parts.map((p) => ({ amount: euros(p.amount_cents), category_id: p.category_id, person: p.person ?? "", shared: !!p.person }))
          : [
              { amount: euros(r.amount_cents), category_id: category, person: "", shared: false },
              { amount: "", category_id: category, person: "", shared: false },
            ],
      );
    });
  }, [txId, category]);
  if (!s) return null;
  const sign = s.amount_cents < 0 ? -1 : 1;
  const total = Math.abs(s.amount_cents);
  const used = rows.reduce((t, r) => t + (parseEuros(r.amount) ?? 0), 0);
  const left = total - used;
  const set = (i: number, patch: Partial<Row>) => setRows(rows.map((r, k) => (k === i ? { ...r, ...patch } : r)));

  const shareEqually = () => {
    const mine = Math.round(total / people);
    setRows([
      { amount: euros(mine), category_id: category, person: "", shared: false },
      { amount: euros(total - mine), category_id: category, person: rows.find((r) => r.shared)?.person || "", shared: true },
    ]);
  };
  const save = async () => {
    setError(null);
    const parts = rows
      .filter((r) => (parseEuros(r.amount) ?? 0) > 0)
      .map((r) => ({ amount_cents: sign * (parseEuros(r.amount) ?? 0), category_id: r.category_id, person: r.shared ? r.person.trim() || "Quelqu'un" : null }));
    try {
      await api.post(`/transactions/${txId}/split`, { parts });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const undo = async () => {
    await api.del(`/transactions/${txId}/split`);
    onDone();
  };

  return (
    <div className="space-y-2 rounded-xl border border-slate-200 p-3 dark:border-white/10">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-medium">✂️ Découper {formatCents(s.amount_cents)}</p>
        {s.amount_cents < 0 && (
          <span className="flex items-center gap-1 text-xs">
            Partager entre
            <select className="input w-16 py-1" value={people} onChange={(e) => setPeople(Number(e.target.value))} aria-label="Nombre de personnes">
              {[2, 3, 4, 5, 6, 8, 10].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={shareEqually}>parts égales</button>
          </span>
        )}
      </div>
      <ul className="space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="space-y-1 rounded-lg bg-slate-50 p-2 dark:bg-white/5">
            <div className="flex gap-2">
              <input className="input w-28 text-right" inputMode="decimal" placeholder="0,00" value={r.amount} onChange={(e) => set(i, { amount: e.target.value })} aria-label="Montant de la part" />
              <div className="min-w-0 flex-1">
                <CategorySelect value={r.category_id} onChange={(id) => set(i, { category_id: id })} />
              </div>
              {rows.length > 2 && (
                <button type="button" className="btn-ghost px-2" onClick={() => setRows(rows.filter((_, k) => k !== i))} aria-label="Retirer la part">✕</button>
              )}
            </div>
            {s.amount_cents < 0 && (
              <label className="flex flex-wrap items-center gap-2 text-xs">
                <input type="checkbox" checked={r.shared} onChange={(e) => set(i, { shared: e.target.checked })} />
                Avancé pour quelqu'un (on me le doit)
                {r.shared && (
                  <input className="input w-40 py-1 text-xs" placeholder="Qui ?" value={r.person} onChange={(e) => set(i, { person: e.target.value })} />
                )}
              </label>
            )}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => setRows([...rows, { amount: left > 0 ? euros(left) : "", category_id: category, person: "", shared: false }])}>
          + Une part
        </button>
        <span className={`ml-auto text-xs tabular-nums ${left === 0 ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600"}`}>
          {left === 0 ? "✓ le compte est bon" : left > 0 ? `reste ${formatCents(left)} à répartir` : `${formatCents(-left)} de trop`}
        </span>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <div className="flex flex-wrap gap-2">
        <button className="btn" disabled={left !== 0} onClick={save}>Enregistrer le découpage</button>
        {s.split && <button className="btn-ghost text-red-600" onClick={undo}>Annuler le découpage</button>}
        <button className="btn-ghost" onClick={onDone}>Fermer</button>
      </div>
    </div>
  );
}
