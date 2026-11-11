import { FormEvent, useEffect, useState } from "react";
import { Account, MerchantStats, Transaction, api } from "../api";
import { isoDate, parseEuros } from "../format";
import { CategorySelect } from "./categories";
import { TagPicker } from "./tags";

/** Saisie (ou modification) d'une opération à la main : espèces, oubli, compte sans import… */
export function ManualForm({ tx, onDone, onCancel }: { tx?: Transaction; onDone: () => void; onCancel: () => void }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [merchants, setMerchants] = useState<string[]>([]);
  const [accountId, setAccountId] = useState(tx ? String(tx.account_id) : "");
  const [day, setDay] = useState(tx?.booked_at ?? isoDate(new Date()));
  const [kind, setKind] = useState<"depense" | "revenu">(tx && tx.amount_cents > 0 ? "revenu" : "depense");
  const [amount, setAmount] = useState(tx ? (Math.abs(tx.amount_cents) / 100).toFixed(2).replace(".", ",") : "");
  const [label, setLabel] = useState(tx?.raw_label ?? "");
  const [merchant, setMerchant] = useState(tx?.merchant ?? "");
  const [category, setCategory] = useState<number | null>(tx?.category_id ?? null);
  const [note, setNote] = useState(tx?.note ?? "");
  const [tags, setTags] = useState<number[]>(tx ? tx.tags.filter((t) => t.source === "manuel").map((t) => t.id) : []);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<Account[]>("/accounts").then((list) => {
      setAccounts(list);
      if (!tx && list.length) setAccountId((v) => v || String(list[0].id));
    });
    api.get<MerchantStats[]>("/merchants?include_inactive=true").then((ms) => setMerchants(ms.map((m) => m.name)));
  }, [tx]);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    const cents = parseEuros(amount);
    if (cents === null || cents === 0) return setError("Montant invalide (ex. 12,50)");
    const signed = kind === "depense" ? -Math.abs(cents) : Math.abs(cents);
    const body = {
      account_id: Number(accountId),
      booked_at: day,
      amount_cents: signed,
      label: label.trim(),
      merchant: merchant.trim() || null,
      note: note.trim() || null,
    };
    try {
      if (tx) {
        await api.patch(`/transactions/${tx.id}`, category !== tx.category_id ? { ...body, category_id: category } : body);
        const before = tx.tags.filter((t) => t.source === "manuel").map((t) => t.id);
        if (before.join() !== tags.join()) {
          await api.post("/transactions/bulk", {
            ids: [tx.id],
            add_tag_ids: tags.filter((id) => !before.includes(id)),
            remove_tag_ids: before.filter((id) => !tags.includes(id)),
          });
        }
      } else {
        await api.post("/transactions", { ...body, category_id: category, tag_ids: tags });
      }
      onDone();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form onSubmit={submit} className="card grid gap-3 text-sm sm:grid-cols-2">
      <p className="font-medium sm:col-span-2">{tx ? "Modifier l'opération" : "Nouvelle opération"}</p>
      <div className="flex gap-1 sm:col-span-2">
        {(["depense", "revenu"] as const).map((k) => (
          <button key={k} type="button" className={`btn-ghost ${kind === k ? "bg-slate-200 font-semibold dark:bg-slate-700" : ""}`} onClick={() => setKind(k)}>
            {k === "depense" ? "Dépense" : "Revenu"}
          </button>
        ))}
      </div>
      <label className="space-y-1">
        <span>Montant (€)</span>
        <input className="input" inputMode="decimal" placeholder="12,50" value={amount} onChange={(e) => setAmount(e.target.value)} required />
      </label>
      <label className="space-y-1">
        <span>Date</span>
        <input type="date" className="input" value={day} onChange={(e) => setDay(e.target.value)} required />
      </label>
      <label className="space-y-1">
        <span>Compte</span>
        <select className="input" value={accountId} onChange={(e) => setAccountId(e.target.value)} required>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
      </label>
      <label className="space-y-1">
        <span>Vendeur (facultatif)</span>
        <input className="input" list="manual-merchants" value={merchant} onChange={(e) => setMerchant(e.target.value)} placeholder="Choisir ou taper un nom" />
        <datalist id="manual-merchants">
          {merchants.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
      </label>
      <label className="space-y-1 sm:col-span-2">
        <span>Libellé</span>
        <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="ex. Marché du samedi" required />
      </label>
      <div className="space-y-1">
        <span>Catégorie</span>
        <CategorySelect value={category} onChange={setCategory} emptyLabel="Automatique (selon les règles)" />
      </div>
      <label className="space-y-1">
        <span>Note</span>
        <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <div className="space-y-1 sm:col-span-2">
        <span>Étiquettes</span>
        <TagPicker value={tags} onChange={setTags} />
      </div>
      <p className="text-xs text-slate-500 sm:col-span-2">
        L'opération s'ajoute au solde du compte si elle est datée après son dernier solde connu. Si un import bancaire
        la retrouve plus tard (même montant, ±3 jours), les deux sont fusionnées en gardant ta catégorie, ta note et tes
        étiquettes.
      </p>
      {error && <p className="text-red-600 sm:col-span-2">{error}</p>}
      <div className="flex gap-2 sm:col-span-2">
        <button className="btn">{tx ? "Enregistrer" : "Ajouter"}</button>
        <button type="button" className="btn-ghost" onClick={onCancel}>Annuler</button>
      </div>
    </form>
  );
}
