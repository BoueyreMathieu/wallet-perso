import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Category, CategoryDeleteResult, CategoryKind, CategoryUsage, NATURE_LABELS, Nature, api } from "../api";
import { CategoryIcon, CategorySelect, shade, useCategories } from "../components/categories";

const KINDS: { key: CategoryKind; label: string; icon: string }[] = [
  { key: "depense", label: "Dépenses", icon: "💸" },
  { key: "revenu", label: "Revenus", icon: "💰" },
  { key: "transfert", label: "Transferts", icon: "🔄" },
];

const PALETTE = [
  "#ef4444", "#f97316", "#f59e0b", "#eab308", "#84cc16", "#22c55e", "#10b981", "#14b8a6",
  "#06b6d4", "#0ea5e9", "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7", "#d946ef", "#ec4899",
  "#f43f5e", "#a16207", "#64748b", "#334155",
];

const EMOJIS = [
  "🛒", "🍽️", "🍔", "🥐", "☕", "🍷", "🍻", "🏠", "🔑", "⚡", "💧", "📶", "🛋️", "🔨", "🚗", "⛽",
  "🚇", "✈️", "🚕", "🚲", "🅿️", "🔁", "📺", "🎧", "🎮", "☁️", "📰", "🏋️", "🎉", "🎬", "🎤", "🧳",
  "⚽", "🎲", "📚", "🎨", "🛍️", "📦", "👕", "👟", "💻", "🎁", "🩺", "💊", "🦷", "👓", "💅", "💇",
  "🏦", "🧾", "💶", "🛡️", "🎓", "🐾", "🤝", "👨‍👩‍👧", "👶", "💼", "📌", "💰", "📈", "🐷", "🔄", "🏷️",
];

/** Luminosité approximative (0–255) pour trier les nuances du plus clair au plus foncé. */
const lightness = (hex: string) => {
  const n = parseInt(hex.slice(1), 16);
  return 0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255);
};

interface Draft {
  id?: number;
  name: string;
  parent_id: number | null;
  kind: CategoryKind;
  color: string;
  icon: string;
  nature: Nature | "auto";
}

