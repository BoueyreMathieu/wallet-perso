import { useEffect, useState } from "react";
import { api } from "../api";

interface Group {
  merchants: { id: number; name: string; count: number }[];
  proposed_id: number;
}

/** Vendeurs probablement identiques (même début de nom) : fusionner ou ignorer. */
export function SimilarMerchants({ onChanged }: { onChanged: () => void }) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const load = () => api.get<Group[]>("/merchants/similar").then(setGroups);
  useEffect(() => {
    load();
  }, []);

  if (groups.length === 0 && !msg) return null;
  return (
    <section className="card space-y-3 border-accent-200 dark:border-accent-500/20">
      <div>
        <h2 className="section-title">🔀 Vendeurs à regrouper ? ({groups.length})</h2>
        <p className="muted text-sm">
          Ces noms commencent pareil mais la suite diffère : c'est peut-être le même vendeur. Les cas évidents (nom tronqué,
          référence en plus) sont déjà fusionnés automatiquement.
        </p>
      </div>
      {msg && <p className="text-sm">{msg}</p>}
      <ul className="space-y-2">
        {groups.slice(0, 10).map((g) => (
          <GroupRow
            key={g.merchants.map((m) => m.id).join("-")}
            group={g}
            onDone={(text) => {
              setMsg(text);
              load();
              onChanged();
            }}
          />
        ))}
      </ul>
      {groups.length > 10 && <p className="muted text-xs">… et {groups.length - 10} autre(s) après celles-ci.</p>}
    </section>
  );
}

function GroupRow({ group, onDone }: { group: Group; onDone: (msg: string) => void }) {
  const [checked, setChecked] = useState<number[]>(group.merchants.map((m) => m.id));
  const [target, setTarget] = useState<number>(group.proposed_id);
  const [name, setName] = useState(group.merchants.find((m) => m.id === group.proposed_id)?.name ?? "");
  const [busy, setBusy] = useState(false);

  const toggle = (id: number) => setChecked((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const ids = checked.includes(target) ? checked : [...checked, target];

  const merge = async () => {
    setBusy(true);
    try {
      await api.post("/merchants/merge-group", { ids, target_id: target, name });
      const left = group.merchants.filter((m) => !ids.includes(m.id)).map((m) => m.id);
      if (left.length) await api.post("/merchants/similar/ignore", { ids: [target, ...left] });
      onDone(`${ids.length} vendeurs regroupés sous « ${name} ».`);
    } catch (err) {
      onDone((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const ignore = async () => {
    await api.post("/merchants/similar/ignore", { ids: group.merchants.map((m) => m.id) });
    onDone("Compris : ces vendeurs restent séparés.");
  };

  return (
    <li className="space-y-2 rounded-xl bg-slate-50 p-3 dark:bg-white/5">
      <div className="flex flex-wrap gap-2">
        {group.merchants.map((m) => (
          <label key={m.id} className={`chip cursor-pointer px-2 py-1 text-sm ${checked.includes(m.id) ? "bg-accent-100 text-accent-800 dark:bg-accent-500/20 dark:text-accent-100" : "bg-white text-slate-500 dark:bg-white/5"}`}>
            <input type="checkbox" className="mr-1" checked={checked.includes(m.id)} onChange={() => toggle(m.id)} />
            {m.name} <span className="muted text-xs">· {m.count} op.</span>
            <button
              type="button"
              className={`ml-1 text-xs ${target === m.id ? "text-accent-700 dark:text-accent-200" : "opacity-50 hover:opacity-100"}`}
              title="Garder ce nom"
              onClick={(e) => {
                e.preventDefault();
                setTarget(m.id);
                setName(m.name);
              }}
            >
              {target === m.id ? "★" : "☆"}
            </button>
          </label>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input className="input w-auto flex-1 py-1.5 text-sm" value={name} onChange={(e) => setName(e.target.value)} aria-label="Nom du vendeur regroupé" />
        <button className="btn py-1.5 text-sm" disabled={busy || ids.length < 2 || !name.trim()} onClick={merge}>Regrouper</button>
        <button className="btn-ghost text-sm" onClick={ignore}>Ce sont des vendeurs différents</button>
      </div>
    </li>
  );
}
