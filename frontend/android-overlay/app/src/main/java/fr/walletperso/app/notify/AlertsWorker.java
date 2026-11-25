package fr.walletperso.app.notify;

import android.content.Context;
import android.content.SharedPreferences;

import androidx.annotation.NonNull;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Iterator;

/**
 * Toutes les 30 minutes environ (WorkManager, réseau disponible) : lit /api/alerts sur ton serveur et affiche une
 * notification pour chaque alerte jamais vue. Une alerte (clé stable) ne sonne qu'une fois ; les clés vues sont
 * gardées 60 jours. Au tout premier passage, les alertes déjà présentes sont marquées vues sans sonner (pas de
 * rafale à l'installation). Serveur injoignable (Tailscale coupé…) : rien, on réessaie au prochain passage.
 */
public class AlertsWorker extends Worker {
    private static final String CAPACITOR_PREFS = "CapacitorStorage";
    static final String PREFS = "WalletNotify";
    private static final long KEEP_MS = 60L * 24 * 3600 * 1000;
    private static final int MAX_PER_RUN = 5;

    public AlertsWorker(@NonNull Context context, @NonNull WorkerParameters params) {
        super(context, params);
    }

    @NonNull
    @Override
    public Result doWork() {
        Context ctx = getApplicationContext();
        JSONArray alerts;
        try {
            alerts = fetch(ctx);
        } catch (Exception e) {
            return Result.success(); // pas de connexion : prochain passage
        }
        if (alerts == null) return Result.success();
        SharedPreferences prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        JSONObject seen;
        try {
            seen = new JSONObject(prefs.getString("seen", "{}"));
        } catch (Exception e) {
            seen = new JSONObject();
        }
        boolean first = !prefs.getBoolean("baseline_done", false);
        long now = System.currentTimeMillis();
        int shown = 0;
        try {
            for (int i = 0; i < alerts.length(); i++) {
                JSONObject a = alerts.getJSONObject(i);
                String key = a.optString("key", "");
                if (key.isEmpty() || seen.has(key)) continue;
                seen.put(key, now);
                if (first || shown >= MAX_PER_RUN) continue;
                Notifier.show(ctx, key, a.optString("title"), a.optString("body"), a.optString("deep", "home"), a.optString("level", "info"));
                shown++;
            }
            // Oubli des clés de plus de 60 jours.
            for (Iterator<String> it = seen.keys(); it.hasNext(); ) {
                String k = it.next();
                if (now - seen.optLong(k, now) > KEEP_MS) it.remove();
            }
        } catch (Exception ignored) {
            // alerte illisible : on garde ce qui a été fait
        }
        prefs.edit().putString("seen", seen.toString()).putBoolean("baseline_done", true).apply();
        return Result.success();
    }

    private static JSONArray fetch(Context ctx) throws Exception {
        SharedPreferences p = ctx.getSharedPreferences(CAPACITOR_PREFS, Context.MODE_PRIVATE);
        String server = p.getString("server_url", null);
        String token = p.getString("device_token", null);
        if (server == null || server.isEmpty() || token == null || token.isEmpty()) return null; // pas connecté
        HttpURLConnection c = (HttpURLConnection) new URL(server + "/api/alerts").openConnection();
        c.setConnectTimeout(10000);
        c.setReadTimeout(30000);
        c.setRequestProperty("Authorization", "Bearer " + token);
        c.setRequestProperty("Accept", "application/json");
        try {
            if (c.getResponseCode() != 200) return null;
            StringBuilder sb = new StringBuilder();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = r.readLine()) != null) sb.append(line);
            }
            return new JSONObject(sb.toString()).optJSONArray("alerts");
        } finally {
            c.disconnect();
        }
    }
}
