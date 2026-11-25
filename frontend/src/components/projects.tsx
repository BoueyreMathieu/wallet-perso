/** Prévoir › Projets (suivi par étiquette) et Prévoir › Contrats (échéances, préavis). */
import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Contract, Project, Recurring, api } from "../api";
import { formatCents, parseEuros } from "../format";
import { CategoryIcon, useCategories } from "./categories";
import { LEVELS } from "./planning";
import { TagSelect, useTags } from "./tags";

const dateFr = (iso: string | null) => (iso ? new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR") : "");
const monthFr = new Intl.DateTimeFormat("fr-FR", { month: "short", year: "2-digit" });

// --- Projets --------------------------------------------------------------------------------------

export function ProjectsPage() {
  const [items, setItems] = useState<Project[] | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const load = () => api.get<Project[]>(`/projects${showArchived ? "?archived=true" : ""}`).then(setItems, (e) => setMsg((e as Error).message));
  useEffect(() => {
    load();
  }, [showArchived]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-4">
      <p className="muted px-1 text-sm">
        Un projet suit tout ce qui porte une étiquette (« Voyage », « Travaux »…), toutes catégories confondues, avec un budget total
        et des dates si tu veux. Pose l'étiquette sur les opérations (ou sur un vendeur) depuis Opérations.
      </p>
      {msg && <p className="card text-sm text-red-600">{msg}</p>}
      {items?.map((p) => <ProjectCard key={p.id} p={p} onChanged={load} />)}
      {items?.length === 0 && <p className="card muted text-sm">Aucun projet suivi pour l'instant.</p>}
      <NewProject onCreated={load} onError={setMsg} />
      <label className="muted flex items-center gap-2 px-1 text-xs">
        <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} /> Voir aussi les projets terminés
      </label>
    </div>
  );
}

function NewProject({ onCreated, onError }: { onCreated: () => void; onError: (m: string | null) => void }) {
  const { reload } = useTags();
  const [tag, setTag] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [budget, setBudget] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const cents = budget.trim() ? parseEuros(budget) : null;
    if (budget.trim() && !cents) return onError("Budget invalide (ex. 1 200)");
    try {
      await api.post("/projects", {
        tag_id: tag, name: tag === null ? name : null, budget_cents: cents, start_date: start || null, end_date: end || null,
      });
      setTag(null); setName(""); setBudget(""); setStart(""); setEnd("");
      onError(null);
      reload?.();
      onCreated();
    } catch (err) {
      onError((err as Error).message);
    }
  };
  return (
    <form className="card space-y-3" onSubmit={submit}>
      <h2 className="section-title">➕ Nouveau projet</h2>
      <div className="grid gap-2 sm:grid-cols-2">
        <TagSelect value={tag} onChange={setTag} emptyLabel="Nouvelle étiquette…" />
        {tag === null && <input className="input" placeholder="Nom (ex. Voyage Japon)" value={name} onChange={(e) => setName(e.target.value)} maxLength={50} />}
        <input className="input" inputMode="decimal" placeholder="Budget total € (facultatif)" value={budget} onChange={(e) => setBudget(e.target.value)} />
        <label className="flex items-center gap-2 text-sm"><span className="muted w-8">Du</span><input className="input" type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label className="flex items-center gap-2 text-sm"><span className="muted w-8">au</span><input className="input" type="date" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
      </div>
      <button className="btn">Suivre ce projet</button>
    </form>
  );
}

