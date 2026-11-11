import { useEffect, useState } from "react";
import { Account, ImportBatch, api } from "../api";
import { CategorySelect, useCategories } from "../components/categories";
import { TagChip, useTags } from "../components/tags";
import { formatCents } from "../format";

const SOURCE_LABELS: Record<string, string> = {
  csv_credit_agricole: "Crédit Agricole (CSV)",
  csv_paypal: "PayPal (CSV)",
};

export default function Data() {
  const { pathOf } = useCategories();
  const [imports, setImports] = useState<ImportBatch[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [category, setCategory] = useState<number | null>(null);
  const [confirmWord, setConfirmWord] = useState("");
  const [keepAccounts, setKeepAccounts] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    api.get<ImportBatch[]>("/data/imports").then(setImports);
    api.get<Account[]>("/accounts?include_archived=true").then(setAccounts);
  };
  useEffect(load, []);

  const run = async (question: string, action: () => Promise<{ updated: number }>, done: (n: number) => string) => {
    if (question && !confirm(question)) return;
    try {
      const r = await action();
      setMsg(done(r.updated));
    } catch (err) {
      setMsg((err as Error).message);
    }
    load();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Données</h1>
      {msg && <p className="card text-sm">{msg}</p>}

      <section className="card space-y-2">
        <h2 className="font-medium">Imports</h2>
        <p className="text-sm text-slate-500">Annuler un import supprime les opérations qu'il avait ajoutées.</p>
        <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
          {imports.length === 0 && <li className="py-2 text-slate-500">Aucun import.</li>}
          {imports.map((b) => (
            <li key={b.id} className="flex items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <p className="truncate">
                  {SOURCE_LABELS[b.source] ?? b.source} → {b.account_name ?? "compte supprimé"}
                </p>
                <p className="text-xs text-slate-500">
                  {new Date(b.started_at).toLocaleString("fr-FR")} · {b.rows_imported} ajoutée{b.rows_imported > 1 ? "s" : ""} sur{" "}
                  {b.rows_total}
                  {b.filename && ` · ${b.filename}`}
                </p>
              </div>
              <button
                className="btn-ghost shrink-0 text-red-600"
                onClick={() =>
                  run(
                    `Annuler cet import et supprimer ses ${b.rows_imported} opérations ?`,
                    () => api.del(`/data/imports/${b.id}`),
                    () => "Import annulé.",
                  )
                }
              >
                Annuler
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="card space-y-2">
        <h2 className="font-medium">Comptes</h2>
        <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
          {accounts.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span>
                {a.name}
                {a.is_archived && <span className="text-slate-500"> (archivé)</span>}
              </span>
              <span className="flex gap-1">
                <button
                  className="btn-ghost"
                  onClick={() =>
                    run(
                      `Vider « ${a.name} » ? Toutes ses opérations, soldes et imports seront supprimés. Le compte est conservé.`,
                      () => api.post(`/data/accounts/${a.id}/clear`),
                      (n) => `« ${a.name} » vidé (${n} opérations supprimées).`,
                    )
                  }
                >
                  Vider
                </button>
                <button
                  className="btn-ghost text-red-600"
                  onClick={() =>
                    run(
                      `Supprimer définitivement « ${a.name} » et toutes ses données ?`,
                      () => api.del(`/data/accounts/${a.id}`),
                      () => `« ${a.name} » supprimé.`,
                    )
                  }
                >
                  Supprimer
                </button>
              </span>
            </li>
          ))}
        </ul>
      </section>

      <section className="card space-y-2">
        <h2 className="font-medium">Catégorisations</h2>
        <p className="text-sm text-slate-500">
          Oublie les catégories que tu as choisies (vendeurs et corrections à la main) ; les règles par défaut s'appliquent
          à nouveau. Pour un seul vendeur, passe par la page Vendeurs.
        </p>
        <div className="flex flex-wrap gap-2">
          <CategorySelect className="input max-w-xs" value={category} onChange={setCategory} emptyLabel="Choisir une catégorie…" />
          <button
            className="btn-ghost"
            disabled={category === null}
            onClick={() =>
              run(
                `Réinitialiser tes choix pour « ${pathOf(category)} » (et ses sous-catégories) ?`,
                () => api.post(`/data/categories/${category}/reset`),
                (n) => `Catégorie réinitialisée (${n} opérations recatégorisées).`,
              )
            }
          >
            Réinitialiser cette catégorie
          </button>
        </div>
        <button
          className="btn-ghost text-red-600"
          onClick={() =>
            run(
              "Oublier TOUTES tes catégorisations (vendeurs et corrections) ?",
              () => api.post("/data/reset-categorization"),
              (n) => `Catégorisations réinitialisées (${n} opérations recatégorisées).`,
            )
          }
        >
          Réinitialiser toutes mes catégorisations
        </button>
      </section>

      <TagsSection />

      <section className="card space-y-2 border-red-300 dark:border-red-900">
        <h2 className="font-medium text-red-600">Tout effacer</h2>
        <p className="text-sm text-slate-500">
          Supprime toutes les opérations, vendeurs, soldes, imports et tes catégorisations. Les catégories par défaut sont
          conservées.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={keepAccounts} onChange={(e) => setKeepAccounts(e.target.checked)} />
          Garder mes comptes (vides)
        </label>
        <div className="flex flex-wrap gap-2">
          <input className="input max-w-xs" placeholder="Tape EFFACER" value={confirmWord} onChange={(e) => setConfirmWord(e.target.value)} />
          <button
            className="btn bg-red-600 hover:bg-red-700 dark:bg-red-600 dark:text-white"
            disabled={confirmWord !== "EFFACER"}
            onClick={() =>
              run(
                "",
                () => api.post("/data/wipe", { confirm: confirmWord, keep_accounts: keepAccounts }),
                () => {
                  setConfirmWord("");
                  return "Toutes les données ont été effacées.";
                },
              )
            }
          >
            Tout effacer
          </button>
        </div>
      </section>
    </div>
  );
}

function TagsSection() {
  const { tags, reload, create } = useTags();
  const [name, setName] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState({ name: "", color: "#475569" });
  const [error, setError] = useState<string | null>(null);

  const add = async () => {
    if (!name.trim()) return;
    try {
      await create(name.trim());
      setName("");
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const save = async (id: number) => {
    try {
      await api.patch(`/tags/${id}`, draft);
      setEditing(null);
      setError(null);
      reload();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const remove = async (id: number, label: string) => {
    if (!confirm(`Supprimer l'étiquette « ${label} » partout ? Les opérations ne sont pas supprimées.`)) return;
    await api.del(`/tags/${id}`);
    reload();
  };

  return (
    <section className="card space-y-2">
      <h2 className="font-medium">Étiquettes</h2>
      <p className="text-sm text-slate-500">
        Vues transversales (« Assurances », « Vacances »…) : elles s'ajoutent à la catégorie sans changer les totaux.
        Pose-les sur un vendeur, un service, ou sur une sélection d'opérations.
      </p>
      <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
        {tags.map((t) => (
          <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            {editing === t.id ? (
              <span className="flex flex-wrap items-center gap-2">
                <input className="input w-40" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                <input type="color" value={draft.color} onChange={(e) => setDraft({ ...draft, color: e.target.value })} />
                <button className="btn-ghost" onClick={() => save(t.id)}>OK</button>
                <button className="btn-ghost" onClick={() => setEditing(null)}>Annuler</button>
              </span>
            ) : (
              <span className="flex flex-wrap items-center gap-2">
                <TagChip name={t.name} color={t.color} />
                <span className="text-xs text-slate-500">
                  {t.transactions} op. · {formatCents(t.spent_cents)} dépensés · {t.merchants} vendeur(s) · {t.services} service(s)
                </span>
              </span>
            )}
            {editing !== t.id && (
              <span className="flex gap-1">
                <button className="btn-ghost" onClick={() => { setEditing(t.id); setDraft({ name: t.name, color: t.color ?? "#475569" }); }}>
                  Modifier
                </button>
                <button className="btn-ghost text-red-600" onClick={() => remove(t.id, t.name)}>Supprimer</button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <input className="input max-w-xs" placeholder="Nouvelle étiquette" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn-ghost" onClick={add} disabled={!name.trim()}>Créer</button>
      </div>
      {error && <p className="text-sm text-red-600">{error}</p>}
    </section>
  );
}
