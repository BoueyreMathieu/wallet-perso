import { useCallback, useEffect, useMemo, useState } from "react";
import { MerchantStats, Service, Share, Transaction, api } from "../api";
import { ServiceForm } from "../components/ServiceForm";
import { SimilarMerchants } from "../components/SimilarMerchants";
import { CategoryBadge, CategorySelect, useCategories } from "../components/categories";
import { TagChip, TagPicker, useTags } from "../components/tags";
import { PERIODS, PeriodKey, formatCents, formatDate, periodRange } from "../format";

type SortKey = "spent" | "received" | "count" | "name" | "last";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "spent", label: "Montant dépensé" },
  { key: "received", label: "Montant reçu" },
  { key: "count", label: "Nombre d'opérations" },
  { key: "last", label: "Dernière opération" },
  { key: "name", label: "Nom" },
];

export default function Merchants() {
  const [period, setPeriod] = useState<PeriodKey>("year");
  const [custom, setCustom] = useState<[string, string]>(["", ""]);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortKey>("spent");
  const [items, setItems] = useState<MerchantStats[]>([]);
  const [open, setOpen] = useState<number | null>(null);
  const { byId: tagsById } = useTags();

  const [from, to] = useMemo<[string | null, string | null]>(
    () => (period === "custom" ? [custom[0] || null, custom[1] || null] : periodRange(period)),
    [period, custom],
  );

  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (from) params.set("date_from", from);
    if (to) params.set("date_to", to);
    return api.get<MerchantStats[]>(`/merchants?${params}`).then(setItems);
  }, [from, to]);

  useEffect(() => {
    load();
  }, [load]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const list = items.filter((m) => !needle || m.name.toLowerCase().includes(needle));
    const by: Record<SortKey, (a: MerchantStats, b: MerchantStats) => number> = {
      spent: (a, b) => b.spent_cents - a.spent_cents,
      received: (a, b) => b.received_cents - a.received_cents,
      count: (a, b) => b.count - a.count,
      last: (a, b) => (b.last_date ?? "").localeCompare(a.last_date ?? ""),
      name: (a, b) => a.name.localeCompare(b.name, "fr"),
    };
    return [...list].sort(by[sort]);
  }, [items, q, sort]);

  const totalSpent = shown.reduce((s, m) => s + m.spent_cents, 0);
  const totalReceived = shown.reduce((s, m) => s + m.received_cents, 0);
  const maxSpent = Math.max(1, ...shown.map((m) => m.spent_cents));

  const setCategory = async (m: MerchantStats, catId: number | null) => {
    await api.post(`/merchants/${m.id}/category`, { category_id: catId });
    load();
  };

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Vendeurs</h1>
      <SimilarMerchants onChanged={load} />

      <div className="card grid gap-2 sm:grid-cols-4">
        <select className="input" value={period} onChange={(e) => setPeriod(e.target.value as PeriodKey)}>
          {PERIODS.map((p) => (
            <option key={p.key} value={p.key}>{p.label}</option>
          ))}
        </select>
        {period === "custom" ? (
          <div className="flex gap-2 sm:col-span-2">
            <input type="date" className="input" value={custom[0]} onChange={(e) => setCustom([e.target.value, custom[1]])} />
            <input type="date" className="input" value={custom[1]} onChange={(e) => setCustom([custom[0], e.target.value])} />
          </div>
        ) : (
          <input className="input sm:col-span-2" placeholder="Rechercher un vendeur…" value={q} onChange={(e) => setQ(e.target.value)} />
        )}
        <select className="input" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
          {SORTS.map((s) => (
            <option key={s.key} value={s.key}>Trier : {s.label}</option>
          ))}
        </select>
        {period === "custom" && (
          <input className="input sm:col-span-4" placeholder="Rechercher un vendeur…" value={q} onChange={(e) => setQ(e.target.value)} />
        )}
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="card p-3">
          <p className="text-xs text-slate-500">Vendeurs</p>
          <p className="text-lg font-semibold tabular-nums">{shown.length}</p>
        </div>
        <div className="card p-3">
          <p className="text-xs text-slate-500">Dépensé</p>
          <p className="text-lg font-semibold tabular-nums">{formatCents(totalSpent)}</p>
        </div>
        <div className="card p-3">
          <p className="text-xs text-slate-500">Reçu</p>
          <p className="text-lg font-semibold tabular-nums text-emerald-600">{formatCents(totalReceived)}</p>
        </div>
      </div>

      <ul className="card divide-y divide-slate-100 p-0 dark:divide-slate-800">
        {shown.length === 0 && <li className="p-4 text-sm text-slate-500">Aucune opération sur cette période.</li>}
        {shown.map((m) => (
          <li key={m.id} className="px-4 py-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <button className="min-w-0 flex-1 text-left" onClick={() => setOpen(open === m.id ? null : m.id)}>
                <p className="truncate font-medium">{m.name}</p>
                <p className="text-xs text-slate-500">
                  {m.count} op.{m.last_date && ` · dernière le ${formatDate(m.last_date)}`}
                  {m.received_cents > 0 && <span className="text-emerald-600"> · reçu {formatCents(m.received_cents)}</span>}
                  {m.services > 0 && ` · ${m.services} service${m.services > 1 ? "s" : ""}`}
                </p>
                <p className="mt-1 flex flex-wrap gap-1">
                  {m.categories.length > 1 &&
                    m.categories.map((c) => <CategoryBadge key={c.category_id ?? "none"} id={c.category_id ?? null} />)}
                  {m.tag_ids.map((id) => {
                    const tg = tagsById.get(id);
                    return tg ? <TagChip key={id} name={tg.name} color={tg.color} source="vendeur" /> : null;
                  })}
                </p>
                {m.spent_cents > 0 && (
                  <div className="mt-1 h-1.5 rounded bg-slate-100 dark:bg-slate-800">
                    <div className="h-1.5 rounded bg-slate-400" style={{ width: `${(100 * m.spent_cents) / maxSpent}%` }} />
                  </div>
                )}
              </button>
              <div className="flex min-w-0 items-center gap-2 sm:w-80 sm:shrink-0">
                <CategorySelect className="input" value={m.category_id} onChange={(id) => setCategory(m, id)} emptyLabel="— Catégorie générale —" />
                <span className="w-24 shrink-0 text-right font-semibold tabular-nums">{formatCents(m.spent_cents)}</span>
              </div>
            </div>
            {!m.category_chosen && m.category_id !== null && (
              <p className="mt-1 text-xs text-slate-400">Catégorie générale déduite automatiquement : choisis-la pour la figer.</p>
            )}
            {open === m.id && <MerchantDetail m={m} from={from} to={to} others={items} onChange={load} />}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MerchantDetail({
  m,
  from,
  to,
  others,
  onChange,
}: {
  m: MerchantStats;
  from: string | null;
  to: string | null;
  others: MerchantStats[];
  onChange: () => void;
}) {
  const { pathOf } = useCategories();
  const { byId: tagsById } = useTags();
  const [txs, setTxs] = useState<Transaction[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [bd, setBd] = useState<{ by_service: Share[]; by_category: Share[] } | null>(null);
  const [editingService, setEditingService] = useState<Service | "new" | null>(null);
  const [tags, setTags] = useState<number[]>(m.tag_ids);
  const [name, setName] = useState(m.name);
  const [mergeInto, setMergeInto] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  const loadDetail = useCallback(() => {
    const params = new URLSearchParams({ merchant_id: String(m.id), limit: "50" });
    const period = new URLSearchParams();
    if (from) {
      params.set("date_from", from);
      period.set("date_from", from);
    }
    if (to) {
      params.set("date_to", to);
      period.set("date_to", to);
    }
    api.get<{ items: Transaction[] }>(`/transactions?${params}`).then((p) => setTxs(p.items));
    api.get<Service[]>(`/merchants/${m.id}/services`).then(setServices);
    api.get<{ by_service: Share[]; by_category: Share[] }>(`/merchants/${m.id}/breakdown?${period}`).then(setBd);
  }, [m.id, from, to]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  const refresh = () => {
    loadDetail();
    onChange();
  };
  const rename = async () => {
    const r = await api.patch<{ merged: boolean }>(`/merchants/${m.id}`, { name });
    setMsg(r.merged ? "Fusionné avec le vendeur existant du même nom." : "Renommé.");
    onChange();
  };
  const merge = async () => {
    const target = others.find((o) => String(o.id) === mergeInto);
    if (!target || !confirm(`Fusionner « ${m.name} » dans « ${target.name} » ?`)) return;
    await api.post(`/merchants/${m.id}/merge`, { into_id: target.id });
    onChange();
  };
  const reset = async () => {
    await api.post(`/merchants/${m.id}/reset`);
    setMsg("Catégorie générale réinitialisée.");
    refresh();
  };
  const saveTags = async (ids: number[]) => {
    setTags(ids);
    await api.put(`/merchants/${m.id}/tags`, { tag_ids: ids });
    onChange();
  };
  const deleteService = async (sv: Service) => {
    if (!confirm(`Supprimer le service « ${sv.label} » ? Ses opérations reprendront la catégorie générale du vendeur.`)) return;
    await api.del(`/services/${sv.id}`);
    refresh();
  };

  const describe = (sv: Service) => {
    const parts: string[] = [];
    if (sv.pattern) parts.push(`libellé contient « ${sv.pattern} »`);
    if (sv.amount_min_cents !== null || sv.amount_max_cents !== null) {
      const lo = sv.amount_min_cents, hi = sv.amount_max_cents;
      parts.push(
        lo !== null && hi !== null && lo === hi
          ? `montant = ${formatCents(lo)}`
          : `montant ${lo !== null ? `≥ ${formatCents(lo)}` : ""}${lo !== null && hi !== null ? " et " : ""}${hi !== null ? `≤ ${formatCents(hi)}` : ""}`,
      );
    }
    return parts.join(" et ");
  };

  return (
    <div className="mt-3 space-y-4 rounded-lg bg-slate-50 p-3 text-sm dark:bg-slate-800/50">
      {bd && (bd.by_service.length > 1 || bd.by_category.length > 1) && (
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Par service</p>
            {bd.by_service.map((s) => (
              <p key={s.rule_id ?? "none"} className="flex justify-between gap-2">
                <span className="truncate">{s.label} <span className="text-xs text-slate-500">({s.count})</span></span>
                <span className="tabular-nums">{formatCents(s.spent_cents)}</span>
              </p>
            ))}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Par catégorie</p>
            {bd.by_category.map((c) => (
              <p key={c.category_id ?? "none"} className="flex justify-between gap-2">
                <span className="truncate">{c.category_id ? pathOf(c.category_id) : "À catégoriser"} <span className="text-xs text-slate-500">({c.count})</span></span>
                <span className="tabular-nums">{formatCents(c.spent_cents)}</span>
              </p>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-2">
        <p className="text-xs font-medium text-slate-500">
          Services : une catégorie par type de prestation (ex. assurance habitation / auto chez le même courtier)
        </p>
        {services.map((sv) =>
          editingService !== "new" && editingService?.id === sv.id ? (
            <ServiceForm key={sv.id} merchantId={m.id} merchantName={m.name} service={sv} onCancel={() => setEditingService(null)} onDone={() => { setEditingService(null); refresh(); }} />
          ) : (
            <div key={sv.id} className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-200 p-2 dark:border-slate-700">
              <div className="min-w-0">
                <p className="font-medium">{sv.label}</p>
                <p className="text-xs text-slate-500">{describe(sv)} → {pathOf(sv.category_id)}</p>
                <p className="flex flex-wrap gap-1">
                  {sv.tag_ids.map((id) => {
                    const tg = tagsById.get(id);
                    return tg ? <TagChip key={id} name={tg.name} color={tg.color} source="service" /> : null;
                  })}
                </p>
              </div>
              <span className="flex gap-1">
                <button className="btn-ghost" onClick={() => setEditingService(sv)}>Modifier</button>
                <button className="btn-ghost text-red-600" onClick={() => deleteService(sv)}>Supprimer</button>
              </span>
            </div>
          ),
        )}
        {editingService === "new" ? (
          <ServiceForm merchantId={m.id} merchantName={m.name} onCancel={() => setEditingService(null)} onDone={() => { setEditingService(null); refresh(); }} />
        ) : (
          <button className="btn-ghost" onClick={() => setEditingService("new")}>+ Ajouter un service</button>
        )}
      </div>

      <div className="space-y-1">
        <p className="text-xs font-medium text-slate-500">Étiquettes du vendeur (héritées par toutes ses opérations)</p>
        <TagPicker value={tags} onChange={saveTags} />
      </div>

      <div>
        <p className="mb-1 text-xs font-medium text-slate-500">Opérations sur la période</p>
        <ul className="space-y-1">
          {txs.map((t) => (
            <li key={t.id} className={`flex justify-between gap-2 ${t.counted ? "" : "opacity-60"}`}>
              <span className="min-w-0 truncate">
                {formatDate(t.booked_at)} · {t.account_name} {t.details?.objet && `· ${t.details.objet}`}{" "}
                <CategoryBadge id={t.category_id} />
              </span>
              <span className={`shrink-0 tabular-nums ${t.amount_cents > 0 ? "text-emerald-600" : ""}`}>{formatCents(t.amount_cents)}</span>
            </li>
          ))}
          {txs.length === 0 && <li className="text-slate-500">Aucune opération sur la période.</li>}
        </ul>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input className="input max-w-xs" value={name} onChange={(e) => setName(e.target.value)} />
        <button className="btn-ghost" onClick={rename} disabled={!name.trim() || name === m.name}>Renommer</button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select className="input max-w-xs" value={mergeInto} onChange={(e) => setMergeInto(e.target.value)}>
          <option value="">Fusionner avec…</option>
          {others
            .filter((o) => o.id !== m.id)
            .sort((a, b) => a.name.localeCompare(b.name, "fr"))
            .map((o) => (
              <option key={o.id} value={o.id}>{o.name}</option>
            ))}
        </select>
        <button className="btn-ghost" onClick={merge} disabled={!mergeInto}>Fusionner</button>
        {m.category_chosen && (
          <button className="btn-ghost text-red-600" onClick={reset}>Réinitialiser la catégorie générale</button>
        )}
      </div>
      {msg && <p className="text-xs text-slate-500">{msg}</p>}
    </div>
  );
}
