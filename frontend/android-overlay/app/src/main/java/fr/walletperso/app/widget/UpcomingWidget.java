package fr.walletperso.app.widget;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Date;

/**
 * « À venir » : prochains prélèvements et revenus attendus (récurrents confirmés ou suggérés).
 * Petit : le prochain. Moyen : à payer d'ici 7 jours + les 3 prochains. Grand : jusqu'à 7.
 */
public class UpcomingWidget extends BaseWidget {
    @Override
    protected String title(Context ctx, int widgetId, JSONObject data) {
        return "📅 À venir";
    }

    @Override
    protected String deepLink(Context ctx, int widgetId, JSONObject data) {
        return "prevoir";
    }

    @Override
    protected void render(Card c, JSONObject d, int widgetId) {
        if (!d.has("upcoming")) {
            needsServerUpdate(c);
            return;
        }
        JSONArray ev = d.optJSONArray("upcoming");
        if (ev == null || ev.length() == 0) {
            c.value(c.size == Size.TINY ? "—" : "Rien de prévu").sub("Confirme tes récurrents dans Prévoir › Récurrents", true);
            return;
        }
        JSONObject next = ev.optJSONObject(0);
        long nextAmount = next.optLong("amount_cents");
        if (!c.atLeast(Size.MEDIUM)) {
            String txt = c.size == Size.TINY ? Fmt.compact(nextAmount) : Fmt.signed(nextAmount);
            if (nextAmount > 0) c.value(txt, Charts.POSITIVE);
            else c.value(txt);
            c.sub(next.optString("label") + " · " + Fmt.upcoming(next.optString("date")));
            return;
        }

        long week = 0;
        int count = 0;
        for (int i = 0; i < ev.length(); i++) {
            JSONObject e = ev.optJSONObject(i);
            Date date = Fmt.parseDate(e.optString("date"));
            if (date == null || Fmt.daysFromToday(date) > 7) break;
            if (e.optLong("amount_cents") < 0) {
                week += e.optLong("amount_cents");
                count++;
            }
        }
        if (count > 0) {
            c.value(Fmt.round(week)).sub(count + (count > 1 ? " prélèvements" : " prélèvement") + " d'ici 7 jours");
        } else {
            c.value(nextAmount > 0 ? Fmt.signed(nextAmount) : Fmt.round(nextAmount), nextAmount > 0 ? Charts.POSITIVE : 0)
                    .sub("Prochain : " + next.optString("label") + " · " + Fmt.upcoming(next.optString("date")));
        }
        int max = c.rowsFor(3, 7);
        for (int i = 0; i < Math.min(max, ev.length()); i++) {
            JSONObject e = ev.optJSONObject(i);
            long a = e.optLong("amount_cents");
            c.row(Fmt.upcoming(e.optString("date")) + " · " + e.optString("label"), Fmt.signed(a), Card.amountColor(a));
        }
    }
}
