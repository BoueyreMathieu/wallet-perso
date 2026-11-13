package fr.walletperso.app.widget;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * « Fin du mois » : solde prévu des comptes courants (même calcul que Prévoir › Trésorerie, sans scénario).
 * Petit : solde prévu. Bandeau : + date et point bas. Moyen : + aujourd'hui / point bas / écart. Grand : + courbe.
 */
public class MonthEndWidget extends BaseWidget {
    @Override
    protected String title(Context ctx, int widgetId, JSONObject data) {
        return "🔮 Fin du mois";
    }

    @Override
    protected String deepLink(Context ctx, int widgetId, JSONObject data) {
        return "prevoir";
    }

    @Override
    protected void render(Card c, JSONObject d, int widgetId) throws Exception {
        if (!d.has("end_of_month")) {
            needsServerUpdate(c);
            return;
        }
        JSONObject e = d.optJSONObject("end_of_month");
        if (e == null) {
            c.value("—").sub("Prévision indisponible pour le moment", true);
            return;
        }
        long end = e.getLong("balance_cents"), start = e.getLong("start_cents"), low = e.getLong("low_cents");
        String horizon = Fmt.dayMonth(e.getString("horizon"));
        String lowDate = Fmt.dayMonth(e.getString("low_date"));
        String txt = c.size == Size.TINY ? Fmt.compact(end) : Fmt.round(end);
        if (end < 0) c.value(txt, Charts.NEGATIVE);
        else c.value(txt);

        boolean lowMatters = low < end - 1000 && low < start; // point bas nettement sous l'arrivée
        if (c.size == Size.SMALL && lowMatters) c.sub("au " + horizon + " · point bas " + Fmt.round(low) + " le " + lowDate);
        else c.sub("prévu au " + horizon);

        if (!c.atLeast(Size.MEDIUM)) return;
        if (c.size == Size.LARGE) {
            JSONArray pts = e.optJSONArray("points");
            if (pts != null && pts.length() > 1) {
                long[] v = new long[pts.length()];
                for (int i = 0; i < v.length; i++) v[i] = pts.getLong(i);
                c.chart(Charts.balanceLine(v), "Solde prévu jour par jour jusqu'au " + horizon);
            }
        }
        c.row("Aujourd'hui", Fmt.round(start));
        c.row("Point bas · " + lowDate, Fmt.round(low), low < 0 ? Charts.NEGATIVE : 0);
        c.row("Écart d'ici là", Fmt.signed(end - start), end - start >= 0 ? Charts.POSITIVE : 0);
    }
}
