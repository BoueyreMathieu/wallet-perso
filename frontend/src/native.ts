/** Appli Android (Capacitor) : adresse du serveur et jeton d'appareil.
 *
 * Dans le navigateur, rien ne change (même adresse que l'interface, cookie de session).
 * Dans l'appli, l'interface est embarquée dans le téléphone : elle appelle le serveur choisi à la connexion
 * (ex. https://wallet.<réseau>.ts.net) avec un jeton d'appareil. Ce jeton et l'adresse sont aussi rangés dans
 * les « Preferences » Capacitor, que les widgets Android lisent (SharedPreferences « CapacitorStorage »).
 */
import { Capacitor } from "@capacitor/core";
import { Preferences } from "@capacitor/preferences";

const SERVER_KEY = "server_url";
const TOKEN_KEY = "device_token";

export const isNative = () => Capacitor.isNativePlatform();

let server = "";
let token = "";

/** Au démarrage de l'appli : relit l'adresse et le jeton enregistrés. */
export async function loadNativeSession(): Promise<void> {
  if (!isNative()) return;
  server = (await Preferences.get({ key: SERVER_KEY })).value ?? "";
  token = (await Preferences.get({ key: TOKEN_KEY })).value ?? "";
}

export const apiBase = () => (isNative() ? server.replace(/\/+$/, "") : "");
export const authHeader = (): Record<string, string> => (isNative() && token ? { Authorization: `Bearer ${token}` } : {});
export const savedServer = () => server;

export async function saveNativeSession(serverUrl: string, deviceToken: string): Promise<void> {
  server = serverUrl.replace(/\/+$/, "");
  token = deviceToken;
  await Preferences.set({ key: SERVER_KEY, value: server });
  await Preferences.set({ key: TOKEN_KEY, value: token });
}

export async function clearNativeSession(): Promise<void> {
  token = "";
  await Preferences.remove({ key: TOKEN_KEY }); // l'adresse du serveur est gardée pour la prochaine connexion
}
