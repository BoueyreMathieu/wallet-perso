package fr.walletperso.app.widget;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * « Patrimoine » (nom de classe historique : BalancesWidget, pour garder les widgets déjà posés).
 * Petit : total. Bandeau : + variation du mois. Moyen : + 3 plus gros comptes. Grand : jusqu'à 7 comptes.
 */
public class BalancesWidget extends BaseWidget {
    @Override
    protected String title(Context ctx, int widgetId, JSONObject data) {
        return "💎 Patrimoine";
    }

    @Override
    protected String deepLink(Context ctx, int widgetId, JSONObject data) {
        return "comptes";
    }

    @Override
    protected void render(Card c, JSONObject d, int widgetId) {
        long net = d.optLong("net_worth_cents");
        c.value(c.size == Size.TINY ? Fmt.compact(net) : Fmt.round(net));
        if (d.has("net_worth_change_cents")) {
            long change = d.optLong("net_worth_change_cents");
            c.sub((change > 0 ? "▲ " : change < 0 ? "▼ " : "= ") + Fmt.signed(change) + " ce mois-ci");
        }
        int max = c.rowsFor(3, 7);
        JSONArray accounts = d.optJSONArray("accounts");
        int shown = 0;
        for (int i = 0; accounts != null && i < accounts.length() && shown < max; i++) {
            JSONObject a = accounts.optJSONObject(i);
            if (a == null || !a.optBoolean("in_net_worth", true) || a.isNull("balance_cents")) continue;
            long bal = a.optLong("balance_cents");
            c.row(a.optString("name"), Fmt.round(bal), bal < 0 ? Charts.NEGATIVE : 0);
            shown++;
        }
    }
}
