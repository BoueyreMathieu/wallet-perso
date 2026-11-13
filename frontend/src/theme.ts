/** Mode clair / sombre. « system » (par défaut) suit le réglage de l'appareil. */
export type ThemePref = "system" | "light" | "dark";

const KEY = "wallet-theme";
const media = () => window.matchMedia("(prefers-color-scheme: dark)");

export function getThemePref(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

export function applyTheme(pref: ThemePref = getThemePref()) {
  const dark = pref === "dark" || (pref === "system" && media().matches);
  document.documentElement.classList.toggle("dark", dark);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#0b1020" : "#f6f5fb");
}

export function setThemePref(pref: ThemePref) {
  try {
    if (pref === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, pref);
  } catch {
    /* stockage indisponible : le choix vaut pour cette visite */
  }
  applyTheme(pref);
}

/** Suit les changements du réglage système tant que la préférence est « system ». */
export function watchSystemTheme() {
  media().addEventListener("change", () => {
    if (getThemePref() === "system") applyTheme("system");
  });
}

export const THEME_LABELS: Record<ThemePref, { icon: string; label: string }> = {
  system: { icon: "🖥️", label: "Auto" },
  light: { icon: "☀️", label: "Clair" },
  dark: { icon: "🌙", label: "Sombre" },
};
