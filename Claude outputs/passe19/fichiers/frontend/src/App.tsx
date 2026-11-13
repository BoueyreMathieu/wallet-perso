import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { App as CapApp } from "@capacitor/app";
import { api } from "./api";
import { clearNativeSession, isNative } from "./native";
import { CategoriesProvider } from "./components/categories";
import { TagsProvider } from "./components/tags";
import Accounts from "./pages/Accounts";
import Categories from "./pages/Categories";
import Home from "./pages/Home";
import Login from "./pages/Login";
import Merchants from "./pages/Merchants";
import Planning from "./pages/Planning";
import Recap from "./pages/Recap";
import Settings from "./pages/Settings";
import Transactions from "./pages/Transactions";
import { ThemeSwitch, ThemeToggle } from "./components/ThemeSwitch";
import { PasswordPrompt } from "./components/PasswordPrompt";
import { DemoBanner, DemoChip } from "./demo/DemoBanner"; // DÉMO (voir docs/demo.md)
import { SyncOnOpen } from "./components/SyncOnOpen";

const NAV = [
  { to: "/", label: "Accueil", icon: "🏠" },
  { to: "/operations", label: "Opérations", icon: "💳" },
  { to: "/prevoir", label: "Prévoir", icon: "🔮" },
  { to: "/vendeurs", label: "Vendeurs", icon: "🏪" },
  { to: "/categories", label: "Catégories", icon: "🗂️" },
  { to: "/comptes", label: "Comptes", icon: "🏦" },
  { to: "/parametres", label: "Paramètres", icon: "⚙️", short: "Réglages" },
];

// Anciennes adresses (avant la page Paramètres) : redirigées, en gardant ?ok=… / ?erreur=… du retour de banque.
const MOVED: Record<string, string> = {
  "/connexions": "connexions",
  "/importer": "importer",
  "/donnees": "donnees",
};

function Brand() {
  return (
    <div className="flex items-center gap-2">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-accent-500 to-fuchsia-500 text-lg text-white shadow-sm">€</span>
      <span className="text-lg font-bold tracking-tight">Wallet perso</span>
    </div>
  );
}

// Liens ouverts par les widgets Android : walletperso://add, walletperso://operations…
const DEEP_LINKS: Record<string, string> = {
  add: "/operations?nouvelle=1",
  operations: "/operations",
  categoriser: "/operations?a_categoriser=1",
  comptes: "/comptes",
  prevoir: "/prevoir",
  budgets: "/prevoir/budgets",
  home: "/",
};

function useDeepLinks() {
  const navigate = useNavigate();
  useEffect(() => {
    if (!isNative()) return;
    const open = (url: string | undefined) => {
      if (!url) return;
      const [key, query = ""] = url.replace(/^walletperso:\/\//, "").split("?", 2);
      const target = DEEP_LINKS[key.replace(/\/+$/, "")];
      if (!target) return;
      // Seul paramètre accepté : le compte (widget « Solde d'un compte » → ses opérations).
      const compte = new URLSearchParams(query).get("compte");
      navigate(compte && /^\d+$/.test(compte) ? `${target}${target.includes("?") ? "&" : "?"}compte=${compte}` : target);
    };
    CapApp.getLaunchUrl().then((r) => open(r?.url));
    const sub = CapApp.addListener("appUrlOpen", (e) => open(e.url));
    return () => {
      sub.then((h) => h.remove());
    };
  }, [navigate]);
}

// Changement de page : on repart du haut (un simple filtre ?… dans la même page ne fait pas remonter).
function useScrollTopOnPageChange() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
}

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  useDeepLinks();
  useScrollTopOnPageChange();

  useEffect(() => {
    api.get("/auth/me").then(() => setAuthed(true), () => setAuthed(false));
  }, []);

  if (authed === null) return null;
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const logout = async () => {
    if (isNative()) {
      await api.post("/auth/device/logout").catch(() => undefined); // révoque le jeton de ce téléphone
      await clearNativeSession();
    } else {
      await api.post("/auth/logout");
    }
    setAuthed(false);
  };
  const sideLink = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition ${
      isActive
        ? "bg-accent-50 font-semibold text-accent-700 dark:bg-accent-500/15 dark:text-accent-200"
        : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-white/5"
    }`;

  return (
    <CategoriesProvider>
      <TagsProvider>
        <PasswordPrompt />
        <SyncOnOpen />
        <div className="min-h-screen lg:flex">
          {/* Barre latérale (ordinateur) */}
          <aside className="sticky top-0 hidden h-screen w-56 shrink-0 flex-col gap-6 border-r border-slate-200/70 bg-panel p-4 lg:flex dark:border-white/5 dark:bg-panel-dark">
            <Brand />
            <nav className="flex flex-1 flex-col gap-1">
              {NAV.map((n) => (
                <NavLink key={n.to} to={n.to} end={n.to === "/"} className={sideLink}>
                  <span aria-hidden className="text-base">{n.icon}</span>
                  {n.label}
                </NavLink>
              ))}
            </nav>
            <div className="space-y-2">
              <ThemeSwitch compact />
              <button className="btn-ghost w-full justify-center muted" onClick={logout}>⎋ Déconnexion</button>
            </div>
          </aside>

          <div className="min-w-0 flex-1">
            {/* En-tête (téléphone / tablette) */}
            <header className="safe-top sticky top-0 z-20 flex items-center justify-between border-b border-slate-200/70 bg-surface/90 px-4 pb-3 backdrop-blur lg:hidden dark:border-white/5 dark:bg-surface-dark/90">
              <Brand />
              <nav className="hidden gap-1 sm:flex">
                {NAV.map((n) => (
                  <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => `btn-ghost ${isActive ? "font-semibold text-accent-700 dark:text-accent-200" : ""}`}>
                    {n.label}
                  </NavLink>
                ))}
              </nav>
              <div className="flex items-center gap-1">
                <DemoChip />
                <ThemeToggle />
                <button className="btn-ghost px-2 text-lg" onClick={logout} title="Déconnexion" aria-label="Déconnexion">⎋</button>
              </div>
            </header>

            <main className="mx-auto max-w-6xl px-4 pb-28 pt-4 sm:pb-10 lg:px-8 lg:pt-8">
              <DemoBanner />
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/operations" element={<Transactions />} />
                <Route path="/prevoir/*" element={<Planning />} />
                <Route path="/bilan" element={<Recap />} />
                <Route path="/vendeurs" element={<Merchants />} />
                <Route path="/comptes" element={<Accounts />} />
                <Route path="/categories" element={<Categories />} />
                <Route path="/parametres/*" element={<Settings onLogout={logout} />} />
                {Object.entries(MOVED).map(([from, tab]) => (
                  <Route key={from} path={from} element={<Navigate to={`/parametres/${tab}${window.location.search}`} replace />} />
                ))}
                <Route path="*" element={<Navigate to="/" />} />
              </Routes>
            </main>
          </div>

          {/* Barre du bas (téléphone) */}
          <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-7 border-t border-slate-200/70 bg-panel/95 safe-bottom backdrop-blur sm:hidden dark:border-white/5 dark:bg-panel-dark/95">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.to === "/"}
                className={({ isActive }) => `flex min-w-0 flex-col items-center gap-0.5 py-2 text-[10px] ${isActive ? "font-semibold text-accent-600 dark:text-accent-300" : "muted"}`}
              >
                <span aria-hidden className="text-lg leading-none">{n.icon}</span>
                <span className="w-full truncate text-center">{n.short ?? n.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      </TagsProvider>
    </CategoriesProvider>
  );
}
