import { useEffect, useState } from "react";
import { demoActive, demoAvailable, demoForced, demoGeneratedAt, onDemoChange, setDemoForced } from "./demo";
import { offlineActive, offlineSince, onOfflineChange } from "../offline/offline";

function useDemo() {
  const [on, setOn] = useState(demoActive());
  useEffect(() => onDemoChange(() => setOn(demoActive())), []);
  return on;
}

function useOffline() {
  const [on, setOn] = useState(offlineActive());
  useEffect(() => onOfflineChange(() => setOn(offlineActive())), []);
  return on;
}

const fmt = (d: Date) => d.toLocaleString("fr-FR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

/** Bandeau en haut des pages : jeu de données fictif, ou tes dernières données hors ligne. */
export function DemoBanner() {
  const demo = useDemo();
  const offline = useOffline();
  if (offline && !demo) {
    const at = offlineSince();
    return (
      <div className="mb-4 flex items-start gap-3 rounded-2xl border border-sky-300 bg-sky-50 px-4 py-3 text-sm text-sky-900 dark:border-sky-500/30 dark:bg-sky-500/10 dark:text-sky-100" role="status">
        <span aria-hidden className="text-lg leading-none">📴</span>
        <div className="min-w-0">
          <p className="font-semibold">Hors ligne : le serveur est injoignable</p>
          <p className="text-xs opacity-80">
            Tes données telles qu'elles étaient{at ? ` le ${fmt(new Date(at))}` : ""}, en lecture seule. Le direct revient tout seul dès que la connexion revient.
          </p>
        </div>
      </div>
    );
  }
  if (!demo) return null;
  const when = demoGeneratedAt();
  const set = when ? ` (jeu du ${new Date(when).toLocaleDateString("fr-FR")})` : "";
  return (
    <div className="mb-4 flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100" role="status">
      <span aria-hidden className="text-lg leading-none">🧪</span>
      <div className="min-w-0 flex-1">
        {demoForced() ? (
          <>
            <p className="font-semibold">Données de test</p>
            <p className="text-xs opacity-80">Comptes et opérations inventés{set}, rien n'est enregistré. Tes vraies données ne sont pas affichées.</p>
          </>
        ) : (
          <>
            <p className="font-semibold">Données de test : le serveur est injoignable</p>
            <p className="text-xs opacity-80">
              Comptes et opérations inventés{set}, rien n'est enregistré. Tes vraies données reviennent toutes seules dès que la connexion revient.
            </p>
          </>
        )}
      </div>
      {demoForced() && (
        <button className="btn-ghost shrink-0 px-2 py-1 text-xs font-semibold" onClick={() => setDemoForced(false)}>
          Revenir à mes données
        </button>
      )}
    </div>
  );
}

/** Petite pastille « TEST » ou « HORS LIGNE » pour l'en-tête. */
export function DemoChip() {
  const demo = useDemo();
  const offline = useOffline();
  if (demo) return <span className="chip bg-amber-100 text-[11px] font-semibold text-amber-800 dark:bg-amber-500/20 dark:text-amber-200">🧪 TEST</span>;
  if (offline) return <span className="chip bg-sky-100 text-[11px] font-semibold text-sky-800 dark:bg-sky-500/20 dark:text-sky-200">📴 HORS LIGNE</span>;
  return null;
}

/** Bouton de l'accueil : bascule entre tes données et les données de test (à tout moment). */
export function DemoToggle() {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    demoAvailable().then(setAvailable, () => setAvailable(false));
  }, []);
  if (!available) return null;
  const on = demoForced();
  return (
    <button
      className={`btn-ghost px-3 text-sm ${on ? "text-amber-700 dark:text-amber-300" : ""}`}
      onClick={() => setDemoForced(!on)}
      aria-pressed={on}
      title={on ? "Revenir à mes données" : "Afficher des données de test (comptes inventés)"}
      aria-label={on ? "Revenir à mes données" : "Afficher des données de test"}
    >
      🧪
    </button>
  );
}
