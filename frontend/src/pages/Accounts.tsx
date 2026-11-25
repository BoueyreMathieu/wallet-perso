import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Account, AccountType, api } from "../api";
import { BankPicker, Conn, ConnectionHeader, UnlinkedBankAccounts, useBankConnections } from "../components/bankConnections";
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
  const bank = useBankConnections(load);

  const linked = new Set(bank.conns.flatMap((c) => c.accounts.map((a) => a.account_id)).filter((id): id is number => id !== null));
  const byConnection = (c: Conn) => accounts.filter((a) => c.accounts.some((r) => r.account_id === a.id));
  const others = accounts.filter((a) => !linked.has(a.id));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Comptes</h1>
        <button className="btn" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "Annuler" : "Ajouter un compte"}
        </button>
      </div>

      {bank.msg && <p className={`card text-sm ${bank.msg.error ? "text-red-600" : ""}`}>{bank.msg.text}</p>}

      {showForm && (
        <NewAccountForm
          onCreated={() => {
            setShowForm(false);
            load();
          }}
        />
      )}

      {bank.conns.map((c) => (
        <section key={c.id} className="card space-y-3">
          <ConnectionHeader
            c={c}
            busy={bank.busy === c.id}
            onSync={() => bank.syncNow(c)}
            onRenew={() => bank.start(c.label, c.id)}
            onRemove={() => bank.remove(c)}
          />
          <ul className="space-y-2">
            {byConnection(c).map((a) => (
              <AccountRow
                key={a.id}
                account={a}
                onChange={load}
                onUnlink={() => {
                  const uid = c.accounts.find((r) => r.account_id === a.id)?.uid;
                  if (uid && confirm(`Ne plus synchroniser « ${a.name} » ? Le compte et ses opérations sont gardés.`)) bank.mapAccount(c, uid, "");
                }}
              />
            ))}
          </ul>
          <UnlinkedBankAccounts c={c} accounts={accounts} onMap={(uid, value) => bank.mapAccount(c, uid, value)} />
        </section>
      ))}

      <section className="space-y-2">
        {bank.conns.length > 0 && others.length > 0 && <h2 className="section-title px-1">✋ Comptes sans synchro</h2>}
        <p className="px-1 text-xs text-slate-500">
          Solde affiché = dernier solde connu (synchro, import ou mise à jour à la main) + opérations datées après.
        </p>
        {accounts.length === 0 && !showForm && (
          <p className="card text-sm text-slate-500">Aucun compte. Connecte ta banque ci-dessous, ou ajoute un compte à la main.</p>
        )}
        <ul className="space-y-2">
          {others.map((a) => (
            <AccountRow key={a.id} account={a} onChange={load} />
          ))}
        </ul>
      </section>

      {bank.config?.configured ? (
        <BankPicker onPick={(name) => bank.start(name)} syncHours={bank.config.sync_interval_hours} />
      ) : (
        bank.config && (
          <p className="card text-sm">
            🔗 Pour synchroniser tes banques automatiquement, configure d'abord Enable Banking :{" "}
            <Link to="/parametres/connexions" className="font-medium text-accent-600 hover:underline dark:text-accent-300">Paramètres › Connexions</Link>.
          </p>
        )
      )}
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

function AccountRow({ account: a, onChange, onUnlink }: { account: Account; onChange: () => void; onUnlink?: () => void }) {
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

  const checked = async () => {
    await api.post(`/accounts/${a.id}/balance-check/ok`);
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
            {a.institution && !a.connection_id && ` · ${a.institution}`}
            {!a.connection_id && " · ✋ à la main ou par import"}
          </p>
          {a.balance_gap_cents === 0 && <p className="text-xs text-emerald-700 dark:text-emerald-400">✓ Cohérent avec la banque</p>}
        </div>
        <div className="text-right">
          <p className={`font-semibold tabular-nums ${(a.balance_cents ?? 0) < 0 ? "text-red-600" : ""}`}>
            {a.balance_cents === null ? "—" : formatCents(a.balance_cents)}
          </p>
          {a.balance_date && <p className="text-xs text-slate-500">au {formatDate(a.balance_date)}</p>}
          {a.pending_count > 0 && (
            <p className="text-xs text-amber-700 dark:text-amber-300">
              ⏳ {formatCents(a.pending_cents)} à venir ({a.pending_count}) · prévu {formatCents((a.balance_cents ?? 0) + a.pending_cents)}
            </p>
          )}
        </div>
      </div>

      {a.balance_gap_cents != null && a.balance_gap_cents !== 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-100">
          <span className="min-w-0 flex-1">
            🧮 Le solde de la banque et tes opérations diffèrent de <b>{formatCents(a.balance_gap_cents)}</b>
            {a.balance_gap_since ? ` depuis le ${formatDate(a.balance_gap_since)}` : ""} : une opération manque ({a.balance_gap_cents > 0 ? "une rentrée" : "une dépense"}) ou est en double ?
          </span>
          <button className="btn-ghost px-2 py-1 text-xs font-semibold" onClick={checked}>J'ai vérifié</button>
        </div>
      )}

      {editing ? (
        <form onSubmit={saveBalance} className="mt-3 flex gap-2">
          <input className="input" inputMode="decimal" autoFocus value={value} onChange={(e) => setValue(e.target.value)} placeholder="Nouveau solde" />
          <button className="btn">OK</button>
          <button type="button" className="btn-ghost" onClick={() => setEditing(false)}>Annuler</button>
        </form>
      ) : (
        <div className="mt-2 flex gap-1">
          {!a.connection_id && <button className="btn-ghost" onClick={() => setEditing(true)}>Mettre à jour le solde</button>}
          {onUnlink && <button className="btn-ghost" onClick={onUnlink}>Ne plus synchroniser</button>}
          <button className="btn-ghost text-red-600" onClick={archive}>Archiver</button>
        </div>
      )}
    </li>
  );
}
