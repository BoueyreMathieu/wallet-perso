package fr.walletperso.app.widget;

import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.Context;
import android.widget.RemoteViews;

import fr.walletperso.app.R;

/** « Ajout rapide » : un bouton + (1 case) qui ouvre la saisie d'une dépense. Pas de données, pas d'appel réseau. */
public class QuickAddWidget extends AppWidgetProvider {
    @Override
    public void onUpdate(Context ctx, AppWidgetManager manager, int[] ids) {
        for (int id : ids) {
            RemoteViews v = new RemoteViews(ctx.getPackageName(), R.layout.widget_quickadd);
            v.setOnClickPendingIntent(R.id.widget_root, BaseWidget.openApp(ctx, "add", id));
            manager.updateAppWidget(id, v);
        }
    }
}