function ProjectCard({ p, onChanged }: { p: Project; onChanged: () => void }) {
  const { byId } = useCategories();
  const [edit, setEdit] = useState(false);
  const [budget, setBudget] = useState(p.budget_cents ? String(p.budget_cents / 100).replace(".", ",") : "");
  const [start, setStart] = useState(p.start_date ?? "");
  const [end, setEnd] = useState(p.end_date ?? "");
  const lv = LEVELS[p.level];
  const pct = p.budget_cents ? Math.min(p.net_cents / p.budget_cents, 1.2) : null;
  const save = async () => {
    const cents = budget.trim() ? parseEuros(budget) : 0;
    await api.patch(`/projects/${p.id}`, { budget_cents: cents ?? 0, start_date: start || null, end_date: end || null });
    setEdit(false);
    onChanged();
  };
  const maxMonth = Math.max(1, ...p.by_month.map((m) => Math.abs(m.net_cents)));
  return (
    <section className={`card space-y-3 ${p.archived ? "opacity-70" : ""}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex items-center gap-2 text-lg font-semibold">
            <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: p.color ?? "#7552f5" }} aria-hidden />
            🧳 {p.name}
          </p>
          <p className="muted text-xs">
            {p.start_date || p.end_date ? `${p.start_date ? `du ${dateFr(p.start_date)}` : ""}${p.end_date ? ` au ${dateFr(p.end_date)}` : ""}` : "sans dates"}
            {p.days_left !== null && ` · encore ${p.days_left} jour(s)`} · {p.count} opération(s)
          </p>
        </div>
        <div className="text-right tabular-nums">
          <p className={`text-xl font-bold ${p.budget_cents ? lv.text : ""}`}>{formatCents(p.net_cents)}</p>
          {p.budget_cents ? <p className="muted text-xs">sur {formatCents(p.budget_cents)} · {lv.icon} {p.remaining_cents! >= 0 ? `reste ${formatCents(p.remaining_cents!)}` : `dépassé de ${formatCents(-p.remaining_cents!)}`}</p>
            : <p className="muted text-xs">dépensé{p.refunds_cents > 0 ? ` (dont ${formatCents(p.refunds_cents)} remboursés)` : ""}</p>}
        </div>
      </div>
      {pct !== null && (
        <div className="h-2 overflow-hidden rounded-full bg-slate-100 dark:bg-white/10">
          <div className={`h-full rounded-full ${lv.bar}`} style={{ width: `${Math.max(Math.min(pct, 1), 0) * 100}%` }} />
        </div>
      )}
      {p.by_category.length > 0 && (
        <ul className="flex flex-wrap gap-1.5 text-xs">
          {p.by_category.map((c) => (
            <li key={c.category_id ?? "none"} className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 dark:bg-white/5">
              {c.category_id !== null && <CategoryIcon id={c.category_id} size="sm" />}
              <span>{c.category_id === null ? "À catégoriser" : byId.get(c.category_id)?.name ?? "?"}</span>
              <b className="tabular-nums">{formatCents(c.net_cents)}</b>
            </li>
          ))}
        </ul>
      )}
      {p.by_month.length > 1 && (
        <div className="flex h-16 items-end gap-1" aria-label="Dépenses du projet par mois">
          {p.by_month.map((m) => (
            <div key={m.month} className="flex min-w-0 flex-1 flex-col items-center gap-0.5" title={`${m.month} : ${formatCents(m.net_cents)}`}>
              <div className="w-full max-w-[28px] rounded-t bg-accent-500/70" style={{ height: `${Math.max(2, (Math.abs(m.net_cents) / maxMonth) * 44)}px` }} />
              <span className="muted truncate text-[10px]">{monthFr.format(new Date(`${m.month}-01T12:00:00`))}</span>
            </div>
          ))}
        </div>
      )}
      <div className="flex flex-wrap gap-1">
        <Link className="btn-ghost px-2 text-sm" to={`/operations?etiquette=${p.tag_id}`}>Voir les opérations</Link>
        <button className="btn-ghost px-2 text-sm" onClick={() => setEdit(!edit)}>✎ Modifier</button>
        <button className="btn-ghost px-2 text-sm" onClick={async () => { await api.patch(`/projects/${p.id}`, { archived: !p.archived }); onChanged(); }}>
          {p.archived ? "Réactiver" : "Terminé"}
        </button>
        <button className="btn-ghost px-2 text-sm text-red-600" onClick={async () => {
          if (!confirm(`Ne plus suivre « ${p.name} » comme projet ? L'étiquette et les opérations restent.`)) return;
          await api.del(`/projects/${p.id}`);
          onChanged();
        }}>Ne plus suivre</button>
      </div>
      {edit && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-slate-50 p-2 dark:bg-white/5">
          <input className="input w-36" inputMode="decimal" placeholder="Budget total €" value={budget} onChange={(e) => setBudget(e.target.value)} aria-label="Budget total" />
          <input className="input w-auto" type="date" value={start} onChange={(e) => setStart(e.target.value)} aria-label="Début" />
          <input className="input w-auto" type="date" value={end} onChange={(e) => setEnd(e.target.value)} aria-label="Fin" />
          <button className="btn" onClick={save}>Enregistrer</button>
        </div>
      )}
    </section>
  );
}

