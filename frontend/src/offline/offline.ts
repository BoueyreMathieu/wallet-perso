/** Mode hors ligne (appli Android) : les réponses du serveur sont gardées sur le téléphone, chiffrées par une clé du
 *  Keystore Android (plugin natif « SecureCache », voir android-overlay/…/SecureCachePlugin.java). Quand le serveur est
 *  injoignable, l'appli affiche ces dernières données, en lecture seule, avec un bandeau ; elle revient d'elle-même au
 *  direct dès que le serveur répond. Sans copie hors ligne (premier lancement, navigateur), c'est le jeu de test qui
 *  prend le relais (demo/demo.ts).
 *
 *  Ce qui est gardé : chaque écran tel qu'il a été vu la dernière fois avec la connexion (même adresse, mêmes réglages).
 *  Les opérations vues sont réunies et filtrées sur le téléphone (compte, catégorie, recherche…).
 *  Tout est effacé à la déconnexion. */
import { registerPlugin } from "@capacitor/core";
import { isNative } from "../native";
import { closestKey, filterTransactions, keyOf, serverReachable, type DemoTx } from "../demo/demo";

interface SecureCachePlugin {
  put(o: { name: string; value: string }): Promise<void>;
  get(o: { name: string }): Promise<{ value: string | null }>;
  remove(o: { name: string }): Promise<void>;
  clear(): Promise<void>;
}
const SecureCache = registerPlugin<SecureCachePlugin>("SecureCache");

const INDEX = "__index__";
const MAX_ENTRIES = 250; // au-delà, les écrans les plus anciens sont oubliés
const SKIP = /^(POST|PUT|PATCH|DELETE) |^GET \/(auth\/device|export)/; // jamais gardés

type Index = Record<string, number>; // clé (méthode + adresse) → date de la réponse (ms)

let index: Promise<Index> | null = null;
let active = false;
let lastAt: number | null = null;
const listeners = new Set<() => void>();

