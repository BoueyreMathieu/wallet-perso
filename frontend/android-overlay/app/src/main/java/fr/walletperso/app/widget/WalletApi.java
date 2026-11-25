package fr.walletperso.app.widget;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;

import fr.walletperso.app.SecureStore;

/**
 * Appel du serveur Wallet pour les widgets (adresse + jeton enregistrés par l'appli à la connexion).
 * Un seul appel sert tous les widgets : le résumé est gardé, et réutilisé tel quel pendant une minute
 * (sauf ↻), pour que l'actualisation de 8 widgets ne fasse qu'un aller-retour vers le serveur.
 * Hors ligne, les widgets affichent ce dernier résumé avec sa date. Il est gardé chiffré (SecureStore) et effacé
 * à la déconnexion.
 */
final class WalletApi {
    /** Fichier des « Preferences » Capacitor (écrit par l'appli : server_url, device_token). */
    private static final String CAPACITOR_PREFS = "CapacitorStorage";
    /** Réglages des widgets (ex. compte choisi) et date du dernier résumé. */
    static final String PREFS = "WalletWidgets";
    private static final String SUMMARY = "widgets_summary";
    private static final long FRESH_MS = 60_000;
    private static final Object LOCK = new Object();

    private WalletApi() {}

    /** Résultat d'un chargement : données (éventuellement gardées) et ligne d'état à afficher. */
    static final class Result {
        final JSONObject data;
        final String status;
        final boolean ok;

        Result(JSONObject data, String status, boolean ok) {
            this.data = data;
            this.status = status;
            this.ok = ok;
        }
    }

    /** Résumé à jour (ou gardé s'il date de moins d'une minute et que force est faux). Jamais d'exception. */
    static Result load(Context ctx, boolean force) {
        synchronized (LOCK) {
            SharedPreferences prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
            long at = prefs.getLong("summary_at", 0);
            JSONObject cached = cached(ctx);
            if (!force && cached != null && System.currentTimeMillis() - at < FRESH_MS) {
                return new Result(cached, "Mis à jour " + when(at, "à "), true);
            }
            try {
                String raw = fetch(ctx);
                JSONObject json = new JSONObject(raw);
                long now = System.currentTimeMillis();
                SecureStore.put(ctx, SUMMARY, raw);
                prefs.edit().putLong("summary_at", now).apply();
                return new Result(json, "Mis à jour " + when(now, "à "), true);
            } catch (Exception e) {
                String msg;
                if (e instanceof IOException && !(e instanceof HttpError)) msg = "Hors ligne";
                else if (e instanceof org.json.JSONException) msg = "Réponse inattendue du serveur";
                else msg = e.getMessage() != null && !e.getMessage().isEmpty() ? e.getMessage() : "Serveur injoignable";
                if (cached != null) msg += " · données " + when(at, "de ");
                return new Result(cached, msg, false);
            }
        }
    }

    /** Dernier résumé connu, sans appel réseau (null après une déconnexion). */
    static JSONObject cached(Context ctx) {
        SharedPreferences prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        if (prefs.contains("summary")) {
            // Ancienne version : résumé gardé en clair → déplacé dans la copie chiffrée.
            String old = prefs.getString("summary", null);
            try {
                if (old != null) SecureStore.put(ctx, SUMMARY, old);
            } catch (Exception ignored) {
                // tant pis : il sera rechargé au prochain appel
            }
            prefs.edit().remove("summary").apply();
        }
        return parse(SecureStore.get(ctx, SUMMARY));
    }

    private static final class HttpError extends IOException {
        HttpError(String msg) {
            super(msg);
        }
    }

    private static String fetch(Context ctx) throws Exception {
        SharedPreferences p = ctx.getSharedPreferences(CAPACITOR_PREFS, Context.MODE_PRIVATE);
        String server = p.getString("server_url", null);
        String token = p.getString("device_token", null);
        if (server == null || server.isEmpty() || token == null || token.isEmpty()) {
            throw new IllegalStateException("Ouvre l'appli pour te connecter");
        }
        HttpURLConnection c = (HttpURLConnection) new URL(server + "/api/widgets/summary").openConnection();
        c.setConnectTimeout(8000);
        c.setReadTimeout(12000);
        c.setRequestProperty("Authorization", "Bearer " + token);
        c.setRequestProperty("Accept", "application/json");
        try {
            int code = c.getResponseCode();
            if (code == 401) throw new HttpError("Reconnecte-toi dans l'appli");
            if (code >= 400) throw new HttpError("Erreur du serveur (" + code + ")");
            StringBuilder sb = new StringBuilder();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
            }
            return sb.toString();
        } finally {
            c.disconnect();
        }
    }

    private static JSONObject parse(String raw) {
        if (raw == null) return null;
        try {
            return new JSONObject(raw);
        } catch (Exception e) {
            return null;
        }
    }

    /** Aujourd'hui : « à 14:05 » (ou « de 14:05 »), sinon « du 24/11 à 14:05 ». */
    private static String when(long millis, String todayPrefix) {
        Calendar then = Calendar.getInstance();
        then.setTimeInMillis(millis);
        Calendar now = Calendar.getInstance();
        boolean today = then.get(Calendar.YEAR) == now.get(Calendar.YEAR) && then.get(Calendar.DAY_OF_YEAR) == now.get(Calendar.DAY_OF_YEAR);
        String hour = new SimpleDateFormat("HH:mm", Locale.FRANCE).format(new Date(millis));
        return today ? todayPrefix + hour : "du " + new SimpleDateFormat("dd/MM", Locale.FRANCE).format(new Date(millis)) + " à " + hour;
    }
}
