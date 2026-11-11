import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { api } from "./api";
import Accounts from "./pages/Accounts";
import Home from "./pages/Home";
import Login from "./pages/Login";

const NAV = [
  { to: "/", label: "Accueil" },
  { to: "/comptes", label: "Comptes" },
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

  return (
    <div className="mx-auto max-w-5xl px-4 pb-24 sm:pb-8">
      <header className="flex items-center justify-between py-4">
        <span className="text-lg font-semibold">Wallet perso</span>
        <nav className="hidden gap-1 sm:flex">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end className={({ isActive }) => `btn-ghost ${isActive ? "font-semibold" : ""}`}>
              {n.label}
            </NavLink>
          ))}
          <button className="btn-ghost" onClick={logout}>Déconnexion</button>
        </nav>
        <button className="btn-ghost sm:hidden" onClick={logout}>Déconnexion</button>
      </header>

      <main>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/comptes" element={<Accounts />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>

      {/* Barre de navigation en bas sur mobile */}
      <nav className="fixed inset-x-0 bottom-0 flex justify-around border-t border-slate-200 bg-white py-2 sm:hidden dark:border-slate-800 dark:bg-slate-900">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end className={({ isActive }) => `px-4 py-2 text-sm ${isActive ? "font-semibold" : "text-slate-500"}`}>
            {n.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
