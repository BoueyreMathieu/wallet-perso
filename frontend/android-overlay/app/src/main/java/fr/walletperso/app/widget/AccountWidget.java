package fr.walletperso.app.widget;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * « Solde d'un compte » : le compte est choisi à la pose du widget (écran AccountWidgetConfigure),
 * modifiable ensuite par appui long › Reconfigurer (Android 12+).
 * Petit : solde. Bandeau : + entrées / sorties du mois. Moyen : + à venir et 2 dernières opérations. Grand : 5.
 */
public class AccountWidget extends BaseWidget {
    static String key(int widgetId) {
        return "account_" + widgetId;
    }

    static void choose(Context ctx, int widgetId, long accountId, String name) {
        ctx.getSharedPreferences(WalletApi.PREFS, Context.MODE_PRIVATE).edit()
                .putLong(key(widgetId), accountId).putString(key(widgetId) + "_name", name).apply();
    }

    private static long chosen(Context ctx, int widgetId) {
        return ctx.getSharedPreferences(WalletApi.PREFS, Context.MODE_PRIVATE).getLong(key(widgetId), -1);
    }

    private static JSONObject account(JSONObject data, long id) {
        JSONArray accounts = data == null ? null : data.optJSONArray("accounts");
        if (accounts == null || id < 0) return null;
        for (int i = 0; i < accounts.length(); i++) {
            JSONObject a = accounts.optJSONObject(i);
            if (a != null && a.optLong("id", -2) == id) return a;
        }
        return null;
    }

    @Override
    protected String title(Context ctx, int widgetId, JSONObject data) {
        JSONObject a = account(data, chosen(ctx, widgetId));
        String name = a != null ? a.optString("name")
                : ctx.getSharedPreferences(WalletApi.PREFS, Context.MODE_PRIVATE).getString(key(widgetId) + "_name", "Compte");
        return "🏦 " + name;
    }

    @Override
    protected String deepLink(Context ctx, int widgetId, JSONObject data) {
        long id = chosen(ctx, widgetId);
        return id >= 0 ? "operations?compte=" + id : "comptes";
    }

    @Override
    protected void render(Card c, JSONObject d, int widgetId) {
        long id = chosen(c.ctx, widgetId);
        if (id < 0) {
            c.value("—").sub("Aucun compte choisi : retire le widget et pose-le à nouveau", true);
            return;
        }
        JSONArray accounts = d.optJSONArray("accounts");
        if (accounts != null && accounts.length() > 0 && accounts.optJSONObject(0) != null && !accounts.optJSONObject(0).has("id")) {
            needsServerUpdate(c);
            return;
        }
        JSONObject a = account(d, id);
        if (a == null) {
            c.value("—").sub("Compte introuvable (archivé ?) : appui long › Reconfigurer", true);
            return;
        }
        if (a.isNull("balance_cents")) {
            c.value("—").sub("Solde inconnu : renseigne-le dans Comptes");
        } else {
            long bal = a.optLong("balance_cents");
            String txt = c.size == Size.TINY ? Fmt.compact(bal) : Fmt.euros(bal);
            if (bal < 0) c.value(txt, Charts.NEGATIVE);
            else c.value(txt);
        }

        long in = a.optLong("month_in_cents"), out = a.optLong("month_out_cents");
        if (in == 0 && out == 0) {
            String inst = a.optString("institution", "");
            c.sub(inst.isEmpty() || "null".equals(inst) ? "Aucun mouvement ce mois-ci" : inst + " · aucun mouvement ce mois-ci");
        } else {
            c.sub("Ce mois : +" + Fmt.round(in) + " · −" + Fmt.round(out));
        }

        int max = c.rowsFor(2, 5);
        if (max == 0) return;
        long pending = a.optLong("pending_cents");
        if (pending != 0) {
            c.row("⏳ À venir", Fmt.signed(pending), Card.amountColor(pending));
            max--;
        }
        JSONArray recent = a.optJSONArray("recent");
        for (int i = 0; recent != null && i < Math.min(max, recent.length()); i++) {
            JSONObject t = recent.optJSONObject(i);
            if (t == null) continue;
            long amount = t.optLong("amount_cents");
            c.row(Fmt.past(t.optString("booked_at")) + " · " + t.optString("label"), Fmt.signed(amount), Card.amountColor(amount));
        }
    }

    @Override
    public void onDeleted(Context ctx, int[] ids) {
        SharedPreferences.Editor e = ctx.getSharedPreferences(WalletApi.PREFS, Context.MODE_PRIVATE).edit();
        for (int id : ids) e.remove(key(id)).remove(key(id) + "_name");
        e.apply();
    }
}
