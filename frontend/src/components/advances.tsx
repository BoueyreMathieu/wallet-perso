import { useEffect, useState } from "react";
import { AdvanceItem, api, Transaction } from "../api";
import { formatCents, formatDate } from "../format";

/** « On me doit » : parts avancées pour quelqu'un (resto partagé…) ; marquer remboursé avec l'argent reçu. */
export function AdvancesCard({ className = "", showEmpty = false }: { className?: string; showEmpty?: boolean }) {
  const [items, setItems] = useState<AdvanceItem[] | null>(null);
  const [settling, setSettling] = useState<number | null>(null);
  const [incomes, setIncomes] = useState<Transaction[]>([]);
  const load = () => api.get<AdvanceItem[]>("/advances").then(setItems, () => setItems([]));
  useEffect(() => {
    load();
  }, []);
  const open = (items ?? []).filter((a) => !a.settled);
  if (!items || (!showEmpty && open.length === 0)) return null;
  const startSettle = async (id: number) => {
    setSettling(id);
    const page = await api.get<{ items: Transaction[] }>("/transactions?limit=60");
    setIncomes(page.items.filter((t) => t.amount_cents > 0 && t.counted && !t.is_transfer));
  };
  const settle = async (id: number, txId: number | null) => {
    await api.post(`/advances/${id}/settle`, { transaction_id: txId });
    setSettling(null);
    load();
  };
  const total = open.reduce((s, a) => s + a.amount_cents, 0);
  return (
    <section className={`card space-y-2 ${className}`}>
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="section-title">🤝 On me doit</h2>
        {total > 0 && <span className="font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">{formatCents(total)}</span>}
      </div>
      {open.length === 0 && <p className="muted text-sm">Personne ne te doit rien. Pour partager une dépense : Opérations › l'opération › ✂️ Découper.</p>}
      <ul className="divide-y divide-slate-100 text-sm dark:divide-white/5">
        {open.map((a) => (
          <li key={a.id} className="space-y-2 py-2">
            <div className="flex items-center gap-2">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{a.person ?? "Quelqu'un"}</p>
                <p className="muted text-xs">{a.label} · {formatDate(a.date)}</p>
              </div>
              <span className="tabular-nums">{formatCents(a.amount_cents)}</span>
              <button className="btn-ghost px-2 py-1 text-xs" onClick={() => (settling === a.id ? setSettling(null) : startSettle(a.id))}>Remboursé ?</button>
            </div>
            {settling === a.id && (
              <div className="space-y-1 rounded-lg bg-slate-50 p-2 text-xs dark:bg-white/5">
                <p className="muted">Choisis l'argent reçu (il ne comptera pas comme un revenu) :</p>
                <ul className="max-h-48 space-y-1 overflow-y-auto">
                  {incomes.map((t) => (
                    <li key={t.id}>
                      <button className="flex w-full justify-between gap-2 rounded px-1 py-1 text-left hover:bg-white dark:hover:bg-white/10" onClick={() => settle(a.id, t.id)}>
                        <span className="truncate">{formatDate(t.booked_at)} · {t.label}</span>
                        <span className="tabular-nums text-emerald-600">{formatCents(t.amount_cents)}</span>
                      </button>
                    </li>
                  ))}
                  {incomes.length === 0 && <li className="muted">Aucune entrée récente.</li>}
                </ul>
                <button className="btn-ghost px-2 py-1 text-xs" onClick={() => settle(a.id, null)}>Réglé autrement (espèces…)</button>
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
