package fr.walletperso.app.widget;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * « Budgets » du mois. Petit : « Tout va bien » / « 2 en alerte ». Bandeau : + le plus tendu.
 * Moyen : les 3 budgets les plus tendus avec barres (plein = dépensé, clair = prévu en fin de mois). Grand : jusqu'à 7.
 */
public class BudgetsWidget extends BaseWidget {
    @Override
    protected String title(Context ctx, int widgetId, JSONObject data) {
        return "🎯 Budgets";
    }

    @Override
    protected String deepLink(Context ctx, int widgetId, JSONObject data) {
        return "budgets";
    }

    private static int color(String level) {
        return "depasse".equals(level) ? Charts.NEGATIVE : "alerte".equals(level) ? Charts.WARNING : Charts.POSITIVE;
    }

    @Override
    protected void render(Card c, JSONObject d, int widgetId) {
        if (!d.has("budgets")) {
            needsServerUpdate(c);
            return;
        }
        JSONArray b = d.optJSONArray("budgets");
        if (b == null || b.length() == 0) {
            c.value(c.size == Size.TINY ? "—" : "Aucun budget").sub("Ajoute-en dans Prévoir › Budgets", true);
            return;
        }
        int over = 0, alert = 0;
        for (int i = 0; i < b.length(); i++) {
            String level = b.optJSONObject(i).optString("level");
            if ("depasse".equals(level)) over++;
            else if ("alerte".equals(level)) alert++;
        }
        if (c.size == Size.TINY) {
            if (over + alert == 0) c.value("✓", Charts.POSITIVE);
            else c.value((over + alert) + " ⚠", over > 0 ? Charts.NEGATIVE : Charts.WARNING);
        } else if (over > 0) {
            c.value(over + (over > 1 ? " dépassés" : " dépassé"), Charts.NEGATIVE);
        } else if (alert > 0) {
            c.value(alert + " en alerte", Charts.WARNING);
        } else {
            c.value("Tout va bien", Charts.POSITIVE);
        }

        JSONObject first = b.optJSONObject(0); // le plus tendu (trié par le serveur)
        if (c.size == Size.SMALL || c.size == Size.TINY) {
            long budget = Math.max(1, first.optLong("budget_cents"));
            c.sub(first.optString("name") + " : " + Math.round(first.optLong("spent_cents") * 100.0 / budget) + " % · "
                    + b.length() + (b.length() > 1 ? " budgets" : " budget"));
            return;
        }
        if (c.size == Size.LARGE) c.sub("Plein : dépensé · clair : prévu en fin de mois");
        int max = c.rowsFor(3, 7);
        for (int i = 0; i < Math.min(max, b.length()); i++) {
            JSONObject x = b.optJSONObject(i);
            long budget = Math.max(1, x.optLong("budget_cents")), spent = x.optLong("spent_cents"), proj = x.optLong("projected_cents");
            String icon = x.optString("icon", "");
            String label = (icon.isEmpty() || "null".equals(icon) ? "" : icon + " ") + x.optString("name");
            int col = color(x.optString("level"));
            c.barRow(label, Fmt.round(spent) + " / " + Fmt.round(budget), "depasse".equals(x.optString("level")) ? Charts.NEGATIVE : 0,
                    Charts.progress(spent / (float) budget, proj / (float) budget, col));
        }
    }
}
