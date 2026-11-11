import { useCallback, useEffect, useState } from "react";
import { Account, MerchantGroup, ServiceSuggestion, Transaction, api } from "../api";
import { ManualForm } from "../components/ManualForm";
import { ServiceDraft, ServiceForm } from "../components/ServiceForm";
import { CategoryBadge, CategorySelect } from "../components/categories";
import { TagChip, TagPicker, TagSelect } from "../components/tags";
import { formatCents, formatDate } from "../format";

const PAGE = 100;

export default function Transactions() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState("");
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [tagId, setTagId] = useState<number | null>(null);
  const [onlyUncategorized, setOnlyUncategorized] = useState(false);
  const [q, setQ] = useState("");
  const [items, setItems] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [groups, setGroups] = useState<MerchantGroup[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [creating, setCreating] = useState(false);
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  useEffect(() => {
    api.get<Account[]>("/accounts").then(setAccounts);
  }, []);

  const load = useCallback(
    async (offset = 0) => {
      const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
      if (accountId) params.set("account_id", accountId);
      if (categoryId !== null) params.set("category_id", String(categoryId));
      if (tagId !== null) params.set("tag_id", String(tagId));
      if (onlyUncategorized) params.set("uncategorized", "true");
      if (q.trim()) params.set("q", q.trim());
      const page = await api.get<{ items: Transaction[]; total: number }>(`/transactions?${params}`);
      setItems((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
      setTotal(page.total);
    },
    [accountId, categoryId, tagId, onlyUncategorized, q],
  );

  const loadGroups = () => api.get<MerchantGroup[]>("/transactions/to-categorize").then(setGroups);

  useEffect(() => {
    const t = setTimeout(() => load(0), 250); // petite attente pendant la saisie de recherche
    return () => clearTimeout(t);
  }, [load]);
  useEffect(() => {
    loadGroups();
  }, []);
  useEffect(() => setSelected(new Set()), [accountId, categoryId, tagId, onlyUncategorized, q]);

  const refresh = () => {
    load(0);
    loadGroups();
  };

  const categorizeMerchant = async (merchantId: number, catId: number | null) => {
    await api.post(`/merchants/${merchantId}/category`, { category_id: catId });
    refresh();
  };

  const changeCategory = async (t: Transaction, catId: number | null, allForMerchant: boolean) => {
    await api.patch(`/transactions/${t.id}`, { category_id: catId, apply_to_merchant: allForMerchant });
    setEditing(null);
    refresh();
  };

  const unlinkTx = async (t: Transaction) => {
    await api.post(`/transactions/${t.id}/unlink`);
    setEditing(null);
    refresh();
  };

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allShown = items.length > 0 && items.every((t) => selected.has(t.id));
  const toggleAll = () => setSelected(allShown ? new Set() : new Set(items.map((t) => t.id)));

  const uncategorizedCount = groups.reduce((s, g) => s + g.count, 0);

  return (
    <div className={`space-y-4 ${selected.size ? "pb-40 sm:pb-24" : ""}`}>
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Opérations</h1>
        {!creating && (
          <button className="btn" onClick={() => setCreating(true)}>+ Nouvelle opération</button>
        )}
      </div>

      {creating && (
        <ManualForm
          onCancel={() => setCreating(false)}
          onDone={() => {
            setCreating(false);
            refresh();
          }}
        />
      )}

      {groups.length > 0 && (
        <details className="card" open>
          <summary className="cursor-pointer font-medium">
            À catégoriser : {uncategorizedCount} opération{uncategorizedCount > 1 ? "s" : ""}, {groups.length}{" "}
            vendeur{groups.length > 1 ? "s" : ""}
          </summary>
          <p className="mt-2 text-sm text-slate-500">
            Choisis la catégorie générale d'un vendeur : elle s'applique à toutes ses opérations, passées et futures
            (sauf celles reconnues par un de ses services).
          </p>
          <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
            {groups.slice(0, 15).map((g) => {
              const key = String(g.merchant_id ?? "none");
              return (
                <li key={key} className="py-2">
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <button className="min-w-0 flex-1 text-left" onClick={() => setOpenGroup(openGroup === key ? null : key)}>
                      <p className="truncate font-medium">
                        <span className="mr-1 text-slate-400">{openGroup === key ? "▾" : "▸"}</span>
                        {g.merchant ?? "Sans vendeur"}
                      </p>
                      <p className="text-xs text-slate-500">
                        {g.count} op. · {formatCents(g.total_cents)} · dernière le {formatDate(g.last_date)} · voir le détail
                      </p>
                    </button>
                    {g.merchant_id !== null && (
                      <CategorySelect
                        className="input sm:w-64"
                        value={null}
                        emptyLabel="Catégorie pour tout le vendeur…"
                        onChange={(id) => id !== null && categorizeMerchant(g.merchant_id!, id)}
                      />
                    )}
                  </div>
                  {openGroup === key && <GroupDetail merchantId={g.merchant_id} onChanged={refresh} />}
                </li>
              );
            })}
          </ul>
          {groups.length > 15 && (
            <p className="mt-2 text-xs text-slate-500">… et {groups.length - 15} autres (traite d'abord les plus fréquents).</p>
          )}
        </details>
      )}

      <div className="card grid gap-2 sm:grid-cols-4">
        <input className="input sm:col-span-2" placeholder="Rechercher (vendeur, libellé)…" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)}>
          <option value="">Tous les comptes</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
        <CategorySelect className="input" value={categoryId} onChange={setCategoryId} emptyLabel="Toutes les catégories" />
        <TagSelect className="input sm:col-span-2" value={tagId} onChange={setTagId} />
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" checked={onlyUncategorized} onChange={(e) => setOnlyUncategorized(e.target.checked)} />
          Seulement les opérations à catégoriser
        </label>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-500">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={allShown} onChange={toggleAll} />
          Tout sélectionner ({items.length} affichée{items.length > 1 ? "s" : ""})
        </label>
        <span>{total} opération{total > 1 ? "s" : ""}</span>
      </div>

      <ul className="card divide-y divide-slate-100 p-0 dark:divide-slate-800">
        {items.map((t) => (
          <li key={t.id} className={`px-4 py-3 ${t.counted ? "" : "opacity-60"} ${selected.has(t.id) ? "bg-sky-50 dark:bg-sky-950/40" : ""}`}>
            <div className="flex items-start gap-3">
              <input type="checkbox" className="mt-1" checked={selected.has(t.id)} onChange={() => toggle(t.id)} aria-label="Sélectionner" />
              <button className="min-w-0 flex-1 text-left" onClick={() => setEditing(editing === t.id ? null : t.id)}>
                <p className="truncate font-medium">{t.label}</p>
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
                  <span>{formatDate(t.booked_at)}</span>
                  <span>· {t.account_name}</span>
                  <CategoryBadge id={t.category_id} />
                  {t.is_transfer && <span>· transfert</span>}
                  {t.details?.via && <span className="rounded bg-sky-100 px-1 text-sky-700 dark:bg-sky-900 dark:text-sky-200">via {t.details.via}</span>}
                  {!t.counted && <span>· non compté</span>}
                  {t.status === "en attente" && <span>· en attente</span>}
                  {t.tags.map((tg) => (
                    <TagChip key={tg.id} name={tg.name} color={tg.color} source={tg.source} />
                  ))}
                </p>
              </button>
              <span className={`shrink-0 font-semibold tabular-nums ${t.amount_cents > 0 ? "text-emerald-600" : ""}`}>
                {formatCents(t.amount_cents)}
              </span>
            </div>
            {editing === t.id && <EditPanel t={t} onSave={changeCategory} onUnlink={unlinkTx} onChanged={refresh} />}
          </li>
        ))}
      </ul>

      {items.length < total && (
        <button className="btn-ghost w-full" onClick={() => load(items.length)}>
          Afficher plus
        </button>
      )}

      {selected.size > 0 && (
        <BulkBar
          ids={[...selected]}
          onDone={() => {
            refresh();
          }}
          onClear={() => setSelected(new Set())}
        />
      )}
    </div>
  );
}

/** Détail d'une carte « À catégoriser » : les opérations du vendeur, avec libellé complet. */
function GroupDetail({ merchantId, onChanged }: { merchantId: number | null; onChanged: () => void }) {
  const [txs, setTxs] = useState<Transaction[]>([]);
  const load = useCallback(() => {
    const params = new URLSearchParams({ uncategorized: "true", limit: "50" });
    if (merchantId === null) params.set("no_merchant", "true");
    else params.set("merchant_id", String(merchantId));
    api.get<{ items: Transaction[] }>(`/transactions?${params}`).then((p) => setTxs(p.items));
  }, [merchantId]);
  useEffect(() => {
    load();
  }, [load]);

  const setOne = async (t: Transaction, catId: number | null) => {
    if (catId === null) return;
    await api.patch(`/transactions/${t.id}`, { category_id: catId });
    load();
    onChanged();
  };

  return (
    <ul className="mt-2 space-y-2 rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/50">
      {txs.map((t) => (
        <li key={t.id} className="space-y-1 border-b border-slate-200 pb-2 last:border-0 last:pb-0 dark:border-slate-700">
          <div className="flex justify-between gap-2">
            <span className="text-slate-500">
              {formatDate(t.booked_at)} · {t.account_name}
            </span>
            <span className={`font-semibold tabular-nums ${t.amount_cents > 0 ? "text-emerald-600" : ""}`}>{formatCents(t.amount_cents)}</span>
          </div>
          <p className="break-words text-xs">{t.raw_label}</p>
          {t.details && (
            <p className="text-xs text-slate-500">
              {Object.entries(DETAIL_LABELS)
                .filter(([k]) => t.details?.[k])
                .map(([k, label]) => `${label} : ${t.details?.[k]}`)
                .join(" · ")}
            </p>
          )}
          <CategorySelect className="input sm:w-72" value={null} emptyLabel="Catégorie pour cette opération seulement…" onChange={(id) => setOne(t, id)} />
        </li>
      ))}
      {txs.length === 0 && <li className="text-slate-500">Plus rien à catégoriser ici.</li>}
    </ul>
  );
}

function BulkBar({ ids, onDone, onClear }: { ids: number[]; onDone: () => void; onClear: () => void }) {
  const [tag, setTag] = useState<number | null>(null);
  const [cat, setCat] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const run = async (body: object, done: (r: { updated: number; inherited_kept: number }) => string) => {
    const r = await api.post<{ updated: number; inherited_kept: number }>("/transactions/bulk", { ids, ...body });
    setMsg(done(r));
    onDone();
  };

  return (
    <div className="fixed inset-x-0 bottom-14 z-10 px-4 sm:bottom-4">
      <div className="card mx-auto max-w-5xl space-y-2 shadow-lg">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium">{ids.length} sélectionnée{ids.length > 1 ? "s" : ""}</span>
          <TagSelect className="input w-auto" value={tag} onChange={setTag} emptyLabel="Étiquette…" />
          <button className="btn-ghost" disabled={tag === null} onClick={() => run({ add_tag_ids: [tag] }, (r) => `Étiquette ajoutée sur ${r.updated} opération(s).`)}>
            Ajouter
          </button>
          <button
            className="btn-ghost"
            disabled={tag === null}
            onClick={() =>
              run({ remove_tag_ids: [tag] }, (r) =>
                `Étiquette retirée de ${r.updated} opération(s).` +
                (r.inherited_kept ? ` ${r.inherited_kept} la gardent car elle vient de leur vendeur ou service.` : ""),
              )
            }
          >
            Retirer
          </button>
          <span className="hidden h-5 border-l border-slate-300 sm:inline dark:border-slate-700" />
          <CategorySelect className="input w-auto" value={cat} onChange={setCat} emptyLabel="Catégorie…" />
          <button className="btn-ghost" disabled={cat === null} onClick={() => run({ set_category: true, category_id: cat }, (r) => `${r.updated} opération(s) catégorisée(s).`)}>
            Catégoriser
          </button>
          <button className="btn-ghost ml-auto" onClick={onClear}>Désélectionner</button>
        </div>
        {msg && <p className="text-xs text-slate-500">{msg}</p>}
      </div>
    </div>
  );
}

const DETAIL_LABELS: Record<string, string> = {
  vendeur: "Vendeur",
  objet: "Objet",
  paypal_transaction: "N° de transaction PayPal",
  transaction: "N° de transaction",
  type: "Type d'opération",
  saisie_manuelle: "Saisie manuelle fusionnée",
};

function EditPanel({
  t,
  onSave,
  onUnlink,
  onChanged,
}: {
  t: Transaction;
  onSave: (t: Transaction, c: number | null, all: boolean) => void;
  onUnlink: (t: Transaction) => void;
  onChanged: () => void;
}) {
  const [cat, setCat] = useState<number | null>(t.category_id);
  const [all, setAll] = useState(t.merchant_id !== null);
  const manual = t.tags.filter((tg) => tg.source === "manuel").map((tg) => tg.id);
  const [tags, setTags] = useState<number[]>(manual);
  const [draft, setDraft] = useState<ServiceDraft | null>(null);
  const [editingManual, setEditingManual] = useState(false);

  const remove = async () => {
    const msg =
      t.source === "manuel"
        ? "Supprimer cette opération saisie à la main ?"
        : "Supprimer cette opération importée ? Elle reviendra si tu réimportes le même fichier.";
    if (!confirm(msg)) return;
    await api.del(`/transactions/${t.id}`);
    onChanged();
  };

  const saveTags = async (next: number[]) => {
    setTags(next);
    await api.post("/transactions/bulk", {
      ids: [t.id],
      add_tag_ids: next.filter((id) => !manual.includes(id)),
      remove_tag_ids: manual.filter((id) => !next.includes(id)),
    });
    onChanged();
  };

  const startService = async () => {
    const s = await api.get<ServiceSuggestion>(`/transactions/${t.id}/service-suggestion`);
    setDraft({ label: s.label, pattern: s.pattern, amount_cents: s.amount_cents, category_id: t.category_id });
  };

  const inherited = t.tags.filter((tg) => tg.source !== "manuel");

  if (editingManual) {
    return (
      <div className="mt-3">
        <ManualForm
          tx={t}
          onCancel={() => setEditingManual(false)}
          onDone={() => {
            setEditingManual(false);
            onChanged();
          }}
        />
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-3 rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/50">
      {t.source === "manuel" && <p className="text-xs text-slate-500">Opération saisie à la main{t.note ? ` · Note : ${t.note}` : ""}</p>}
      {t.source !== "manuel" && t.note && <p className="text-xs text-slate-500">Note : {t.note}</p>}
      <p className="break-words text-xs text-slate-500">{t.raw_label}</p>
      {t.details && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          {Object.entries(DETAIL_LABELS)
            .filter(([k]) => t.details?.[k])
            .map(([k, label]) => (
              <div key={k} className="contents">
                <dt className="text-slate-500">{label}</dt>
                <dd className="break-words">{t.details?.[k]}</dd>
              </div>
            ))}
        </dl>
      )}
      {!t.counted && (
        <p className="text-xs text-slate-500">
          Cette ligne n'est pas comptée dans les statistiques
          {t.linked_id ? " : la dépense est déjà comptée sur l'opération bancaire rapprochée." : " (mouvement technique)."}
        </p>
      )}

      <div className="space-y-2">
        <CategorySelect value={cat} onChange={setCat} />
        {t.merchant && (
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} />
            En faire la catégorie générale de « {t.merchant} » (hors services)
          </label>
        )}
        <div className="flex flex-wrap gap-2">
          <button className="btn" onClick={() => onSave(t, cat, all)}>Enregistrer la catégorie</button>
          {(t.linked_id !== null || t.details?.via) && (
            <button className="btn-ghost text-red-600" onClick={() => onUnlink(t)}>
              Dissocier le rapprochement
            </button>
          )}
        </div>
      </div>

      <div className="space-y-1">
        <p className="text-xs text-slate-500">Étiquettes de cette opération</p>
        <TagPicker value={tags} onChange={saveTags} />
        {inherited.length > 0 && (
          <p className="flex flex-wrap items-center gap-1 text-xs text-slate-500">
            Héritées :
            {inherited.map((tg) => (
              <TagChip key={tg.id} name={tg.name} color={tg.color} source={tg.source} />
            ))}
          </p>
        )}
      </div>

      {t.merchant_id !== null && t.merchant && !draft && (
        <button className="btn-ghost" onClick={startService}>
          + Créer un service à partir de cette opération
        </button>
      )}
      <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-2 dark:border-slate-700">
        {t.source === "manuel" && (
          <button className="btn-ghost" onClick={() => setEditingManual(true)}>Modifier l'opération</button>
        )}
        <button className="btn-ghost text-red-600" onClick={remove}>Supprimer l'opération</button>
      </div>
      {draft && t.merchant_id !== null && (
        <ServiceForm
          merchantId={t.merchant_id}
          merchantName={t.merchant ?? ""}
          draft={draft}
          onCancel={() => setDraft(null)}
          onDone={() => {
            setDraft(null);
            onChanged();
          }}
        />
      )}
    </div>
  );
}
