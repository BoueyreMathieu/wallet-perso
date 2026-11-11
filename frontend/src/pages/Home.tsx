import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AccountType, NetWorth, api } from "../api";
import { ACCOUNT_TYPE_LABELS, formatCents } from "../format";

export default function Home() {
  const [nw, setNw] = useState<NetWorth | null>(null);

  useEffect(() => {
    api.get<NetWorth>("/accounts/net-worth").then(setNw);
  }, []);

  if (!nw) return null;
  const types = Object.entries(nw.by_type).sort((a, b) => b[1] - a[1]);

  return (
    <div className="space-y-4">
      <section className="card">
        <p className="text-sm text-slate-500">Patrimoine net</p>
        <p className={`text-3xl font-semibold tabular-nums ${nw.total_cents < 0 ? "text-red-600" : ""}`}>
          {formatCents(nw.total_cents)}
        </p>
      </section>

      {types.length === 0 ? (
        <section className="card text-sm text-slate-500">
          Aucun solde pour l'instant. <Link to="/comptes" className="underline">Ajoute ton premier compte</Link>.
        </section>
      ) : (
        <section className="card divide-y divide-slate-100 dark:divide-slate-800">
          {types.map(([type, cents]) => (
            <div key={type} className="flex justify-between py-2">
              <span>{ACCOUNT_TYPE_LABELS[type as AccountType] ?? type}</span>
              <span className={`tabular-nums ${cents < 0 ? "text-red-600" : ""}`}>{formatCents(cents)}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
