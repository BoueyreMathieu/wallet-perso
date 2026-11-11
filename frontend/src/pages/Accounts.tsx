import { FormEvent, useEffect, useState } from "react";
import { Account, AccountType, api } from "../api";
import { ACCOUNT_TYPE_LABELS, formatCents, formatDate, parseEuros } from "../format";

const TYPES = Object.keys(ACCOUNT_TYPE_LABELS) as AccountType[];
const today = () => new Date().toISOString().slice(0, 10);

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [showForm, setShowForm] = useState(false);

  const load = () => api.get<Account[]>("/accounts").then(setAccounts);
  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Comptes</h1>
        <button className="btn" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Annuler" : "Ajouter un compte"}
        </button>
      </div>

      {showForm && (
        <NewAccountForm
          onCreated={() => {
            setShowForm(false);
            load();
          }}
        />
      )}

      {accounts.length === 0 && !showForm && (
        <p className="card text-sm text-slate-500">Aucun compte. Commence par ton compte courant Crédit Agricole.</p>
      )}

      <ul className="space-y-2">
        {accounts.map((a) => (
          <AccountRow key={a.id} account={a} onChange={load} />
        ))}
      </ul>
    </div>
  );
}

function NewAccountForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [type, setType] = useState<AccountType>("courant");
  const [institution, setInstitution] = useState("");
  const [balance, setBalance] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const cents = balance.trim() ? parseEuros(balance) : null;
    if (balance.trim() && cents === null) return setError("Solde invalide (ex. 1234,56)");
    try {
      await api.post("/accounts", {
        name,
        type,
        institution: institution || null,
        initial_balance_cents: cents,
      });
      onCreated();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <form onSubmit={submit} className="card grid gap-3 sm:grid-cols-2">
      <label className="space-y-1 text-sm">
        <span>Nom</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Compte courant" required />
      </label>
      <label className="space-y-1 text-sm">
        <span>Type</span>
        <select className="input" value={type} onChange={(e) => setType(e.target.value as AccountType)}>
          {TYPES.map((t) => (
            <option key={t} value={t}>{ACCOUNT_TYPE_LABELS[t]}</option>
          ))}
        </select>
      </label>
      <label className="space-y-1 text-sm">
        <span>Établissement</span>
        <input className="input" value={institution} onChange={(e) => setInstitution(e.target.value)} placeholder="Crédit Agricole" />
      </label>
      <label className="space-y-1 text-sm">
        <span>Solde actuel (€)</span>
        <input className="input" inputMode="decimal" value={balance} onChange={(e) => setBalance(e.target.value)} placeholder="1 234,56" />
      </label>
      {error && <p className="text-sm text-red-600 sm:col-span-2">{error}</p>}
      <div className="sm:col-span-2">
        <button className="btn">Créer</button>
      </div>
    </form>
  );
}

function AccountRow({ account: a, onChange }: { account: Account; onChange: () => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");

  const saveBalance = async (e: FormEvent) => {
    e.preventDefault();
    const cents = parseEuros(value);
    if (cents === null) return;
    await api.post(`/accounts/${a.id}/balances`, { date: today(), balance_cents: cents });
    setEditing(false);
    onChange();
  };

  const archive = async () => {
    if (!confirm(`Archiver « ${a.name} » ?`)) return;
    await api.del(`/accounts/${a.id}`);
    onChange();
  };

  return (
    <li className="card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{a.name}</p>
          <p className="text-sm text-slate-500">
            {ACCOUNT_TYPE_LABELS[a.type]}
            {a.institution && ` · ${a.institution}`}
          </p>
        </div>
        <div className="text-right">
          <p className={`font-semibold tabular-nums ${(a.balance_cents ?? 0) < 0 ? "text-red-600" : ""}`}>
            {a.balance_cents === null ? "—" : formatCents(a.balance_cents)}
          </p>
          {a.balance_date && <p className="text-xs text-slate-500">au {formatDate(a.balance_date)}</p>}
        </div>
      </div>

      {editing ? (
        <form onSubmit={saveBalance} className="mt-3 flex gap-2">
          <input className="input" inputMode="decimal" autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder="Nouveau solde" />
          <button className="btn">OK</button>
          <button type="button" className="btn-ghost" onClick={() => setEditing(false)}>Annuler</button>
        </form>
      ) : (
        <div className="mt-2 flex gap-1">
          <button className="btn-ghost" onClick={() => setEditing(true)}>Mettre à jour le solde</button>
          <button className="btn-ghost text-red-600" onClick={archive}>Archiver</button>
        </div>
      )}
    </li>
  );
}