// --- Contrats -------------------------------------------------------------------------------------

const STATE: Record<Contract["state"], { label: string; cls: string }> = {
  bientot: { label: "À décider bientôt", cls: "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-200" },
  ok: { label: "Tranquille", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-200" },
  engage: { label: "Trop tard pour cette échéance", cls: "bg-slate-100 text-slate-600 dark:bg-white/10 dark:text-slate-300" },
  termine: { label: "Échéance passée", cls: "bg-slate-100 text-slate-500 dark:bg-white/10 dark:text-slate-400" },
};

export function ContractsPage() {
  const [items, setItems] = useState<Contract[] | null>(null);
  const [series, setSeries] = useState<Recurring[]>([]);
  const load = () => api.get<Contract[]>("/contracts").then(setItems, () => setItems([]));
  useEffect(() => {
    load();
    api.get<{ items: Recurring[] }>("/recurring").then((r) => setSeries(r.items.filter((s) => s.amount_cents < 0)), () => undefined);
  }, []);
  const linked = new Set((items ?? []).map((c) => c.recurring_id));
  return (
    <div className="space-y-4">
      <p className="muted px-1 text-sm">
        Assurance, box, énergie, mutuelle… Note la date d'échéance (ou de renouvellement) et le préavis : l'appli te prévient avant la
        date limite pour résilier. Avec une reconduction tacite, l'échéance avance toute seule chaque période.
      </p>
      {(items ?? []).map((c) => <ContractCard key={c.id} c={c} onChanged={load} />)}
      {items?.length === 0 && <p className="card muted text-sm">Aucun contrat pour l'instant.</p>}
      <section className="card space-y-2">
        <h2 className="section-title">➕ Ajouter un contrat</h2>
        <ContractForm series={series.filter((s) => !linked.has(s.id))} onSaved={load} />
      </section>
    </div>
  );
}

function ContractCard({ c, onChanged }: { c: Contract; onChanged: () => void }) {
  const [edit, setEdit] = useState(false);
  const st = STATE[c.state];
  return (
    <section className="card space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2 font-semibold">
            📄 {c.label} <span className={`rounded-full px-2 py-0.5 text-xs font-normal ${st.cls}`}>{st.label}</span>
          </p>
          <p className="muted text-xs">
            {c.renew_months ? `Se reconduit le ${dateFr(c.renewal_date)}` : `Échéance le ${dateFr(c.renewal_date)}`} · préavis {c.notice_days} j
            {c.recurring_label && c.recurring_label !== c.label ? ` · récurrent « ${c.recurring_label} »` : ""}
          </p>
        </div>
        <div className="text-right">
          {c.amount_cents !== null && <p className="font-semibold tabular-nums">{formatCents(c.amount_cents)}</p>}
          {c.state !== "termine" && (
            <p className={`text-xs ${c.state === "bientot" ? "font-semibold text-amber-700 dark:text-amber-300" : "muted"}`}>
              {c.days_to_deadline >= 0 ? `Résiliable jusqu'au ${dateFr(c.deadline)} (${c.days_to_deadline} j)` : `Date limite passée (${dateFr(c.deadline)})`}
            </p>
          )}
        </div>
      </div>
      {c.note && <p className="muted text-xs">📝 {c.note}</p>}
      <div className="flex gap-1">
        <button className="btn-ghost px-2 text-sm" onClick={() => setEdit(!edit)}>✎ Modifier</button>
        <button className="btn-ghost px-2 text-sm text-red-600" onClick={async () => {
          if (!confirm(`Supprimer le contrat « ${c.label} » ?`)) return;
          await api.del(`/contracts/${c.id}`);
          onChanged();
        }}>Supprimer</button>
      </div>
      {edit && <ContractForm contract={c} onSaved={() => { setEdit(false); onChanged(); }} />}
    </section>
  );
}

/** Formulaire de contrat : nouveau (depuis un récurrent ou seul), ou modification. */
export function ContractForm({ contract, series = [], recurring, onSaved }: {
  contract?: Contract; series?: Recurring[]; recurring?: Recurring; onSaved: () => void;
}) {
  const [rec, setRec] = useState<number | null>(recurring?.id ?? null);
  const [label, setLabel] = useState(contract?.label ?? "");
  const [renewal, setRenewal] = useState(contract?.renewal_date ?? "");
  const [notice, setNotice] = useState(String(contract?.notice_days ?? 30));
  const [renew, setRenew] = useState(String(contract ? contract.renew_months ?? 0 : 12));
  const [note, setNote] = useState(contract?.note ?? "");
  const [msg, setMsg] = useState<string | null>(null);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!renewal) return setMsg("Indique la date d'échéance ou de renouvellement.");
    const body = { label: label.trim() || null, renewal_date: renewal, notice_days: Number(notice) || 0, renew_months: Number(renew) || null, note: note.trim() || null };
    try {
      if (contract) await api.patch(`/contracts/${contract.id}`, { ...body, renew_months: Number(renew) || 0, label: label.trim() || contract.label });
      else await api.post("/contracts", { ...body, recurring_id: rec });
      setMsg(null);
      onSaved();
    } catch (err) {
      setMsg((err as Error).message);
    }
  };
  return (
    <form className="grid gap-2 text-sm sm:grid-cols-2" onSubmit={submit}>
      {!contract && !recurring && (
        <select className="input sm:col-span-2" value={rec ?? ""} onChange={(e) => setRec(e.target.value ? Number(e.target.value) : null)}>
          <option value="">Sans récurrent (contrat seul)</option>
          {series.map((s) => <option key={s.id} value={s.id}>Depuis le récurrent « {s.label} » ({formatCents(s.amount_cents)})</option>)}
        </select>
      )}
      <input className="input" placeholder={rec || recurring ? "Nom (par défaut : celui du récurrent)" : "Nom (ex. Assurance auto)"} value={label} onChange={(e) => setLabel(e.target.value)} />
      <label className="flex items-center gap-2"><span className="muted shrink-0">Échéance</span><input className="input" type="date" value={renewal} onChange={(e) => setRenewal(e.target.value)} /></label>
      <label className="flex items-center gap-2"><span className="muted shrink-0">Préavis</span><input className="input w-20" inputMode="numeric" value={notice} onChange={(e) => setNotice(e.target.value)} /><span className="muted">jours</span></label>
      <select className="input" value={renew} onChange={(e) => setRenew(e.target.value)} aria-label="Reconduction">
        <option value="12">Reconduction tacite chaque année</option>
        <option value="1">Reconduction tacite chaque mois</option>
        <option value="24">Reconduction tacite tous les 2 ans</option>
        <option value="0">Pas de reconduction (s'arrête)</option>
      </select>
      <input className="input sm:col-span-2" placeholder="Note (n° de contrat, adresse de résiliation…)" value={note} onChange={(e) => setNote(e.target.value)} maxLength={300} />
      <div className="sm:col-span-2 flex items-center gap-2">
        <button className="btn">{contract ? "Enregistrer" : "Ajouter"}</button>
        {msg && <span className="text-red-600">{msg}</span>}
      </div>
    </form>
  );
}
