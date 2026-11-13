package fr.walletperso.app.widget;

import android.app.PendingIntent;
import android.appwidget.AppWidgetManager;
import android.appwidget.AppWidgetProvider;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.util.SizeF;
import android.view.View;
import android.widget.RemoteViews;

import org.json.JSONObject;

import java.util.HashMap;
import java.util.Map;

import fr.walletperso.app.R;

/**
 * Base commune des widgets.
 *
 * - Un seul résumé serveur pour tous les widgets (WalletApi, cache d'une minute) ; hors connexion, le dernier
 *   résumé reçu reste affiché avec un message.
 * - Affichage qui s'adapte à la taille : TINY (1 case), SMALL (bandeau), MEDIUM (2×2), LARGE (3×3 et plus).
 *   Android 12+ choisit lui-même la bonne version quand on redimensionne ; avant, on relit la taille du widget.
 * - ↻ met à jour tous les widgets d'un coup ; toucher le widget ouvre la bonne page de l'appli.
 */
public abstract class BaseWidget extends AppWidgetProvider {
    static final String ACTION_REFRESH = "fr.walletperso.app.widget.REFRESH";
    private static final String TAG = "WalletWidget";

    enum Size { TINY, SMALL, MEDIUM, LARGE }

    /** Tous les widgets qui affichent des données (l'ajout rapide n'en a pas). */
    @SuppressWarnings("unchecked")
    static final Class<? extends BaseWidget>[] PROVIDERS = new Class[]{
            AccountWidget.class, MonthEndWidget.class, SpentWidget.class, BudgetsWidget.class,
            UpcomingWidget.class, BalancesWidget.class, RecentWidget.class,
    };

    /** Titre (emoji + texte court). */
    protected abstract String title(Context ctx, int widgetId, JSONObject data);

    /** Lien ouvert au toucher (voir DEEP_LINKS dans App.tsx), sans le walletperso://. */
    protected abstract String deepLink(Context ctx, int widgetId, JSONObject data);

    /** Remplit la carte ; data n'est jamais null ici. */
    protected abstract void render(Card c, JSONObject data, int widgetId) throws Exception;

    // --- Cycle de vie -------------------------------------------------------------------------------

    @Override
    public void onUpdate(Context ctx, AppWidgetManager manager, int[] ids) {
        final PendingResult pending = goAsync();
        final Context app = ctx.getApplicationContext();
        new Thread(() -> {
            try {
                WalletApi.Result r = WalletApi.load(app, false);
                for (int id : ids) draw(app, manager, id, r);
            } finally {
                pending.finish();
            }
        }).start();
    }

    @Override
    public void onAppWidgetOptionsChanged(Context ctx, AppWidgetManager manager, int id, Bundle options) {
        // Avant Android 12 : la taille a changé, on redessine depuis le cache (pas d'appel réseau).
        if (Build.VERSION.SDK_INT >= 31) return;
        JSONObject cached = WalletApi.cached(ctx);
        draw(ctx, manager, id, new WalletApi.Result(cached, cached != null ? "Données en cache" : "Chargement…", cached != null));
    }

    @Override
    public void onReceive(Context ctx, Intent intent) {
        super.onReceive(ctx, intent);
        if (ACTION_REFRESH.equals(intent.getAction())) {
            final PendingResult pending = goAsync();
            refreshAll(ctx.getApplicationContext(), true, pending);
        }
    }

    /**
     * Appelé par l'appli quand on la quitte (MainActivity.onStop) : les widgets posés reprennent tout de suite
     * la dernière opération saisie, la connexion qui vient d'être faite, etc.
     */
    public static void refreshFromApp(Context ctx) {
        Context app = ctx.getApplicationContext();
        AppWidgetManager manager = AppWidgetManager.getInstance(app);
        for (Class<? extends BaseWidget> cls : PROVIDERS) {
            int[] ids = manager.getAppWidgetIds(new ComponentName(app, cls));
            if (ids != null && ids.length > 0) {
                refreshAll(app, true, null);
                return;
            }
        }
    }

