// Thème appliqué avant l'affichage (évite un flash clair en mode sombre).
// Dans un fichier séparé (et non dans index.html) : la politique de sécurité (CSP) interdit les scripts en ligne.
(function () {
  var pref = "system";
  try { pref = localStorage.getItem("wallet-theme") || "system"; } catch (e) {}
  var dark = pref === "dark" || (pref !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  if (dark) document.documentElement.classList.add("dark");
})();
