import { useEffect, useState } from "react";
import { api } from "../api";

interface Device {
  id: number;
  name: string;
  kind: "app" | "navigateur";
  created_at: string;
  last_used_at: string | null;
  current: boolean;
}

interface SecurityState {
  password_hashed: boolean;
  cookie_secure: boolean;
  lockout_seconds: number;
  backup: {
    last_ok_at: string | null;
    last_size_bytes: number | null;
    offsite: string | null;
    last_error_at: string | null;
    last_error: string | null;
    warning: string | null;
  };
  events: { created_at: string; kind: string; detail: string | null }[];
}

const EVENT_LABELS: Record<string, { icon: string; label: string; alert?: boolean }> = {
  connexion: { icon: "🔓", label: "Connexion" },
  echec_mdp: { icon: "⛔", label: "Mot de passe incorrect", alert: true },
  appareil_ajoute: { icon: "📱", label: "Appareil ajouté" },
  appareil_revoque: { icon: "🚫", label: "Appareil déconnecté" },
  deconnexion_globale: { icon: "🧹", label: "Autres sessions fermées" },
  confirmation: { icon: "🔒", label: "Action sensible confirmée" },
  mdp_change: { icon: "🔑", label: "Mot de passe changé" },
};

const fmt = (iso: string) => new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
const size = (bytes: number) => (bytes > 1e6 ? `${(bytes / 1e6).toFixed(1)} Mo` : `${Math.max(1, Math.round(bytes / 1e3))} Ko`);

export default function Security() {
  const [state, setState] = useState<SecurityState | null>(null);
  const [devices, setDevices] = useState<Device[]>([]);
  const [showAll, setShowAll] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    api.get<SecurityState>("/auth/security").then(setState);
    api.get<Device[]>("/auth/devices").then(setDevices);
  };
  useEffect(load, []);

  const revoke = async (d: Device) => {
    const what = d.kind === "app" ? "L'appli et ses widgets devront se reconnecter avec le mot de passe." : "Ce navigateur devra se reconnecter.";
    if (!confirm(`Déconnecter « ${d.name} » ? ${what}`)) return;
    await api.del(`/auth/devices/${d.id}`);
    load();
  };
  const logoutOthers = async () => {
    if (!confirm("Fermer toutes les autres sessions et déconnecter tous les autres appareils (téléphones compris) ?")) return;
    const r = await api.post<{ revoked: number }>("/auth/logout-others");
    setMsg(`${r.revoked} session(s) ou appareil(s) déconnecté(s).`);
    load();
  };

  const checks = state
    ? [
        { ok: state.password_hashed, good: "Mot de passe stocké sous forme d'empreinte", bad: "Mot de passe en clair dans .env : lance scripts\\securiser-env.ps1" },
        { ok: state.cookie_secure, good: "Cookie de session réservé au HTTPS", bad: "COOKIE_SECURE=false : mets-le à true dans .env (ou lance scripts\\securiser-env.ps1)" },
        { ok: !state.backup.warning, good: "Sauvegardes automatiques à jour", bad: state.backup.warning ?? "" },
      ]
    : [];
  const events = state ? (showAll ? state.events : state.events.slice(0, 8)) : [];
  const failures24h = state ? state.events.filter((e) => e.kind === "echec_mdp" && Date.now() - new Date(e.created_at).getTime() < 864e5).length : 0;

  return (
    <div className="space-y-4">
      <section className="card space-y-3">
        <h2 className="section-title">🛡️ État</h2>
        <ul className="space-y-1.5 text-sm">
          {checks.map((c) => (
            <li key={c.good} className={c.ok ? "" : "font-medium text-amber-700 dark:text-amber-300"}>
              {c.ok ? "✅" : "⚠️"} {c.ok ? c.good : c.bad}
            </li>
          ))}
          {failures24h > 0 && (
            <li className="font-medium text-red-600">
              ⛔ {failures24h} mot(s) de passe incorrect(s) en 24 h
              {state && state.lockout_seconds > 0 && ` — connexions bloquées encore ${Math.ceil(state.lockout_seconds / 60)} min`}
            </li>
          )}
        </ul>
        {state?.backup.last_ok_at && (
          <p className="muted text-xs">
            Dernière sauvegarde : {fmt(state.backup.last_ok_at)}
            {state.backup.last_size_bytes ? ` · ${size(state.backup.last_size_bytes)}` : ""}
            {state.backup.offsite ? ` · copie hors machine : ${state.backup.offsite}` : ""}
          </p>
        )}
      </section>

      <section className="card space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="section-title">📱 Sessions et appareils</h2>
          <button className="btn-ghost text-sm text-red-600" onClick={logoutOthers} disabled={devices.length < 2}>
            Déconnecter tous les autres
          </button>
        </div>
        <p className="muted text-sm">
          Chaque navigateur et chaque téléphone a son propre accès. Un navigateur inutilisé 14 jours est déconnecté, un
          téléphone au bout de 90 jours. En cas de perte ou de doute, déconnecte-le ici.
        </p>
        <ul className="divide-y divide-slate-100 text-sm dark:divide-white/5">
          {devices.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <p className="truncate font-medium">
                  {d.kind === "app" ? "📱" : "💻"} {d.name}
                  {d.current && <span className="chip ml-2 bg-accent-50 text-xs text-accent-700 dark:bg-accent-500/15 dark:text-accent-200">cet appareil</span>}
                </p>
                <p className="muted text-xs">
                  Connecté le {fmt(d.created_at)}
                  {d.last_used_at && ` · dernière utilisation ${fmt(d.last_used_at)}`}
                </p>
              </div>
              {!d.current && (
                <button className="btn-ghost text-red-600" onClick={() => revoke(d)}>Déconnecter</button>
              )}
            </li>
          ))}
        </ul>
        {msg && <p className="text-sm">{msg}</p>}
      </section>

      <section className="card space-y-3">
        <h2 className="section-title">📜 Journal de sécurité</h2>
        <p className="muted text-sm">Connexions, mots de passe incorrects, appareils ajoutés et actions sensibles. Un événement que tu ne reconnais pas : déconnecte tous les autres appareils et change le mot de passe.</p>
        <ul className="divide-y divide-slate-100 text-sm dark:divide-white/5">
          {events.map((e, i) => {
            const meta = EVENT_LABELS[e.kind] ?? { icon: "•", label: e.kind };
            return (
              <li key={i} className="flex items-baseline justify-between gap-3 py-1.5">
                <span className={`min-w-0 truncate ${meta.alert ? "text-red-600" : ""}`}>
                  {meta.icon} {meta.label}
                  {e.detail && <span className="muted"> · {e.detail}</span>}
                </span>
                <span className="muted shrink-0 text-xs">{fmt(e.created_at)}</span>
              </li>
            );
          })}
          {events.length === 0 && <li className="muted py-2">Rien pour l'instant.</li>}
        </ul>
        {state && state.events.length > 8 && (
          <button className="btn-ghost text-sm" onClick={() => setShowAll(!showAll)}>{showAll ? "Voir moins" : `Voir tout (${state.events.length})`}</button>
        )}
      </section>
    </div>
  );
}
