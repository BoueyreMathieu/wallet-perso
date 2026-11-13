import { useState } from "react";
import { THEME_LABELS, ThemePref, getThemePref, setThemePref } from "../theme";

export function ThemeSwitch({ compact = false }: { compact?: boolean }) {
  const [pref, setPref] = useState<ThemePref>(getThemePref());
  const choose = (p: ThemePref) => {
    setThemePref(p);
    setPref(p);
  };
  return (
    <div className={`flex rounded-xl bg-slate-100 p-1 dark:bg-white/5 ${compact ? "text-xs" : "text-sm"}`} role="radiogroup" aria-label="Thème">
      {(Object.keys(THEME_LABELS) as ThemePref[]).map((p) => (
        <button
          key={p}
          role="radio"
          aria-checked={pref === p}
          onClick={() => choose(p)}
          className={`flex flex-1 items-center justify-center gap-1 rounded-lg py-1.5 transition ${compact ? "px-1" : "px-3"} ${
            pref === p ? "bg-white font-semibold shadow-sm dark:bg-slate-700" : "muted hover:text-slate-700 dark:hover:text-slate-200"
          }`}
        >
          <span aria-hidden>{THEME_LABELS[p].icon}</span>
          {THEME_LABELS[p].label}
        </button>
      ))}
    </div>
  );
}

/** Bouton compact (en-tête mobile) : Auto → Clair → Sombre. */
export function ThemeToggle() {
  const [pref, setPref] = useState<ThemePref>(getThemePref());
  const order: ThemePref[] = ["system", "light", "dark"];
  const next = () => {
    const p = order[(order.indexOf(pref) + 1) % order.length];
    setThemePref(p);
    setPref(p);
  };
  return (
    <button className="btn-ghost px-2 text-lg" onClick={next} title={`Thème : ${THEME_LABELS[pref].label}`} aria-label={`Thème : ${THEME_LABELS[pref].label}`}>
      {THEME_LABELS[pref].icon}
    </button>
  );
}
