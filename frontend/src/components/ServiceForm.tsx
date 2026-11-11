import { FormEvent, useState } from "react";
import { Service, api } from "../api";
import { formatCents, parseEuros } from "../format";
import { CategorySelect } from "./categories";
import { TagPicker, useTags } from "./tags";

export interface ServiceDraft {
  label: string;
  pattern: string;
  amount_cents?: number | null;
  category_id?: number | null;
}

const euros = (cents: number | null | undefined) => (cents == null ? "" : (cents / 100).toFixed(2).replace(".", ","));

/** Création / modification d'un service d'un vendeur (ex. « Assurance habitation » chez un courtier). */
export function ServiceForm({
  merchantId,
  merchantName,
  service,
  draft,
  onDone,
  onCancel,
}: {
  merchantId: number;
  merchantName: string;
  service?: Service;
  draft?: ServiceDraft;
  onDone: () => void;
  onCancel: () => void;
}) {
  const { reload } = useTags();
  const [label, setLabel] = useState(service?.label ?? draft?.label ?? "");
  const [pattern, setPattern] = useState(service?.pattern ?? draft?.pattern ?? "");
  const [useAmount, setUseAmount] = useState(
    service ? service.amount_min_cents !== null || service.amount_max_cents !== null : !draft?.pattern,
  );
  const [min, setMin] = useState(euros(service?.amount_min_cents ?? draft?.amount_cents));
  const [max, setMax] = useState(euros(service?.amount_max_cents ?? draft?.amount_cents));
  const [category, setCategory] = useState<number | null>(service?.category_id ?? draft?.category_id ?? null);
  const [tagIds, setTagIds] = useState<number[]>(service?.tag_ids ?? []);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const minC = useAmount && min.trim() ? parseEuros(min) : null;
    const maxC = useAmount && max.trim() ? parseEuros(max) : null;
    if (useAmount && ((min.trim() && minC === null) || (max.trim() && maxC === null))) return setError("Montant invalide (ex. 25,50)");
    if (category === null) return setError("Choisis une catégorie");
    const body = {
      label: label.trim(),
      pattern: pattern.trim(),
      match_type: "contient",
      amount_min_cents: minC === null ? null : Math.abs(minC),
      amount_max_cents: maxC === null ? null : Math.abs(maxC),
      category_id: category,
      tag_ids: tagIds,
    };
    try {
      if (service) await api.patch(`/services/${service.id}`, body);
      else await api.post(`/merchants/${merchantId}/services`, body);
      await reload();
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
      <p className="font-medium">{service ? "Modifier le service" : `Nouveau service chez ${merchantName}`}</p>
      <input className="input" placeholder="Nom du service (ex. Assurance habitation)" value={label} onChange={(e) => setLabel(e.target.value)} required />
      <label className="block space-y-1">
        <span className="text-xs text-slate-500">Reconnu quand le libellé contient (mot ou n° de contrat)</span>
        <input className="input" placeholder="ex. HABITATION" value={pattern} onChange={(e) => setPattern(e.target.value)} />
      </label>
      <label className="flex items-center gap-2">
        <input type="checkbox" checked={useAmount} onChange={(e) => setUseAmount(e.target.checked)} />
        <span>et/ou quand le montant est compris entre</span>
      </label>
      {useAmount && (
        <div className="flex items-center gap-2">
          <input className="input" inputMode="decimal" placeholder="min (€)" value={min} onChange={(e) => setMin(e.target.value)} />
          <span>et</span>
          <input className="input" inputMode="decimal" placeholder="max (€)" value={max} onChange={(e) => setMax(e.target.value)} />
        </div>
      )}
      {draft?.amount_cents != null && useAmount && (
        <p className="text-xs text-slate-500">Montant de l'opération de départ : {formatCents(draft.amount_cents)}</p>
      )}
      <CategorySelect value={category} onChange={setCategory} emptyLabel="Catégorie du service…" />
      <div className="space-y-1">
        <span className="text-xs text-slate-500">Étiquettes du service (héritées par ses opérations)</span>
        <TagPicker value={tagIds} onChange={setTagIds} />
      </div>
      {error && <p className="text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button className="btn">{service ? "Enregistrer" : "Créer le service"}</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>Annuler</button>
      </div>
    </form>
  );
}