export default function Categories() {
  const { categories, reload } = useCategories();
  const [usage, setUsage] = useState<Map<number, CategoryUsage>>(new Map());
  const [kind, setKind] = useState<CategoryKind>("depense");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [deleting, setDeleting] = useState<Category | null>(null);
  const [msg, setMsg] = useState<{ text: string; error?: boolean; link?: boolean } | null>(null);

  const loadUsage = () =>
    api.get<CategoryUsage[]>("/categories/usage").then((rows) => setUsage(new Map(rows.map((u) => [u.id, u] as [number, CategoryUsage]))));
  useEffect(() => {
    loadUsage();
  }, []);

  const refresh = async () => {
    await reload();
    await loadUsage();
  };

  const parents = useMemo(() => categories.filter((c) => c.parent_id === null && c.kind === kind), [categories, kind]);
  const childrenOf = (id: number) => categories.filter((c) => c.parent_id === id);
  const opsOf = (id: number) => usage.get(id)?.transactions ?? 0;
  const totalOps = (p: Category) => opsOf(p.id) + childrenOf(p.id).reduce((s, c) => s + opsOf(c.id), 0);

  const newParent = () => setDraft({ name: "", parent_id: null, kind, color: PALETTE[categories.length % PALETTE.length], icon: "🏷️", nature: "auto" });
  const newChild = (p: Category) => setDraft({ name: "", parent_id: p.id, kind: p.kind, color: p.color ?? "#64748b", icon: "", nature: "auto" });
  const edit = (c: Category) =>
    setDraft({ id: c.id, name: c.name, parent_id: c.parent_id, kind: c.kind, color: c.color ?? "#64748b", icon: c.icon ?? "", nature: c.nature ?? "auto" });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Catégories</h1>
          <p className="muted text-sm">Crée, renomme, colore ou supprime tes catégories et sous-catégories.</p>
        </div>
        <button className="btn" onClick={newParent}>+ Nouvelle catégorie</button>
      </div>

      {msg && (
        <p className={`card text-sm ${msg.error ? "text-red-600" : ""}`}>
          {msg.text}{" "}
          {msg.link && (
            <Link to="/operations?a_categoriser=1" className="font-medium text-accent-600 underline dark:text-accent-300">
              Voir les opérations à catégoriser
            </Link>
          )}
        </p>
      )}

      <div className="flex gap-2">
        {KINDS.map((k) => (
          <button
            key={k.key}
            onClick={() => setKind(k.key)}
            className={`chip px-3 py-1.5 text-sm ${kind === k.key ? "bg-accent-600 text-white" : "bg-panel text-slate-600 shadow-soft dark:bg-panel-dark dark:text-slate-300"}`}
          >
            <span aria-hidden>{k.icon}</span> {k.label}
          </button>
        ))}
      </div>

      {draft && (
        <Editor
          draft={draft}
          onCancel={() => setDraft(null)}
          onSaved={async (text) => {
            setDraft(null);
            setMsg({ text });
            await refresh();
          }}
          onError={(text) => setMsg({ text, error: true })}
        />
      )}
      {deleting && (
        <DeletePanel
          cat={deleting}
          usage={usage}
          subs={childrenOf(deleting.id)}
          onCancel={() => setDeleting(null)}
          onDone={async (res) => {
            setDeleting(null);
            const parts = [`${res.deleted} catégorie(s) supprimée(s)`];
            if (res.transactions) {
              parts.push(
                res.moved_to !== null
                  ? `${res.transactions} opération(s) déplacée(s)`
                  : `${res.transactions} opération(s) libérée(s), dont ${res.to_categorize} à recatégoriser (les autres ont retrouvé une catégorie grâce à tes règles)`,
              );
            }
            setMsg({ text: parts.join(" · ") + ".", link: res.to_categorize > 0 });
            await refresh();
          }}
          onError={(text) => setMsg({ text, error: true })}
        />
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {parents.map((p) => (
          <section key={p.id} className="card space-y-3">
            <div className="flex items-center gap-3">
              <CategoryIcon id={p.id} size="lg" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">
                  {p.name} {p.protected && <span className="chip ml-1 bg-slate-100 text-slate-500 dark:bg-white/5">système</span>}
                </p>
                <p className="muted text-xs">
                  {totalOps(p)} opération(s)
                  {p.nature_effective && ` · ${NATURE_LABELS[p.nature_effective]}`}
                </p>
              </div>
              <span className="h-3 w-3 rounded-full" style={{ background: p.color ?? "#64748b" }} aria-hidden />
              <button className="btn-ghost px-2" onClick={() => edit(p)} aria-label={`Modifier ${p.name}`}>✏️</button>
              {!p.protected && (
                <button className="btn-ghost px-2" onClick={() => setDeleting(p)} aria-label={`Supprimer ${p.name}`}>🗑️</button>
              )}
            </div>
            <ul className="flex flex-wrap gap-2">
              {childrenOf(p.id).map((c) => (
                <li key={c.id} className="group flex items-center gap-1 rounded-full bg-slate-50 py-1 pl-1 pr-2 text-sm dark:bg-white/5">
                  <CategoryIcon id={c.id} size="sm" />
                  <span>{c.name}</span>
                  <span className="muted text-xs">{opsOf(c.id) || ""}</span>
                  <button className="ml-1 text-xs opacity-60 hover:opacity-100" onClick={() => edit(c)} aria-label={`Modifier ${c.name}`}>✏️</button>
                  {!c.protected && (
                    <button className="text-xs opacity-60 hover:opacity-100" onClick={() => setDeleting(c)} aria-label={`Supprimer ${c.name}`}>✕</button>
                  )}
                </li>
              ))}
              <li>
                <button className="rounded-full border border-dashed border-slate-300 px-3 py-1 text-sm muted hover:border-accent-400 hover:text-accent-600 dark:border-white/15" onClick={() => newChild(p)}>
                  + sous-catégorie
                </button>
              </li>
            </ul>
          </section>
        ))}
        {parents.length === 0 && <p className="card muted text-sm">Aucune catégorie de ce type pour l'instant.</p>}
      </div>
    </div>
  );
}

function Editor({
  draft,
  onCancel,
  onSaved,
  onError,
}: {
  draft: Draft;
  onCancel: () => void;
  onSaved: (msg: string) => void;
  onError: (msg: string) => void;
}) {
  const { categories, byId } = useCategories();
  const [d, setD] = useState<Draft>(draft);
  const [busy, setBusy] = useState(false);
  useEffect(() => setD(draft), [draft]);
  const original = d.id ? byId.get(d.id) : undefined;
  const isParent = d.parent_id === null;
  const hasChildren = d.id ? categories.some((c) => c.parent_id === d.id) : false;
  const parentOptions = categories.filter((c) => c.parent_id === null && c.id !== d.id);

  const save = async () => {
    setBusy(true);
    try {
      if (d.id) {
        const body: Record<string, unknown> = { name: d.name, color: d.color, icon: d.icon };
        if (original && d.parent_id !== original.parent_id) Object.assign(body, { move: true, parent_id: d.parent_id });
        if (isParent && original && d.kind !== original.kind) body.kind = d.kind;
        if (d.kind === "depense" && d.nature !== (original?.nature ?? "auto")) body.nature = d.nature;
        await api.patch(`/categories/${d.id}`, body);
        onSaved(`« ${d.name} » mise à jour.`);
      } else {
        const created = await api.post<Category>("/categories", { name: d.name, parent_id: d.parent_id, kind: isParent ? d.kind : null, color: d.color, icon: d.icon || null });
        if (d.kind === "depense" && d.nature !== "auto") await api.patch(`/categories/${created.id}`, { nature: d.nature });
        onSaved(`« ${d.name} » créée.`);
      }
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card space-y-4 ring-2 ring-accent-200 dark:ring-accent-800">
      <div className="flex items-center gap-3">
        <span className="grid h-12 w-12 place-items-center rounded-full text-2xl" style={{ background: `${d.color}26` }} aria-hidden>
          {d.icon || (d.parent_id ? byId.get(d.parent_id)?.icon : "") || "🏷️"}
        </span>
        <h2 className="font-semibold">
          {d.id ? "Modifier la catégorie" : isParent ? "Nouvelle catégorie" : `Nouvelle sous-catégorie de « ${byId.get(d.parent_id!)?.name} »`}
        </h2>
      </div>
      {original?.protected && (
        <p className="muted text-xs">Catégorie système (détection des virements internes) : seules l'icône et la couleur sont modifiables.</p>
      )}

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-sm">
          <span className="muted">Nom</span>
          <input className="input" value={d.name} disabled={original?.protected} onChange={(e) => setD({ ...d, name: e.target.value })} autoFocus />
        </label>
        {d.id && !original?.protected && !hasChildren && (
          <label className="space-y-1 text-sm">
            <span className="muted">Emplacement</span>
            <select
              className="input"
              value={d.parent_id ?? ""}
              onChange={(e) => {
                const pid = e.target.value === "" ? null : Number(e.target.value);
                const parent = pid !== null ? byId.get(pid) : undefined;
                setD({ ...d, parent_id: pid, kind: parent ? parent.kind : d.kind, color: parent?.color ?? d.color });
              }}
            >
              <option value="">Catégorie principale</option>
              {parentOptions.map((p) => (
                <option key={p.id} value={p.id}>Sous-catégorie de {p.name}</option>
              ))}
            </select>
          </label>
        )}
        {d.kind === "depense" && (
          <label className="space-y-1 text-sm">
            <span className="muted">Couche dans les prévisions</span>
            <select className="input" value={d.nature} onChange={(e) => setD({ ...d, nature: e.target.value as Nature | "auto" })}>
              <option value="auto">
                Automatique{original?.nature_effective && original.nature === null ? ` (${NATURE_LABELS[original.nature_effective].toLowerCase()})` : ""}
              </option>
              {(Object.keys(NATURE_LABELS) as Nature[]).map((n) => (
                <option key={n} value={n}>{NATURE_LABELS[n]}</option>
              ))}
            </select>
          </label>
        )}
        {isParent && !original?.protected && (
          <label className="space-y-1 text-sm">
            <span className="muted">Type</span>
            <select className="input" value={d.kind} onChange={(e) => setD({ ...d, kind: e.target.value as CategoryKind })}>
              {KINDS.map((k) => (
                <option key={k.key} value={k.key}>{k.icon} {k.label}</option>
              ))}
            </select>
          </label>
        )}
      </div>

      {!isParent ? (
        <div className="space-y-1 text-sm">
          <span className="muted">Couleur : une nuance de « {byId.get(d.parent_id!)?.name} »</span>
          <div className="flex flex-wrap items-center gap-2">
            {(() => {
              const base = byId.get(d.parent_id!)?.color ?? "#64748b";
              const options = [0, 2, 4, 6, 1, 3, 5, 7].map((i) => shade(base, i)).sort((a, b) => lightness(b) - lightness(a));
              return (
                <>
                  <button
                    onClick={() => setD({ ...d, color: base })}
                    className={`chip px-3 py-1 ${d.color.toLowerCase() === base.toLowerCase() ? "ring-2 ring-offset-2 ring-slate-400 dark:ring-offset-slate-900" : ""}`}
                    style={{ background: `${base}26` }}
                  >
                    <span className="h-3 w-3 rounded-full" style={{ background: base }} /> Automatique
                  </button>
                  {options.map((c) => (
                    <button
                      key={c}
                      onClick={() => setD({ ...d, color: c })}
                      className={`h-7 w-7 rounded-full transition ${d.color.toLowerCase() === c ? "ring-2 ring-offset-2 ring-slate-400 dark:ring-offset-slate-900" : ""}`}
                      style={{ background: c }}
                      aria-label={`Nuance ${c}`}
                    />
                  ))}
                </>
              );
            })()}
          </div>
          <p className="muted text-xs">« Automatique » : une nuance différente pour chaque sous-catégorie, choisie par l'appli.</p>
        </div>
      ) : (
      <div className="space-y-1 text-sm">
        <span className="muted">Couleur</span>
        <div className="flex flex-wrap items-center gap-2">
          {PALETTE.map((c) => (
            <button
              key={c}
              onClick={() => setD({ ...d, color: c })}
              className={`h-7 w-7 rounded-full transition ${d.color === c ? "ring-2 ring-offset-2 ring-slate-400 dark:ring-offset-slate-900" : ""}`}
              style={{ background: c }}
              aria-label={`Couleur ${c}`}
            />
          ))}
          <input type="color" className="h-8 w-10 cursor-pointer rounded border-0 bg-transparent" value={d.color} onChange={(e) => setD({ ...d, color: e.target.value })} aria-label="Couleur personnalisée" />
        </div>
      </div>
      )}

      <div className="space-y-1 text-sm">
        <span className="muted">Icône {!isParent && "(vide = celle de la catégorie principale)"}</span>
        <div className="flex flex-wrap gap-1">
          {EMOJIS.map((e) => (
            <button
              key={e}
              onClick={() => setD({ ...d, icon: e })}
              className={`grid h-9 w-9 place-items-center rounded-xl text-lg transition hover:bg-slate-100 dark:hover:bg-white/10 ${d.icon === e ? "bg-accent-100 ring-2 ring-accent-400 dark:bg-accent-500/20" : ""}`}
            >
              {e}
            </button>
          ))}
        </div>
        <input className="input mt-1 w-40" placeholder="ou colle un emoji" value={d.icon} maxLength={8} onChange={(e) => setD({ ...d, icon: e.target.value })} />
      </div>

      <div className="flex gap-2">
        <button className="btn" disabled={busy || !d.name.trim()} onClick={save}>Enregistrer</button>
        <button className="btn-ghost" onClick={onCancel}>Annuler</button>
      </div>
    </section>
  );
}

function DeletePanel({
  cat,
  subs,
  usage,
  onCancel,
  onDone,
  onError,
}: {
  cat: Category;
  subs: Category[];
  usage: Map<number, CategoryUsage>;
  onCancel: () => void;
  onDone: (r: CategoryDeleteResult) => void;
  onError: (msg: string) => void;
}) {
  const [mode, setMode] = useState<"free" | "move">("free");
  const [target, setTarget] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const ids = [cat.id, ...subs.map((s) => s.id)];
  const sum = (k: "transactions" | "rules" | "merchants") => ids.reduce((s, i) => s + (usage.get(i)?.[k] ?? 0), 0);
  const ops = sum("transactions");

  const run = async () => {
    setBusy(true);
    try {
      const q = mode === "move" && target !== null ? `?move_to=${target}` : "";
      onDone(await api.del<CategoryDeleteResult>(`/categories/${cat.id}${q}`));
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card space-y-3 ring-2 ring-red-200 dark:ring-red-900">
      <h2 className="font-semibold">Supprimer « {cat.name} »{subs.length > 0 && ` et ses ${subs.length} sous-catégorie(s)`} ?</h2>
      <p className="muted text-sm">
        {ops} opération(s), {sum("rules")} règle(s) et {sum("merchants")} vendeur(s) utilisent cette catégorie.
      </p>
      {ops + sum("rules") + sum("merchants") > 0 && (
        <div className="space-y-2 text-sm">
          <label className="flex items-start gap-2">
            <input type="radio" className="mt-1" checked={mode === "free"} onChange={() => setMode("free")} />
            <span>
              <b>Les remettre à catégoriser.</b> Tes autres règles sont réappliquées ; ce qui reste apparaît dans « À catégoriser ».
            </span>
          </label>
          <label className="flex items-start gap-2">
            <input type="radio" className="mt-1" checked={mode === "move"} onChange={() => setMode("move")} />
            <span><b>Tout déplacer vers une autre catégorie</b> (opérations, règles et vendeurs).</span>
          </label>
          {mode === "move" && <CategorySelect value={target} onChange={setTarget} exclude={ids} emptyLabel="Choisir la catégorie de destination…" />}
        </div>
      )}
      <div className="flex gap-2">
        <button className="btn bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:hover:bg-red-500" disabled={busy || (mode === "move" && target === null)} onClick={run}>
          Supprimer
        </button>
        <button className="btn-ghost" onClick={onCancel}>Annuler</button>
      </div>
    </section>
  );
}
