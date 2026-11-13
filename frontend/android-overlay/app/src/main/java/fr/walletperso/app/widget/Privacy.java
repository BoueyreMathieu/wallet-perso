package fr.walletperso.app.widget;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.res.Configuration;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Shader;
import android.os.SystemClock;
import android.util.DisplayMetrics;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.RemoteViews;

/**
 * Montants masqués : par défaut, chaque widget est flouté. Un appui l'affiche pendant quelques minutes (puis il se
 * re-floute tout seul) ; le bouton 🙈 le re-floute tout de suite. État gardé par widget (SharedPreferences).
 *
 * L'effet « verre dépoli » : la carte normale est dessinée hors écran, floutée (réduite très fort puis ré-agrandie
 * avec lissage), puis recouverte d'un voile laiteux, d'un reflet en haut et d'un grain fin, comme du verre givré.
 */
final class Privacy {
    static final String ACTION_REVEAL = "fr.walletperso.app.widget.REVEAL";
    static final String ACTION_HIDE = "fr.walletperso.app.widget.HIDE";
    static final long REVEAL_MS = 5 * 60 * 1000L;
    private static final String PREFS = "wallet_widget_privacy";

    private Privacy() {
    }

    private static SharedPreferences prefs(Context ctx) {
        return ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    static boolean revealed(Context ctx, int widgetId) {
        return prefs(ctx).getLong("until_" + widgetId, 0L) > System.currentTimeMillis();
    }

    /** Affiche les montants de ce widget pour quelques minutes, et programme le retour au flou. */
    static void reveal(Context ctx, Class<?> provider, int widgetId) {
        prefs(ctx).edit().putLong("until_" + widgetId, System.currentTimeMillis() + REVEAL_MS).apply();
        AlarmManager am = (AlarmManager) ctx.getSystemService(Context.ALARM_SERVICE);
        if (am != null) {
            am.set(AlarmManager.ELAPSED_REALTIME, SystemClock.elapsedRealtime() + REVEAL_MS, hideIntent(ctx, provider, widgetId));
        }
    }

    static void hide(Context ctx, int widgetId) {
        prefs(ctx).edit().remove("until_" + widgetId).apply();
    }

    static PendingIntent revealIntent(Context ctx, Class<?> provider, int widgetId) {
        Intent i = new Intent(ctx, provider).setAction(ACTION_REVEAL).putExtra("widget_id", widgetId);
        return PendingIntent.getBroadcast(ctx, widgetId * 10 + 1, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    static PendingIntent hideIntent(Context ctx, Class<?> provider, int widgetId) {
        Intent i = new Intent(ctx, provider).setAction(ACTION_HIDE).putExtra("widget_id", widgetId);
        return PendingIntent.getBroadcast(ctx, widgetId * 10 + 2, i, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
    }

    /** Taille de référence (dp) de chaque format, pour dessiner la carte avant de la flouter. */
    static int[] nominalDp(BaseWidget.Size size) {
        switch (size) {
            case TINY: return new int[]{70, 70};
            case SMALL: return new int[]{250, 70};
            case LARGE: return new int[]{250, 260};
            default: return new int[]{160, 160};
        }
    }

    /** Verre givré : voile laiteux (clair ou sombre selon le thème), reflet dégradé en haut, grain fin régulier. */
    static void frost(Context ctx, Bitmap b) {
        boolean night = (ctx.getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        int w = b.getWidth(), h = b.getHeight();
        Canvas c = new Canvas(b);
        c.drawColor(night ? 0x8C141A2E : 0x99FFFFFF); // voile
        Paint shine = new Paint(Paint.ANTI_ALIAS_FLAG);
        shine.setShader(new LinearGradient(0, 0, 0, h * 0.6f, night ? 0x33FFFFFF : 0x66FFFFFF, 0x00FFFFFF, Shader.TileMode.CLAMP));
        c.drawRect(0, 0, w, h * 0.6f, shine); // reflet
        int[] px = new int[w * h];
        b.getPixels(px, 0, w, 0, 0, w, h);
        long seed = 0x2545F4914F6CDD1DL;
        for (int i = 0; i < px.length; i++) { // grain : ±6 de luminosité, pseudo-aléatoire stable
            seed ^= seed << 13;
            seed ^= seed >>> 7;
            seed ^= seed << 17;
            int d = (int) (seed & 15) - 7;
            int p = px[i];
            int r = Math.min(255, Math.max(0, ((p >> 16) & 0xFF) + d));
            int g = Math.min(255, Math.max(0, ((p >> 8) & 0xFF) + d));
            int bl = Math.min(255, Math.max(0, (p & 0xFF) + d));
            px[i] = (p & 0xFF000000) | (r << 16) | (g << 8) | bl;
        }
        b.setPixels(px, 0, w, 0, 0, w, h);
    }

    /** La carte dessinée puis floutée ; null si le dessin hors écran échoue (on affiche alors une carte vide). */
    static Bitmap blurred(Context ctx, RemoteViews card, BaseWidget.Size size) {
        try {
            DisplayMetrics dm = ctx.getResources().getDisplayMetrics();
            int[] dp = nominalDp(size);
            int w = Math.max(1, Math.round(dp[0] * dm.density));
            int h = Math.max(1, Math.round(dp[1] * dm.density));
            View v = card.apply(ctx, new FrameLayout(ctx));
            v.measure(View.MeasureSpec.makeMeasureSpec(w, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(h, View.MeasureSpec.EXACTLY));
            v.layout(0, 0, w, h);
            Bitmap full = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
            v.draw(new Canvas(full));
            // Réduire très fort puis ré-agrandir avec lissage = flou ; deux fois pour un rendu plus doux.
            Bitmap tiny = Bitmap.createScaledBitmap(full, Math.max(2, w / 14), Math.max(2, h / 14), true);
            Bitmap mid = Bitmap.createScaledBitmap(tiny, Math.max(4, w / 5), Math.max(4, h / 5), true);
            Bitmap tiny2 = Bitmap.createScaledBitmap(mid, Math.max(2, w / 10), Math.max(2, h / 10), true);
            Bitmap blur = Bitmap.createScaledBitmap(tiny2, Math.max(4, w / 3), Math.max(4, h / 3), true);
            Bitmap out = blur.copy(Bitmap.Config.ARGB_8888, true);
            full.recycle();
            tiny.recycle();
            mid.recycle();
            tiny2.recycle();
            blur.recycle();
            frost(ctx, out);
            return out;
        } catch (RuntimeException e) {
            return null;
        }
    }
}
