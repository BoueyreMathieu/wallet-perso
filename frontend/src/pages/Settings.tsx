import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "../api";
import { ThemeSwitch } from "../components/ThemeSwitch";
import Connections from "./Connections";
import Data from "./Data";
import Import from "./Import";
import Security from "./Security";

const TABS = [
  { to: "connexions", label: "Connexions", icon: "🔗" },
  { to: "importer", label: "Importer", icon: "📥" },
  { to: "donnees", label: "Données", icon: "🧰" },
  { to: "securite", label: "Sécurité", icon: "🔒" },
  { to: "preferences", label: "Préférences", icon: "🎨" },
];

export default function Settings({ onLogout }: { onLogout: () => void }) {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Paramètres</h1>
      <nav className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={`/parametres/${t.to}`}
            className={({ isActive }) =>
              `chip shrink-0 px-3 py-1.5 text-sm ${isActive ? "bg-accent-600 text-white" : "bg-panel text-slate-600 shadow-soft dark:bg-panel-dark dark:text-slate-300"}`
            }
          >
            <span aria-hidden>{t.icon}</span> {t.label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route path="categories" element={<Navigate to="/categories" replace />} />
        <Route path="connexions" element={<Connections />} />
        <Route path="importer" element={<Import />} />
        <Route path="donnees" element={<Data />} />
        <Route path="securite" element={<Security />} />
        <Route path="preferences" element={<Preferences onLogout={onLogout} />} />
        <Route path="*" element={<Navigate to="/parametres/connexions" />} />
      </Routes>
    </div>
  );
}

interface OwnerState {
  signatures: string[];
  matching_merchants: string[];
  operations: number;
}

function Preferences({ onLogout }: { onLogout: () => void }) {
  const [owner, setOwner] = useState<OwnerState | null>(null);
  const [text, setText] = useState("");
  const [preview, setPreview] = useState<OwnerState | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api.get<OwnerState>("/settings/owner").then((o) => {
      setOwner(o);
      setText(o.signatures.join("\n"));
    });
  }, []);

  const names = text.split("\n").map((s) => s.trim()).filter(Boolean);
  const changed = owner !== null && names.join("|").toUpperCase() !== owner.signatures.join("|");

  useEffect(() => {
    if (!changed) {
      setPreview(null);
      return;
    }
    const t = setTimeout(() => api.post<OwnerState>("/settings/owner/preview", { signatures: names }).then(setPreview), 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const save = async () => {
    const o = await api.put<OwnerState>("/settings/owner", { signatures: names });
    setOwner(o);
    setText(o.signatures.join("\n"));
    setMsg(`Enregistré : ${o.operations} opération(s) reconnue(s) comme virements entre tes comptes.`);
  };

  const shown = preview ?? owner;

  return (
    <div className="space-y-4">
      <section className="card space-y-3">
        <h2 className="section-title">Apparence</h2>
        <ThemeSwitch />
        <p className="muted text-xs">« Auto » suit le réglage clair/sombre de ton appareil. Aussi disponible en bas du menu.</p>
      </section>

      <section className="card space-y-3">
        <h2 className="section-title">↔ Ton nom de titulaire</h2>
        <p className="muted text-sm">
          Un vendeur dont le nom commence par ton nom (virement vers ou depuis un de tes comptes) est rangé en « Virement
          interne » et sort des dépenses et revenus. Une variante par ligne, telle qu'elle apparaît au début des libellés
          (ex. civilité + nom, même tronqué). Il est appris automatiquement de tes exports CSV.
        </p>
        <textarea className="input min-h-[5rem] font-mono text-sm" value={text} onChange={(e) => setText(e.target.value)} placeholder="MONSIEUR NOM PRENOM" />
        {shown && (
          <p className="text-sm">
            {shown.matching_merchants.length > 0 ? (
              <>
                {changed ? "Avec ces noms : " : "Reconnus : "}
                <b>{shown.matching_merchants.length}</b> vendeur(s), {shown.operations} opération(s) —{" "}
                <span className="muted">{shown.matching_merchants.slice(0, 8).join(", ")}{shown.matching_merchants.length > 8 ? "…" : ""}</span>
              </>
            ) : (
              <span className="muted">Aucun vendeur reconnu.</span>
            )}
          </p>
        )}
        <p className="muted text-xs">Un proche qui porte le même nom serait reconnu aussi : ajoute alors le début de ton prénom.</p>
        <button className="btn" disabled={!changed} onClick={save}>Enregistrer</button>
        {msg && <p className="text-sm">{msg}</p>}
      </section>

      <section className="card flex items-center justify-between">
        <span className="text-sm">Session</span>
        <button className="btn-ghost text-red-600" onClick={onLogout}>Se déconnecter</button>
      </section>
    </div>
  );
}
