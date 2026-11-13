import { FormEvent, useState } from "react";
import { ApiError, api } from "../api";
import { isNative, savedServer, saveNativeSession } from "../native";

export default function Login({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const native = isNative();
  const [server, setServer] = useState(savedServer() || "https://");
  const [deviceName, setDeviceName] = useState("Mon téléphone");

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (native) {
        // Appli : on demande un jeton d'appareil au serveur choisi (il sert aussi aux widgets).
        const url = server.trim().replace(/\/+$/, "");
        let res: Response;
        try {
          res = await fetch(`${url}/api/auth/device`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password, name: deviceName.trim() || "Android" }),
          });
        } catch {
          throw new ApiError(0, "injoignable");
        }
        if (!res.ok) throw new ApiError(res.status, res.statusText);
        const { token } = (await res.json()) as { token: string };
        await saveNativeSession(url, token);
      } else {
        await api.post("/auth/login", { password });
      }
      onLogin();
    } catch (err) {
      const status = err instanceof ApiError ? err.status : 0;
      setError(
        status === 401
          ? "Mot de passe incorrect"
          : native && status === 0
            ? "Serveur injoignable : vérifie l'adresse, que Tailscale est connecté sur le téléphone et que le serveur tourne."
            : `Le serveur ne répond pas correctement (erreur ${status || "réseau"}). Regarde « docker compose logs api ».`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-accent-100 via-surface to-fuchsia-100 px-4 dark:from-accent-900/40 dark:via-surface-dark dark:to-fuchsia-900/30">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <div className="flex items-center gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-2xl bg-gradient-to-br from-accent-500 to-fuchsia-500 text-xl text-white">€</span>
          <div>
            <h1 className="text-xl font-bold">Wallet perso</h1>
            <p className="muted text-sm">Content de te revoir 👋</p>
          </div>
        </div>
        {native && (
          <>
            <label className="block space-y-1 text-sm">
              <span className="muted">Adresse du serveur</span>
              <input className="input" inputMode="url" autoCapitalize="off" value={server} onChange={(e) => setServer(e.target.value)} placeholder="https://wallet.<ton-réseau>.ts.net" />
            </label>
            <label className="block space-y-1 text-sm">
              <span className="muted">Nom de cet appareil</span>
              <input className="input" value={deviceName} onChange={(e) => setDeviceName(e.target.value)} />
            </label>
          </>
        )}
        <input
          type="password"
          className="input"
          placeholder="Mot de passe"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button className="btn w-full" disabled={busy || !password || (native && !/^https?:\/\/.+/.test(server.trim()))}>Se connecter</button>
      </form>
    </div>
  );
}
