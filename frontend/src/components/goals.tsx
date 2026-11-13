import { FormEvent, useEffect, useState } from "react";
import { Account, api, Goal } from "../api";
import { formatCents, parseEuros } from "../format";

const monthYear = new Intl.DateTimeFormat("fr-FR", { month: "long", year: "numeric" });
const asDate = (iso: string) => new Date(`${iso}T12:00:00`);
const STATUS: Record<Goal["status"], { label: string; cls: string }> = {
  atteint: { label: "🎉 Atteint", cls: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" },
  en_avance: { label: "✅ En bonne voie", cls: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300" },
  en_retard: { label: "⏳ En retard", cls: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300" },
  en_cours: { label: "En cours", cls: "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300" },
};

export function useGoals() {
  const [goals, setGoals] = useState<Goal[] | null>(null);
  const reload = () => api.get<Goal[]>("/goals").then(setGoals, () => setGoals([]));
  useEffect(() => {
    reload();
  }, []);
  return { goals, reload };
}

function GoalForm({ goal, accounts, onDone }: { goal?: Goal; accounts: Account[]; onDone: () => void }) {
  const [name, setName] = useState(goal?.name ?? "");
  const [icon, setIcon] = useState(goal?.icon ?? "🎯");
  const [target, setTarget] = useState(goal ? String(goal.target_cents / 100).replace(".", ",") : "");
  const [date, setDate] = useState(goal?.target_date ?? "");
  const [account, setAccount] = useState<number | "">(goal?.account_id ?? "");
  const [saved, setSaved] = useState(goal ? String(goal.saved_cents / 100).replace(".", ",") : "");
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const cents = parseEuros(target);
    if (!name.trim() || !cents || cents <= 0) return setError("Un nom et un montant à atteindre.");
    const body = {
      name: name.trim(), icon: icon || null, target_cents: cents, target_date: date || null,
      account_id: account === "" ? null : account, saved_cents: account === "" ? Math.max(parseEuros(saved) ?? 0, 0) : 0,
    };
    try {
      if (goal) await api.patch(`/goals/${goal.id}`, body);
      else await api.post("/goals", body);
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return (
    <form className="space-y-2 rounded-xl bg-slate-50 p-3 text-sm dark:bg-white/5" onSubmit={submit}>
      <div className="grid gap-2 sm:grid-cols-[4rem_1fr_9rem]">
        <input className="input text-center" value={icon} onChange={(e) => setIcon(e.target.value)} aria-label="Icône" maxLength={4} />
        <input className="input" placeholder="Nom (ex. Voyage au Japon)" value={name} onChange={(e) => setName(e.target.value)} />
        <input className="input" inputMode="decimal" placeholder="Montant €" value={target} onChange={(e) => setTarget(e.target.value)} />
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <label className="flex items-center gap-2">
          <span className="muted shrink-0">Pour le</span>
          <input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <select className="input" value={account} onChange={(e) => setAccount(e.target.value === "" ? "" : Number(e.target.value))}>
          <option value="">Sans compte (je note ce que je mets de côté)</option>
          {accounts.map((a) => <option key={a.id} value={a.id}>Sur {a.name}</option>)}
        </select>
        {account === "" && (
          <label className="flex items-center gap-2 sm:col-span-2">
            <span className="muted shrink-0">Déjà mis de côté</span>
            <input className="input" inputMode="decimal" placeholder="0 €" value={saved} onChange={(e) => setSaved(e.target.value)} />
          </label>
        )}
      </div>
      {error && <p className="text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button className="btn" type="submit">{goal ? "Enregistrer" : "Ajouter l'objectif"}</button>
        <button className="btn-ghost" type="button" onClick={onDone}>Annuler</button>
      </div>
    </form>
  );
}

function GoalRow({ g, accounts, onChanged }: { g: Goal; accounts: Account[]; onChanged: () => void }) {
  const [edit, setEdit] = useState(false);
  const st = STATUS[g.status];
  return (
    <li className="space-y-2 py-3">
      <button type="button" className="block w-full space-y-1.5 text-left" onClick={() => setEdit(!edit)} aria-expanded={edit}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-2 font-medium">
            <span aria-hidden className="text-lg">{g.icon || "🎯"}</span>
            <span className="truncate">{g.name}</span>
            <span className={`chip text-[11px] ${st.cls}`}>{st.label}</span>
          </span>
          <span className="tabular-nums text-sm">
            <b>{formatCents(g.current_cents)}</b> <span className="muted">/ {formatCents(g.target_cents)}</span>
          </span>
        </div>
        <div className="h-2.5 rounded-full bg-slate-100 dark:bg-white/10" role="progressbar" aria-valuenow={Math.round(g.progress * 100)} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full rounded-full bg-accent-500" style={{ width: `${Math.max(g.progress * 100, g.current_cents > 0 ? 2 : 0)}%` }} />
        </div>
        <p className="muted text-xs">
          {g.account_name ? `Sur ${g.account_name}` : "Mis de côté à la main"}
          {g.target_date && ` · pour ${monthYear.format(asDate(g.target_date))}`}
          {g.monthly_needed_cents !== null && ` · ${formatCents(g.monthly_needed_cents)} / mois à mettre de côté`}
          {g.status !== "atteint" && g.monthly_rate_cents !== null && g.monthly_rate_cents > 0 && ` · à ton rythme (${formatCents(g.monthly_rate_cents)} / mois)`}
          {g.status !== "atteint" && g.eta && ` : atteint en ${monthYear.format(asDate(g.eta))}`}
        </p>
      </button>
      {edit && (
        <div className="space-y-2">
          <GoalForm goal={g} accounts={accounts} onDone={() => { setEdit(false); onChanged(); }} />
          <button className="btn-ghost text-sm text-red-600" onClick={async () => { await api.del(`/goals/${g.id}`); onChanged(); }}>Supprimer l'objectif</button>
        </div>
      )}
    </li>
  );
}

/** Onglet Prévoir › Objectifs. */
export function GoalsPage() {
  const { goals, reload } = useGoals();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [adding, setAdding] = useState(false);
  useEffect(() => {
    api.get<Account[]>("/accounts").then((l) => setAccounts(l.filter((a) => !a.is_archived)));
  }, []);
  const needed = (goals ?? []).reduce((s, g) => s + (g.status !== "atteint" ? g.monthly_needed_cents ?? 0 : 0), 0);
  return (
    <section className="card space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="section-title">🏁 Objectifs d'épargne</h2>
        {!adding && <button className="btn px-3 py-1.5 text-sm" onClick={() => setAdding(true)}>+ Nouvel objectif</button>}
      </div>
      {needed > 0 && <p className="muted text-sm">Pour tenir tes dates : {formatCents(needed)} à mettre de côté chaque mois (simulable dans 📈 Projection).</p>}
      {adding && <GoalForm accounts={accounts} onDone={() => { setAdding(false); reload(); }} />}
      {goals && goals.length === 0 && !adding && (
        <p className="muted text-sm">
          Un voyage, un apport, un matelas de sécurité… Rattache l'objectif à un livret : sa progression suit le solde du compte. Plusieurs
          objectifs sur le même compte se le partagent dans l'ordre.
        </p>
      )}
      <ul className="divide-y divide-slate-100 dark:divide-white/5">
        {(goals ?? []).map((g) => <GoalRow key={g.id} g={g} accounts={accounts} onChanged={reload} />)}
      </ul>
    </section>
  );
}

/** Accueil : les objectifs en cours (3 au plus). */
export function GoalsCard({ className = "" }: { className?: string }) {
  const { goals } = useGoals();
  const open = (goals ?? []).filter((g) => g.status !== "atteint");
  if (open.length === 0) return null;
  return (
    <section className={`card space-y-3 ${className}`}>
      <div className="flex items-center justify-between">
        <h2 className="section-title">🏁 Objectifs</h2>
        <a href="/prevoir/objectifs" className="text-xs font-medium text-accent-600 hover:underline dark:text-accent-300">Tous →</a>
      </div>
      <ul className="space-y-3">
        {open.slice(0, 3).map((g) => (
          <li key={g.id} className="space-y-1 text-sm">
            <div className="flex justify-between gap-2">
              <span className="truncate">{g.icon || "🎯"} {g.name}</span>
              <span className="tabular-nums">{Math.round(g.progress * 100)} %</span>
            </div>
            <div className="h-2 rounded-full bg-slate-100 dark:bg-white/10">
              <div className="h-full rounded-full bg-accent-500" style={{ width: `${Math.max(g.progress * 100, 2)}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
