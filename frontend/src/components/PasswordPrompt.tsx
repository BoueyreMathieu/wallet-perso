import { FormEvent, useEffect, useRef, useState } from "react";
import { setPasswordAsker } from "../api";

/** Fenêtre « confirme avec ton mot de passe », ouverte par api.ts quand le serveur le demande (actions sensibles). */
export function PasswordPrompt() {
  const [message, setMessage] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const resolver = useRef<((v: string | null) => void) | null>(null);

  useEffect(() => {
    setPasswordAsker(
      (msg) =>
        new Promise((resolve) => {
          resolver.current = resolve;
          setValue("");
          setMessage(msg);
        }),
    );
    return () => setPasswordAsker(null);
  }, []);

  const close = (v: string | null) => {
    resolver.current?.(v);
    resolver.current = null;
    setMessage(null);
    setValue("");
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (value) close(value);
  };

  if (message === null) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4" onClick={() => close(null)}>
      <form className="card w-full max-w-sm space-y-3" onClick={(e) => e.stopPropagation()} onSubmit={submit}>
        <h2 className="section-title">🔒 Confirmation</h2>
        <p className="text-sm">{message}</p>
        <input
          className="input"
          type="password"
          autoFocus
          autoComplete="current-password"
          placeholder="Mot de passe de l'appli"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Escape" && close(null)}
        />
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={() => close(null)}>Annuler</button>
          <button type="submit" className="btn" disabled={!value}>Confirmer</button>
        </div>
      </form>
    </div>
  );
}
