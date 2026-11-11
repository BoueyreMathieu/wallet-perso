import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import { CategoriesProvider } from "./components/categories";
import { TagsProvider } from "./components/tags";
import Accounts from "./pages/Accounts";
import Data from "./pages/Data";
import Home from "./pages/Home";
import Import from "./pages/Import";
import Login from "./pages/Login";
import Merchants from "./pages/Merchants";
import Transactions from "./pages/Transactions";

// mobile : affiché dans la barre du bas (sinon dans l'en-tête)
const NAV = [
  { to: "/", label: "Accueil", mobile: true },
  { to: "/operations", label: "Opérations", mobile: true },
  { to: "/vendeurs", label: "Vendeurs", mobile: true },
  { to: "/comptes", label: "Comptes", mobile: true },
  { to: "/importer", label: "Importer", mobile: true },
  { to: "/donnees", label: "Données", mobile: false },
];

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    api.get("/auth/me").then(() => setAuthed(true), () => setAuthed(false));
  }, []);

  if (authed === null) return null;
  if (!authed) return <Login onLogin={() => setAuthed(true)} />;

  const logout = async () => {
    await api.post("/auth/logout");
    setAuthed(false);
  };
  const linkClass = ({ isActive }: { isActive: boolean }) => `btn-ghost ${isActive ? "font-semibold" : ""}`;

  return (
    <CategoriesProvider>
      <TagsProvider>
      <div className="mx-auto max-w-5xl px-4 pb-24 sm:pb-8">
        <header className="flex items-center justify-between py-4">
          <span className="text-lg font-semibold">Wallet perso</span>
          <nav className="hidden gap-1 sm:flex">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end className={linkClass}>
                {n.label}
              </NavLink>
            ))}
            <button className="btn-ghost" onClick={logout}>Déconnexion</button>
          </nav>
          <div className="flex gap-1 sm:hidden">
            {NAV.filter((n) => !n.mobile).map((n) => (
              <NavLink key={n.to} to={n.to} end className={linkClass}>
                {n.label}
              </NavLink>
            ))}
            <button className="btn-ghost" onClick={logout}>Déconnexion</button>
          </div>
        </header>

        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/operations" element={<Transactions />} />
            <Route path="/vendeurs" element={<Merchants />} />
            <Route path="/comptes" element={<Accounts />} />
            <Route path="/importer" element={<Import />} />
            <Route path="/donnees" element={<Data />} />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>

        {/* Barre de navigation en bas sur mobile */}
        <nav className="fixed inset-x-0 bottom-0 flex justify-around border-t border-slate-200 bg-white py-2 sm:hidden dark:border-slate-800 dark:bg-slate-900">
          {NAV.filter((n) => n.mobile).map((n) => (
            <NavLink key={n.to} to={n.to} end className={({ isActive }) => `px-1 py-2 text-xs ${isActive ? "font-semibold" : "text-slate-500"}`}>
              {n.label}
            </NavLink>
          ))}
        </nav>
      </div>
      </TagsProvider>
    </CategoriesProvider>
  );
}