    /** Recharge le résumé (force = ignorer le cache d'une minute) puis redessine tous les widgets. */
    static void refreshAll(Context app, boolean force, PendingResult pending) {
        new Thread(() -> {
            try {
                WalletApi.Result r = WalletApi.load(app, force);
                AppWidgetManager manager = AppWidgetManager.getInstance(app);
                for (Class<? extends BaseWidget> cls : PROVIDERS) {
                    int[] ids = manager.getAppWidgetIds(new ComponentName(app, cls));
                    if (ids == null || ids.length == 0) continue;
                    BaseWidget w = cls.newInstance();
                    for (int id : ids) w.draw(app, manager, id, r);
                }
            } catch (Exception e) {
                Log.w(TAG, "Actualisation des widgets impossible", e);
            } finally {
                if (pending != null) pending.finish();
            }
        }).start();
    }

    // --- Dessin -------------------------------------------------------------------------------------

    void draw(Context ctx, AppWidgetManager manager, int id, WalletApi.Result r) {
        try {
            RemoteViews views;
            if (Build.VERSION.SDK_INT >= 31) {
                Map<SizeF, RemoteViews> bySize = new HashMap<>();
                bySize.put(new SizeF(40f, 40f), build(ctx, id, r, Size.TINY));
                bySize.put(new SizeF(100f, 40f), build(ctx, id, r, Size.SMALL));
                bySize.put(new SizeF(100f, 100f), build(ctx, id, r, Size.MEDIUM));
                bySize.put(new SizeF(150f, 190f), build(ctx, id, r, Size.LARGE));
                views = new RemoteViews(bySize);
            } else {
                views = build(ctx, id, r, sizeOf(manager.getAppWidgetOptions(id)));
            }
            manager.updateAppWidget(id, views);
        } catch (Exception e) {
            Log.w(TAG, "Dessin du widget " + getClass().getSimpleName() + " impossible", e);
        }
    }

    /** Avant Android 12 : taille en mode portrait (largeur mini, hauteur maxi). */
    static Size sizeOf(Bundle o) {
        int w = o == null ? 0 : o.getInt(AppWidgetManager.OPTION_APPWIDGET_MIN_WIDTH);
        int h = o == null ? 0 : o.getInt(AppWidgetManager.OPTION_APPWIDGET_MAX_HEIGHT);
        if (w == 0 || h == 0) return Size.MEDIUM;
        if (w < 100) return Size.TINY;
        if (h < 100) return Size.SMALL;
        if (w >= 150 && h >= 190) return Size.LARGE;
        return Size.MEDIUM;
    }

    private RemoteViews build(Context ctx, int id, WalletApi.Result r, Size size) {
        Card c = new Card(ctx, size);
        c.title(title(ctx, id, r.data));
        c.rv.setOnClickPendingIntent(R.id.widget_root, openApp(ctx, deepLink(ctx, id, r.data), id));
        Intent refresh = new Intent(ctx, getClass()).setAction(ACTION_REFRESH);
        c.rv.setOnClickPendingIntent(R.id.widget_refresh, PendingIntent.getBroadcast(
                ctx, id, refresh, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE));
        c.rv.setTextViewText(R.id.widget_status, r.status);
        // En petit, la ligne d'état ne s'affiche que s'il y a un problème.
        if (size == Size.SMALL && r.ok) c.rv.setViewVisibility(R.id.widget_status, View.GONE);

        if (r.data == null) {
            c.value("—").sub(r.status, true);
            return c.rv;
        }
        try {
            render(c, r.data, id);
        } catch (Exception e) {
            Log.w(TAG, "Données inattendues pour " + getClass().getSimpleName(), e);
            c.sub("Réponse inattendue du serveur", true);
        }
        return c.rv;
    }

    static PendingIntent openApp(Context ctx, String link, int requestCode) {
        Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse("walletperso://" + link)).setPackage(ctx.getPackageName())
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        return PendingIntent.getActivity(ctx, requestCode, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** Message affiché quand le serveur est trop ancien pour ce widget. */
    static void needsServerUpdate(Card c) {
        c.value("—").sub("Mets à jour le serveur Wallet (docker compose up -d --build)", true);
    }
}
