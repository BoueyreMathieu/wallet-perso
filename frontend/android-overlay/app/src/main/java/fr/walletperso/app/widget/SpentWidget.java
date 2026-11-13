package fr.walletperso.app.widget;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * « Ce mois-ci » (nom de classe historique : SpentWidget, pour garder les widgets déjà posés).
 * Petit : dépensé. Bandeau : + ▲▼ par rapport au mois dernier à la même date.
 * Moyen : + barre charges fixes / essentiels / plaisirs. Grand : + 3 premières catégories.
 */
public class SpentWidget extends BaseWidget {
    @Override
    protected String title(Context ctx, int widgetId, JSONObject data) {
        return "💸 Ce mois-ci";
    }

    @Override
    protected String deepLink(Context ctx, int widgetId, JSONObject data) {
        return "home";
    }

    @Override
    protected void render(Card c, JSONObject d, int widgetId) {
        long spent = d.optLong("spent_cents");
        long prev = d.optLong("prev_spent_same_day_cents");
        c.value(c.size == Size.TINY ? Fmt.compact(spent) : Fmt.round(spent));
        if (prev > 0) {
            long pct = Math.round((spent - prev) * 100.0 / prev);
            c.sub((pct > 0 ? "▲ " : pct < 0 ? "▼ " : "= ") + Math.abs(pct) + " % vs mois dernier à la même date");
        } else {
            c.sub("Mois dernier : " + Fmt.round(d.optLong("prev_spent_cents")));
        }
        if (!c.atLeast(Size.MEDIUM)) return;

        JSONObject layers = d.optJSONObject("layers");
        if (layers != null && layers.length() > 0) {
            long fixe = layers.optLong("fixe"), ess = layers.optLong("essentiel"), plaisir = layers.optLong("plaisir");
            c.bar(Charts.stacked(new long[]{fixe, ess, plaisir}, new int[]{Charts.LAYER_FIXE, Charts.LAYER_ESSENTIEL, Charts.LAYER_PLAISIR}),
                    "Répartition : charges fixes, essentiels, plaisirs");
            c.row(Card.dot(Charts.LAYER_FIXE, "Charges fixes"), Fmt.round(fixe));
            c.row(Card.dot(Charts.LAYER_ESSENTIEL, "Essentiels"), Fmt.round(ess));
            c.row(Card.dot(Charts.LAYER_PLAISIR, "Plaisirs"), Fmt.round(plaisir));
        }
        if (c.size != Size.LARGE) return;
        JSONArray cats = d.optJSONArray("top_categories");
        for (int i = 0; cats != null && i < Math.min(3, cats.length()); i++) {
            JSONObject cat = cats.optJSONObject(i);
            if (cat == null) continue;
            String icon = cat.optString("icon", "");
            String label = (icon.isEmpty() || "null".equals(icon) ? "" : icon + " ") + cat.optString("name");
            long v = cat.optLong("spent_cents"), p = cat.optLong("prev_spent_cents");
            String arrow = p > 0 && v > p * 11 / 10 ? " ↗" : "";
            c.row(label, Fmt.round(v) + arrow);
        }
    }
}
