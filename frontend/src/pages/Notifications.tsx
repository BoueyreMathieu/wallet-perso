import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertItem, api } from "../api";
import { isNative } from "../native";

interface Kind {
  id: string;
  label: string;
  detail: string;
  enabled: boolean;
}

const LEVEL: Record<AlertItem["level"], string> = {
  danger: "border-l-rose-500",
  warning: "border-l-amber-500",
  info: "border-l-sky-500",
};

/** Paramètres › Notifications : types d'alertes activés (appli et téléphone), et alertes du moment. */
export default function Notifications() {
  const [kinds, setKinds] = useState<Kind[] | null>(null);
  const [alerts, setAlerts] = useState<AlertItem[] | null>(null);

  const loadAlerts = () => api.get<{ alerts: AlertItem[] }>("/alerts").then((r) => setAlerts(r.alerts), () => setAlerts([]));
  useEffect(() => {
    api.get<{ kinds: Kind[] }>("/settings/notifications").then((r) => setKinds(r.kinds), () => undefined);
    loadAlerts();
  }, []);

  const toggle = async (k: Kind) => {
    const r = await api.put<{ kinds: Kind[] }>("/settings/notifications", { kinds: { [k.id]: !k.enabled } });
    setKinds(r.kinds);
    loadAlerts();
  };

  return (
    <div className="space-y-4">
      <section className="card space-y-3">
        <h2 className="section-title">🔔 Ce qui te prévient</h2>
        <p className="muted text-xs">
          {isNative()
            ? "Le téléphone vérifie toutes les 30 minutes environ (Tailscale actif) et ne prévient qu'une fois par alerte. Le contenu est masqué sur l'écran verrouillé."
            : "Ces alertes s'affichent dans l'appli, et en notifications sur le téléphone (appli Android, toutes les 30 minutes environ)."}
        </p>
        <ul className="divide-y divide-slate-100 dark:divide-white/5">
          {(kinds ?? []).map((k) => (
            <li key={k.id} className="flex items-start gap-3 py-2.5">
              <div className="min-w-0 flex-1">
                <p className="font-medium">{k.label}</p>
                <p className="muted text-xs">{k.detail}</p>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={k.enabled}
                aria-label={k.label}
                onClick={() => toggle(k)}
                className={`relative mt-1 h-6 w-11 shrink-0 rounded-full transition ${k.enabled ? "bg-accent-600" : "bg-slate-300 dark:bg-white/15"}`}
              >
                <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition ${k.enabled ? "left-[22px]" : "left-0.5"}`} />
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="card space-y-2">
        <h2 className="section-title">En ce moment</h2>
        {alerts === null && <p className="muted text-sm">Chargement…</p>}
        {alerts?.length === 0 && <p className="muted text-sm">Rien à signaler. 👌</p>}
        <ul className="space-y-2">
          {(alerts ?? []).map((a) => (
            <li key={a.key} className={`rounded-xl border-l-4 bg-slate-50 px-3 py-2 dark:bg-white/5 ${LEVEL[a.level]}`}>
              <Link to={a.link} className="block">
                <p className="text-sm font-medium">{a.title}</p>
                <p className="muted text-xs">{a.body}</p>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
