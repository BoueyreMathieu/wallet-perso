package fr.walletperso.app.widget;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.DashPathEffect;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.RectF;
import android.graphics.Shader;

/**
 * Petits dessins des widgets (courbe, barres). Couleurs choisies pour rester lisibles en thème clair et sombre :
 * le widget ne se redessine pas forcément quand le téléphone change de thème.
 */
final class Charts {
    static final int ACCENT = 0xFF7552F5;
    static final int POSITIVE = 0xFF16A34A;
    static final int WARNING = 0xFFD97706;
    static final int NEGATIVE = 0xFFE11D48;
    static final int TRACK = 0x4094A3B8;
    // Mêmes couleurs que les couches de l'onglet Prévoir.
    static final int LAYER_FIXE = 0xFF2A78D6;
    static final int LAYER_ESSENTIEL = 0xFFEB6834;
    static final int LAYER_PLAISIR = 0xFFD9468C; // magenta, comme l'appli (--layer-plaisir)

    private Charts() {}

    private static Paint paint() {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setStrokeCap(Paint.Cap.ROUND);
        p.setStrokeJoin(Paint.Join.ROUND);
        return p;
    }

    /** Barre de progression arrondie : dépensé (plein) et prévu (même couleur, transparent). */
    static Bitmap progress(float done, float expected, int color) {
        int w = 360, h = 12;
        Bitmap bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(bmp);
        Paint p = paint();
        float r = h / 2f;
        p.setColor(TRACK);
        c.drawRoundRect(new RectF(0, 0, w, h), r, r, p);
        float exp = clamp(Math.max(done, expected));
        if (exp > done) {
            p.setColor((color & 0x00FFFFFF) | 0x55000000);
            c.drawRoundRect(new RectF(0, 0, Math.max(h, w * exp), h), r, r, p);
        }
        if (done > 0) {
            p.setColor(color);
            c.drawRoundRect(new RectF(0, 0, Math.max(h, w * clamp(done)), h), r, r, p);
        }
        return bmp;
    }

    /** Barre empilée (ex. charges fixes / essentiels / plaisirs). */
    static Bitmap stacked(long[] parts, int[] colors) {
        int w = 480, h = 16;
        Bitmap bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(bmp);
        Paint p = paint();
        long total = 0;
        for (long v : parts) total += Math.max(0, v);
        float r = h / 2f;
        if (total <= 0) {
            p.setColor(TRACK);
            c.drawRoundRect(new RectF(0, 0, w, h), r, r, p);
            return bmp;
        }
        // On dessine les segments dans un calque arrondi : coins arrondis aux deux bouts seulement.
        Path clip = new Path();
        clip.addRoundRect(new RectF(0, 0, w, h), r, r, Path.Direction.CW);
        c.clipPath(clip);
        float x = 0;
        float gap = 3f;
        for (int i = 0; i < parts.length; i++) {
            if (parts[i] <= 0) continue;
            float seg = w * parts[i] / (float) total;
            p.setColor(colors[i]);
            c.drawRect(x, 0, Math.min(w, x + seg), h, p);
            x += seg;
            if (x < w - 1) {
                p.setColor(0x00000000);
                p.setXfermode(new android.graphics.PorterDuffXfermode(android.graphics.PorterDuff.Mode.CLEAR));
                c.drawRect(x - gap / 2, 0, x + gap / 2, h, p);
                p.setXfermode(null);
            }
        }
        return bmp;
    }

    /**
     * Courbe du solde prévu : remplissage dégradé, ligne du zéro en pointillé si la courbe passe dessous,
     * point bas marqué (rouge s'il est négatif).
     */
    static Bitmap balanceLine(long[] values) {
        int w = 480, h = 150;
        Bitmap bmp = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888);
        if (values.length == 0) return bmp;
        Canvas c = new Canvas(bmp);
        long min = Long.MAX_VALUE, max = Long.MIN_VALUE;
        int lowIdx = 0;
        for (int i = 0; i < values.length; i++) {
            if (values[i] < min) {
                min = values[i];
                lowIdx = i;
            }
            max = Math.max(max, values[i]);
        }
        long range = Math.max(100, max - min);
        long lo = min - range * 15 / 100;
        long hi = max + range / 10;
        float pad = 10f;
        int n = Math.max(values.length, 2);
        float[] xs = new float[values.length];
        float[] ys = new float[values.length];
        for (int i = 0; i < values.length; i++) {
            xs[i] = pad + (w - 2 * pad) * i / (float) (n - 1);
            ys[i] = h - pad - (h - 2 * pad) * (values[i] - lo) / (float) (hi - lo);
        }
        Path line = new Path();
        line.moveTo(xs[0], ys[0]);
        for (int i = 1; i < values.length; i++) line.lineTo(xs[i], ys[i]);

        Paint p = paint();
        Path fill = new Path(line);
        fill.lineTo(xs[values.length - 1], h);
        fill.lineTo(xs[0], h);
        fill.close();
        p.setStyle(Paint.Style.FILL);
        p.setShader(new LinearGradient(0, 0, 0, h, (ACCENT & 0x00FFFFFF) | 0x55000000, ACCENT & 0x00FFFFFF, Shader.TileMode.CLAMP));
        c.drawPath(fill, p);
        p.setShader(null);

        if (min < 0 && hi > 0) { // le solde passe sous zéro : ligne du zéro
            float y0 = h - pad - (h - 2 * pad) * (0 - lo) / (float) (hi - lo);
            p.setStyle(Paint.Style.STROKE);
            p.setStrokeWidth(3f);
            p.setColor(NEGATIVE);
            p.setPathEffect(new DashPathEffect(new float[]{10f, 8f}, 0));
            c.drawLine(pad, y0, w - pad, y0, p);
            p.setPathEffect(null);
        }

        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(6f);
        p.setColor(ACCENT);
        c.drawPath(line, p);

        p.setStyle(Paint.Style.FILL);
        p.setColor(values[lowIdx] < 0 ? NEGATIVE : WARNING);
        c.drawCircle(xs[lowIdx], ys[lowIdx], 8f, p);
        p.setColor(ACCENT);
        c.drawCircle(xs[values.length - 1], ys[values.length - 1], 8f, p);
        return bmp;
    }

    private static float clamp(float f) {
        return Math.max(0f, Math.min(1f, f));
    }
}
