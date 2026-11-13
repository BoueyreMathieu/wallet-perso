package fr.walletperso.app.widget;

import java.text.NumberFormat;
import java.text.ParseException;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Date;
import java.util.Locale;

/** Mise en forme des montants et des dates pour les widgets (français, sans java.time : Android 7+). */
final class Fmt {
    private Fmt() {}

    private static NumberFormat money(int decimals) {
        NumberFormat f = NumberFormat.getCurrencyInstance(Locale.FRANCE);
        f.setMinimumFractionDigits(decimals);
        f.setMaximumFractionDigits(decimals);
        return f;
    }

    private static String minus(String s) {
        return s.replace('-', '−'); // vrai signe moins, plus lisible
    }

    /** 1 234,56 € */
    static String euros(long cents) {
        return minus(money(2).format(cents / 100.0));
    }

    /** 1 235 € */
    static String round(long cents) {
        return minus(money(0).format(Math.round(cents / 100.0)));
    }

    /** 1 235 € ; au-delà de 10 000 € : 12,3 k€ (pour les petits widgets). */
    static String compact(long cents) {
        long abs = Math.abs(cents);
        if (abs < 1_000_000) return round(cents);
        NumberFormat f = NumberFormat.getNumberInstance(Locale.FRANCE);
        f.setMaximumFractionDigits(abs < 10_000_000 ? 1 : 0);
        return minus(f.format(cents / 100_000.0)) + " k€";
    }

    /** +1 235 € / −1 235 € */
    static String signed(long cents) {
        return (cents > 0 ? "+" : "") + round(cents);
    }

    static Date parseDate(String iso) {
        if (iso == null || iso.length() < 10) return null;
        try {
            return new SimpleDateFormat("yyyy-MM-dd", Locale.FRANCE).parse(iso.substring(0, 10));
        } catch (ParseException e) {
            return null;
        }
    }

    /** Nombre de jours entre aujourd'hui et la date (0 = aujourd'hui, 1 = demain, -1 = hier). */
    static int daysFromToday(Date d) {
        Calendar a = Calendar.getInstance();
        Calendar b = Calendar.getInstance();
        b.setTime(d);
        for (Calendar c : new Calendar[]{a, b}) {
            c.set(Calendar.HOUR_OF_DAY, 12);
            c.set(Calendar.MINUTE, 0);
            c.set(Calendar.SECOND, 0);
            c.set(Calendar.MILLISECOND, 0);
        }
        return Math.round((b.getTimeInMillis() - a.getTimeInMillis()) / 86_400_000f);
    }

    /** 14/11 */
    static String dayMonth(String iso) {
        Date d = parseDate(iso);
        return d == null ? "" : new SimpleDateFormat("dd/MM", Locale.FRANCE).format(d);
    }

    /** Pour une échéance : aujourd'hui, demain, ven. 14, puis 14/12 au-delà d'une semaine. */
    static String upcoming(String iso) {
        Date d = parseDate(iso);
        if (d == null) return "";
        int days = daysFromToday(d);
        if (days <= 0) return "aujourd'hui";
        if (days == 1) return "demain";
        if (days < 7) return new SimpleDateFormat("EEE d", Locale.FRANCE).format(d);
        return new SimpleDateFormat("dd/MM", Locale.FRANCE).format(d);
    }

    /** Pour une opération passée : aujourd'hui, hier, ou 12/11. */
    static String past(String iso) {
        Date d = parseDate(iso);
        if (d == null) return "";
        int days = daysFromToday(d);
        if (days == 0) return "aujourd'hui";
        if (days == -1) return "hier";
        return new SimpleDateFormat("dd/MM", Locale.FRANCE).format(d);
    }
}
