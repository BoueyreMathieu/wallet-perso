/** Mode démo : quand le serveur est injoignable, l'appli affiche un jeu de données **fictif** (bandeau « données de
 *  test ») au lieu d'une erreur, et revient d'elle-même aux vraies données dès que le serveur répond.
 *
 *  Le jeu de données (public/demo/snapshot.json) est produit par le vrai serveur sur des comptes inventés :
 *  `python -m app.tools.demo_snapshot` (voir docs/demo.md). Sans ce fichier, rien ne change.
 *  Pour retirer le mode démo : DEMO_ENABLED = false, ou suivre docs/demo.md. */
import { apiBase, authHeader } from "../native";

export const DEMO_ENABLED = true;

interface Snapshot {
  version: number;
  generated_at: string;
  today: string;
  responses: Record<string, unknown>;
  transactions: DemoTx[];
}
interface DemoTx {
  account_id: number;
  booked_at: string;
  category_id: number | null;
  merchant_id: number | null;
  merchant: string | null;
  raw_label: string;
  tags?: { id: number }[];
}

let snapshot: Promise<Snapshot | null> | null = null;
let active = false;
let since: string | null = null;
const listeners = new Set<() => void>();

export const demoActive = () => active;
export const demoGeneratedAt = () => since;
export function onDemoChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function load(): Promise<Snapshot | null> {
  snapshot ??= fetch("/demo/snapshot.json", { cache: "no-cache" })
    .then((r) => (r.ok ? r.json() : null))
    .then((s) => (s && s.version === 1 && s.responses ? (s as Snapshot) : null))
    .catch(() => null);
  return snapshot;
}

/** Le serveur répond-il (quelle que soit la réponse) ? */
export async function serverReachable(timeoutMs = 5000): Promise<boolean> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    await fetch(`${apiBase()}/api/auth/me`, { credentials: "same-origin", headers: authHeader(), signal: ctrl.signal });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

function activate(s: Snapshot) {
  if (active) return;
  active = true;
  since = s.generated_at;
  listeners.forEach((fn) => fn());
  // Dès que le serveur répond à nouveau : on recharge, les vraies données reprennent leur place.
  const timer = setInterval(async () => {
    if (await serverReachable()) {
      clearInterval(timer);
      window.location.reload();
    }
  }, 15000);
}

/** Même clé que le générateur (backend/app/tools/demo_snapshot.py) : paramètres triés, vides ignorés. */
function keyOf(method: string, path: string): string {
  const [p, q = ""] = path.split("?");
  const params = [...new URLSearchParams(q).entries()].filter(([, v]) => v !== "").sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `${method} ${p}${params.length ? "?" + params.map(([k, v]) => `${k}=${v}`).join("&") : ""}`;
}

/** Opérations filtrées comme le ferait le serveur (compte, catégorie et sous-catégories, vendeur, recherche, dates). */
function transactions(s: Snapshot, query: string) {
  const q = new URLSearchParams(query);
  const cats = (s.responses["GET /categories"] as { id: number; parent_id: number | null }[] | undefined) ?? [];
  const num = (k: string) => (q.get(k) ? Number(q.get(k)) : null);
  const account = num("account_id"), category = num("category_id"), merchant = num("merchant_id"), tag = num("tag_id");
  const family = category === null ? null : new Set([category, ...cats.filter((c) => c.parent_id === category).map((c) => c.id)]);
  const text = (q.get("q") ?? "").toLowerCase();
  const from = q.get("date_from"), to = q.get("date_to");
  const items = s.transactions.filter(
    (t) =>
      (account === null || t.account_id === account) &&
      (family === null || (t.category_id !== null && family.has(t.category_id))) &&
      (merchant === null || t.merchant_id === merchant) &&
      (q.get("no_merchant") !== "true" || t.merchant_id === null) &&
      (q.get("uncategorized") !== "true" || t.category_id === null) &&
      (tag === null || (t.tags ?? []).some((x) => x.id === tag)) &&
      (!text || t.raw_label.toLowerCase().includes(text) || (t.merchant ?? "").toLowerCase().includes(text)) &&
      (!from || t.booked_at >= from) &&
      (!to || t.booked_at <= to),
  );
  const offset = num("offset") ?? 0, limit = num("limit") ?? 100;
  return { items: items.slice(offset, offset + limit), total: items.length };
}

function answer(s: Snapshot, method: string, path: string): { data: unknown } | { error: string } {
  const [p, query = ""] = path.split("?");
  const readOnly = method === "GET" || (method === "POST" && (p === "/forecast" || p === "/projection"));
  if (!readOnly) return { error: "Mode démo (serveur injoignable) : rien n'est enregistré." };
  if (method === "GET" && p === "/transactions") return { data: transactions(s, query) };
  const key = keyOf(method, path);
  if (key in s.responses) return { data: s.responses[key] };
  // Même adresse avec d'autres réglages (autre période, scénario…) : la réponse enregistrée la plus proche.
  const wanted = new Set(key.split("?")[1]?.split("&") ?? []);
  let best: string | null = null, bestScore = -1;
  for (const k of Object.keys(s.responses)) {
    if (k.split("?")[0] !== `${method} ${p}`) continue;
    const have = k.split("?")[1]?.split("&") ?? [];
    const score = have.filter((x) => wanted.has(x)).length * 10 - have.filter((x) => !wanted.has(x)).length;
    if (score > bestScore) [best, bestScore] = [k, score];
  }
  if (best) return { data: s.responses[best] };
  return { error: "Pas disponible en mode démo (serveur injoignable)." };
}

/** Réponse du jeu de démo, ou null s'il n'y a pas de jeu de démo (l'erreur réseau suit alors son cours).
 *  `confirmOffline` : vérifie d'abord que le serveur est vraiment injoignable (et pas juste lent). */
export async function demoAnswer(method: string, path: string, confirmOffline: boolean): Promise<{ data: unknown } | { error: string } | null> {
  if (!DEMO_ENABLED) return null;
  const s = await load();
  if (!s) return null;
  if (!active && confirmOffline && (await serverReachable())) return null;
  activate(s);
  return answer(s, method, path);
}
