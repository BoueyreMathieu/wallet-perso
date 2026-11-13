package fr.walletperso.app.widget;

import android.content.Context;
import android.graphics.Bitmap;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.ForegroundColorSpan;
import android.util.TypedValue;
import android.view.View;
import android.widget.RemoteViews;

import fr.walletperso.app.R;

/**
 * Une carte de widget (layout commun wallet_widget.xml) : titre, grand montant, sous-titre, barre, courbe, lignes.
 * Les widgets remplissent ce dont ils ont besoin selon la taille ; le reste reste masqué.
 */
final class Card {
    final Context ctx;
    final RemoteViews rv;
    final BaseWidget.Size size;
    private int rows = 0;

    Card(Context ctx, BaseWidget.Size size) {
        this.ctx = ctx;
        this.size = size;
        this.rv = new RemoteViews(ctx.getPackageName(), R.layout.wallet_widget);
        float valueSp = size == BaseWidget.Size.TINY ? 17 : size == BaseWidget.Size.SMALL ? 22 : 26;
        rv.setTextViewTextSize(R.id.widget_value, TypedValue.COMPLEX_UNIT_SP, valueSp);
        if (size == BaseWidget.Size.TINY) {
            rv.setViewVisibility(R.id.widget_refresh, View.GONE);
            rv.setViewVisibility(R.id.widget_status, View.GONE);
            rv.setTextViewTextSize(R.id.widget_title, TypedValue.COMPLEX_UNIT_SP, 11);
        }
    }

    boolean atLeast(BaseWidget.Size s) {
        return size.ordinal() >= s.ordinal();
    }

    /** Nombre de lignes à afficher selon la taille : moyen, grand (aucune en petit). */
    int rowsFor(int medium, int large) {
        return size == BaseWidget.Size.LARGE ? large : size == BaseWidget.Size.MEDIUM ? medium : 0;
    }

    Card title(CharSequence t) {
        rv.setTextViewText(R.id.widget_title, t);
        return this;
    }

    Card value(CharSequence t) {
        rv.setViewVisibility(R.id.widget_value, View.VISIBLE);
        rv.setTextViewText(R.id.widget_value, t);
        return this;
    }

    Card value(CharSequence t, int color) {
        value(t);
        rv.setTextColor(R.id.widget_value, color);
        return this;
    }

    Card hideValue() {
        rv.setViewVisibility(R.id.widget_value, View.GONE);
        return this;
    }

    /** Sous-titre (masqué en très petite taille, sauf force). */
    Card sub(CharSequence t) {
        return sub(t, false);
    }

    Card sub(CharSequence t, boolean force) {
        if (t == null || t.length() == 0 || (size == BaseWidget.Size.TINY && !force)) return this;
        rv.setViewVisibility(R.id.widget_sub, View.VISIBLE);
        rv.setTextViewText(R.id.widget_sub, t);
        return this;
    }

    Card bar(Bitmap b, String description) {
        rv.setViewVisibility(R.id.widget_bar, View.VISIBLE);
        rv.setImageViewBitmap(R.id.widget_bar, b);
        rv.setContentDescription(R.id.widget_bar, description);
        return this;
    }

    Card chart(Bitmap b, String description) {
        rv.setViewVisibility(R.id.widget_chart, View.VISIBLE);
        rv.setImageViewBitmap(R.id.widget_chart, b);
        rv.setContentDescription(R.id.widget_chart, description);
        return this;
    }

    Card row(CharSequence label, CharSequence value) {
        return row(label, value, 0);
    }

    /** Ligne « libellé … montant » ; color = 0 pour la couleur de texte normale. */
    Card row(CharSequence label, CharSequence value, int color) {
        RemoteViews r = new RemoteViews(ctx.getPackageName(), R.layout.wallet_widget_row);
        r.setTextViewText(R.id.row_label, label);
        r.setTextViewText(R.id.row_value, value);
        if (color != 0) r.setTextColor(R.id.row_value, color);
        addRow(r);
        return this;
    }

    /** Ligne avec barre de progression dessous (budgets). */
    Card barRow(CharSequence label, CharSequence value, int color, Bitmap bar) {
        RemoteViews r = new RemoteViews(ctx.getPackageName(), R.layout.wallet_widget_row_bar);
        r.setTextViewText(R.id.row_label, label);
        r.setTextViewText(R.id.row_value, value);
        if (color != 0) r.setTextColor(R.id.row_value, color);
        r.setImageViewBitmap(R.id.row_bar, bar);
        addRow(r);
        return this;
    }

    private void addRow(RemoteViews r) {
        if (rows == 0) rv.setViewVisibility(R.id.widget_rows, View.VISIBLE);
        rv.addView(R.id.widget_rows, r);
        rows++;
    }

    /** « ● texte » avec la pastille colorée. */
    static CharSequence dot(int color, String text) {
        SpannableString s = new SpannableString("● " + text);
        s.setSpan(new ForegroundColorSpan(color), 0, 1, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        return s;
    }

    /** Couleur d'un montant : vert s'il est positif, rouge s'il est négatif et que c'est un solde. */
    static int amountColor(long cents) {
        return cents > 0 ? Charts.POSITIVE : 0;
    }
}
