import { useEffect, useState } from "react";
import { demoActive, demoGeneratedAt, onDemoChange } from "./demo";

function useDemo() {
  const [on, setOn] = useState(demoActive());
  useEffect(() => onDemoChange(() => setOn(demoActive())), []);
  return on;
}

/** Bandeau en haut des pages quand l'appli affiche le jeu de données fictif. */
export function DemoBanner() {
  const on = useDemo();
  if (!on) return null;
  const when = demoGeneratedAt();
  return (
    <div className="mb-4 flex items-start gap-3 rounded-2xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-100" role="status">
      <span aria-hidden className="text-lg leading-none">🧪</span>
      <div className="min-w-0">
        <p className="font-semibold">Données de test : le serveur est injoignable</p>
        <p className="text-xs opacity-80">
          Comptes et opérations inventés{when ? ` (jeu du ${new Date(when).toLocaleDateString("fr-FR")})` : ""}, rien n'est enregistré. Tes vraies
          données reviennent toutes seules dès que la connexion revient.
        </p>
      </div>
    </div>
  );
}

/** Petite pastille « TEST » pour l'en-tête. */
export function DemoChip() {
  const on = useDemo();
  if (!on) return null;
  return <span className="chip bg-amber-100 text-[11px] font-semibold text-amber-800 dark:bg-amber-500/20 dark:text-amber-200">🧪 TEST</span>;
}
