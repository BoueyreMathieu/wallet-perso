package fr.walletperso.app.widget;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * « Dernières opérations », tous comptes. Petit : la dernière. Moyen : 3 dernières (+ nombre à catégoriser). Grand : 7.
 * Toucher ouvre les opérations à catégoriser s'il y en a.
 */
public class RecentWidget extends BaseWidget {
    @Override
    protected String title(Context ctx, int widgetId, JSONObject data) {
        return "🧾 Opérations";
    }

    @Override
    protected String deepLink(Context ctx, int widgetId, JSONObject data) {
        return data != null && data.optInt("to_categorize") > 0 ? "categoriser" : "operations";
    }

    @Override
    protected void render(Card c, JSONObject d, int widgetId) {
        JSONArray recent = d.optJSONArray("recent");
        int todo = d.optInt("to_categorize");
        if (recent == null || recent.length() == 0) {
            c.value("—").sub("Aucune opération", true);
            return;
        }
        if (!c.atLeast(Size.MEDIUM)) {
            JSONObject t = recent.optJSONObject(0);
            long a = t.optLong("amount_cents");
            String txt = c.size == Size.TINY ? Fmt.compact(a) : Fmt.signed(a);
            if (a > 0) c.value(txt, Charts.POSITIVE);
            else c.value(txt);
            c.sub(t.optString("label") + " · " + Fmt.past(t.optString("booked_at")));
            return;
        }
        c.hideValue();
        c.sub(todo > 0 ? "🏷️ " + todo + " à catégoriser" : "Tout est catégorisé ✓");
        int max = c.rowsFor(4, 8);
        for (int i = 0; i < Math.min(max, recent.length()); i++) {
            JSONObject t = recent.optJSONObject(i);
            long a = t.optLong("amount_cents");
            c.row(Fmt.past(t.optString("booked_at")) + " · " + t.optString("label"), Fmt.signed(a), Card.amountColor(a));
        }
    }
}