export const offlineActive = () => active;
/** Date des données affichées hors ligne (la plus récente réponse gardée). */
export const offlineSince = () => lastAt;
export function onOfflineChange(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// Le nom du fichier sur le téléphone ne révèle rien (empreinte), le contenu est chiffré.
async function fileName(key: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(key));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function loadIndex(): Promise<Index> {
  index ??= SecureCache.get({ name: INDEX })
    .then((r) => (r.value ? (JSON.parse(r.value) as Index) : {}))
    .catch(() => ({}));
  return index;
}

let saving: ReturnType<typeof setTimeout> | null = null;
function saveIndexSoon(idx: Index) {
  if (saving) clearTimeout(saving);
  saving = setTimeout(() => {
    saving = null;
    SecureCache.put({ name: INDEX, value: JSON.stringify(idx) }).catch(() => undefined);
  }, 1500);
}

/** Lecture seule : ce qu'on peut garder pour le hors ligne (GET, et les calculs de prévision envoyés en POST). */
function readOnly(method: string, path: string): boolean {
  const p = path.split("?")[0];
  return method === "GET" || (method === "POST" && (p === "/forecast" || p === "/projection"));
}

/** Après une réponse réussie du serveur : la garder pour le hors ligne (appli Android seulement). */
export function remember(method: string, path: string, body: unknown, data: unknown): void {
  if (!isNative() || !readOnly(method, path) || data === undefined) return;
  const key = keyOf(method, path) + (method === "POST" && body !== undefined ? ` ${JSON.stringify(body)}` : "");
  if (SKIP.test(key)) return;
  void (async () => {
    try {
      const idx = await loadIndex();
      await SecureCache.put({ name: await fileName(key), value: JSON.stringify(data) });
      idx[key] = Date.now();
      const keys = Object.keys(idx).sort((a, b) => idx[b] - idx[a]);
      for (const old of keys.slice(MAX_ENTRIES)) {
        delete idx[old];
        SecureCache.remove({ name: await fileName(old) }).catch(() => undefined);
      }
      saveIndexSoon(idx);
    } catch {
      /* stockage indisponible : l'appli marche quand même, sans copie hors ligne */
    }
  })();
}

/** Y a-t-il une copie hors ligne de tes données sur ce téléphone ? */
export async function hasOfflineData(): Promise<boolean> {
  if (!isNative()) return false;
  return Object.keys(await loadIndex()).length > 0;
}

async function read(key: string): Promise<unknown> {
  const r = await SecureCache.get({ name: await fileName(key) });
  return r.value ? JSON.parse(r.value) : undefined;
}

/** Toutes les opérations vues (toutes listes confondues), sans doublon, de la plus récente à la plus ancienne. */
async function allTransactions(idx: Index): Promise<(DemoTx & { id: number })[]> {
  const seen = new Map<number, DemoTx & { id: number }>();
  for (const key of Object.keys(idx).filter((k) => k.split("?")[0] === "GET /transactions").sort((a, b) => idx[a] - idx[b])) {
    const page = (await read(key).catch(() => undefined)) as { items?: (DemoTx & { id: number })[] } | undefined;
    for (const t of page?.items ?? []) seen.set(t.id, t); // la version la plus récente l'emporte
  }
  return [...seen.values()].sort((a, b) => (a.booked_at < b.booked_at ? 1 : a.booked_at > b.booked_at ? -1 : b.id - a.id));
}

function activate(idx: Index) {
  if (active) return;
  active = true;
  lastAt = Math.max(...Object.values(idx));
  listeners.forEach((fn) => fn());
  // Dès que le serveur répond à nouveau : on recharge, le direct reprend.
  const timer = setInterval(async () => {
    if (await serverReachable()) {
      clearInterval(timer);
      window.location.reload();
    }
  }, 15000);
}

/** Réponse hors ligne, ou null s'il n'y a pas de copie hors ligne (le jeu de test prend alors le relais).
 *  `confirmOffline` : vérifie d'abord que le serveur est vraiment injoignable (et pas juste lent). */
export async function offlineAnswer(
  method: string,
  path: string,
  body: unknown,
  confirmOffline: boolean,
): Promise<{ data: unknown } | { error: string } | null> {
  if (!isNative()) return null;
  const idx = await loadIndex();
  if (Object.keys(idx).length === 0) return null;
  if (!active && confirmOffline && (await serverReachable())) return null;
  activate(idx);
  if (!readOnly(method, path)) return { error: "Hors ligne : rien n'est enregistré. Réessaie quand la connexion sera revenue." };
  const [p, query = ""] = path.split("?");
  try {
    const key = keyOf(method, path) + (method === "POST" && body !== undefined ? ` ${JSON.stringify(body)}` : "");
    if (key in idx) return { data: await read(key) };
    if (method === "GET" && p === "/transactions") {
      const cats = ((await read("GET /categories").catch(() => undefined)) as { id: number; parent_id: number | null }[] | undefined) ?? [];
      return { data: filterTransactions(await allTransactions(idx), cats, query) };
    }
    // Même écran avec d'autres réglages : la réponse gardée la plus proche.
    const best = closestKey(key.split(" {")[0], Object.keys(idx).map((k) => k.split(" {")[0]));
    const stored = best && Object.keys(idx).find((k) => k.split(" {")[0] === best);
    if (stored) return { data: await read(stored) };
  } catch {
    /* fichier illisible (clé du téléphone changée…) : traité comme absent */
  }
  return { error: "Pas disponible hors ligne : cet écran n'a pas encore été ouvert avec la connexion." };
}

/** À la déconnexion : la copie hors ligne est effacée du téléphone. */
export async function clearOfflineData(): Promise<void> {
  if (!isNative()) return;
  index = Promise.resolve({});
  await SecureCache.clear().catch(() => undefined);
}
