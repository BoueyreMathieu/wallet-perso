import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Advice, AdviceList, api } from "../api";
import { formatCents } from "../format";

const SEVERITY: Record<Advice["severity"], string> = {
  alerte: "border-rose-200 bg-rose-50/60 dark:border-rose-500/20 dark:bg-rose-500/10",
  conseil: "border-slate-100 dark:border-white/10",
  info: "border-slate-100 dark:border-white/10",
};

export function useAdvice() {
  const [data, setData] = useState<AdviceList | null>(null);
  const load = () => api.get<AdviceList>("/advice").then(setData, () => setData({ items: [], total_gain_cents: 0 }));
  useEffect(() => {
    load();
  }, []);
  const dismiss = async (a: Advice, days = 30) => {
    await api.post("/advice/dismiss", { id: a.id, days });
    setData((d) => (d ? { items: d.items.filter((x) => x.id !== a.id), total_gain_cents: d.total_gain_cents - a.gain_monthly_cents } : d));
  };
  return { data, dismiss, reload: load };
}

/** Un conseil : titre, détail, gain estimé, action (simuler dans Trésorerie ou ouvrir la page), « plus tard ». */
export function AdviceItem({ a, onDismiss, compact = false }: { a: Advice; onDismiss: (a: Advice) => void; compact?: boolean }) {
  const navigate = useNavigate();
  const act = () => {
    if (!a.action) return;
    if (a.action.type === "link") navigate(a.action.to);
    else navigate("/prevoir/tresorerie", { state: { scenario: a.action.scenario } });
  };
  return (
    <li className={`rounded-xl border p-3 ${SEVERITY[a.severity]}`}>
      <div className="flex items-start gap-3">
        <span aria-hidden className="text-xl leading-none">{a.icon}</span>
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <p className="font-semibold">{a.title}</p>
            {a.gain_monthly_cents > 0 && (
              <span className="text-sm font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">≈ {formatCents(a.gain_monthly_cents)} / mois</span>
            )}
          </div>
          {!compact && <p className="muted text-sm">{a.detail}</p>}
          <div className="flex flex-wrap gap-2 pt-1">
            {a.action && (
              <button className="btn px-3 py-1 text-xs" onClick={act}>
                {a.action.type === "scenario" ? "🎛️ " : ""}
                {a.action.label}
              </button>
            )}
            <button className="btn-ghost px-2 py-1 text-xs" onClick={() => onDismiss(a)} title="Ne plus afficher pendant 30 jours">
              Plus tard
            </button>
          </div>
        </div>
      </div>
    </li>
  );
}

/** Onglet Prévoir › Conseils. */
export function AdvicePage() {
  const { data, dismiss } = useAdvice();
  if (!data) return <p className="muted text-sm">Analyse en cours…</p>;
  return (
    <div className="space-y-4">
      <section className="card space-y-1">
        <h2 className="section-title">💡 Conseils tirés de tes données</h2>
        <p className="muted text-sm">
          {data.items.length === 0
            ? "Rien à signaler pour l'instant : les conseils apparaissent quand une catégorie dérive, qu'un abonnement augmente, que de l'argent dort…"
            : `${data.items.length} conseil(s)${data.total_gain_cents > 0 ? ` · jusqu'à ${formatCents(data.total_gain_cents)} par mois à gagner` : ""}.`}
        </p>
      </section>
      <ul className="space-y-3">
        {data.items.map((a) => <AdviceItem key={a.id} a={a} onDismiss={dismiss} />)}
      </ul>
    </div>
  );
}

/** Accueil : les 3 conseils les plus utiles. */
export function AdviceCard({ className = "" }: { className?: string }) {
  const { data, dismiss } = useAdvice();
  if (!data || data.items.length === 0) return null;
  return (
    <section className={`card space-y-3 ${className}`}>
      <div className="flex items-center justify-between">
        <h2 className="section-title">💡 Conseils</h2>
        <Link to="/prevoir/conseils" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-300">
          {data.items.length > 3 ? `Les ${data.items.length} →` : "Détail →"}
        </Link>
      </div>
      <ul className="space-y-2">
        {data.items.slice(0, 3).map((a) => <AdviceItem key={a.id} a={a} onDismiss={dismiss} compact />)}
      </ul>
    </section>
  );
}
