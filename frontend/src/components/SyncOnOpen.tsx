import { useEffect, useState } from "react";
import { api } from "../api";
import { demoActive } from "../demo/demo";

interface SyncStale {
  running: boolean;
  synced: string[];
  imported: number;
  errors: { label: string; error: string }[];
}

/** À l'ouverture de l'appli (et quand on y revient) : synchronise les banques si la dernière synchro date de plus
 *  d'une heure (le serveur décide ; les banques limitent le nombre de synchros par jour). Petit message s'il y a du neuf. */
export function SyncOnOpen() {
  const [info, setInfo] = useState<SyncStale | null>(null);
  useEffect(() => {
    let last = 0;
    const run = () => {
      if (document.visibilityState !== "visible" || demoActive() || Date.now() - last < 10 * 60_000) return;
      last = Date.now();
      api.post<SyncStale>("/connections/sync-stale?max_age_minutes=60").then((r) => (r.imported > 0 || r.errors.length ? setInfo(r) : undefined), () => undefined);
    };
    run();
    document.addEventListener("visibilitychange", run);
    return () => document.removeEventListener("visibilitychange", run);
  }, []);
  if (!info) return null;
  return (
    <div className="fixed inset-x-3 bottom-20 z-40 mx-auto flex max-w-md items-center gap-3 rounded-2xl bg-slate-900 px-4 py-3 text-sm text-white shadow-xl sm:bottom-6 dark:bg-slate-700" role="status">
      <span className="min-w-0 flex-1">
        {info.imported > 0 && <>🔄 {info.imported} nouvelle{info.imported > 1 ? "s" : ""} opération{info.imported > 1 ? "s" : ""} synchronisée{info.imported > 1 ? "s" : ""}. </>}
        {info.errors.length > 0 && <>⚠️ Synchro impossible : {info.errors.map((e) => e.label).join(", ")} (voir Réglages › Connexions).</>}
      </span>
      {info.imported > 0 && <button className="shrink-0 font-semibold text-accent-200" onClick={() => window.location.reload()}>Actualiser</button>}
      <button className="shrink-0 opacity-70" onClick={() => setInfo(null)} aria-label="Fermer">✕</button>
    </div>
  );
}
