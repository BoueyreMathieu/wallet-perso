package fr.walletperso.app.widget;

import android.app.Activity;
import android.appwidget.AppWidgetManager;
import android.content.Context;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;

/**
 * Choix du compte du widget « Solde d'un compte » (à la pose du widget, ou appui long › Reconfigurer).
 * La liste vient du résumé des widgets (serveur, sinon dernier résumé en cache).
 */
public class AccountWidgetConfigure extends Activity {
    private int widgetId = AppWidgetManager.INVALID_APPWIDGET_ID;
    private TextView hint;
    private ListView list;
    // Couleurs posées à la main : le thème du système ne s'applique pas toujours à cette fenêtre
    // (texte blanc sur fond blanc : liste « invisible »).
    private int bg, text, muted;

    private static final class Item {
        final long id;
        final String name;
        final String detail;

        Item(long id, String name, String detail) {
            this.id = id;
            this.name = name;
            this.detail = detail;
        }
    }

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        setResult(RESULT_CANCELED); // retour arrière = widget non posé
        Bundle extras = getIntent().getExtras();
        if (extras != null) widgetId = extras.getInt(AppWidgetManager.EXTRA_APPWIDGET_ID, AppWidgetManager.INVALID_APPWIDGET_ID);
        if (widgetId == AppWidgetManager.INVALID_APPWIDGET_ID) {
            finish();
            return;
        }

        boolean night = (getResources().getConfiguration().uiMode & Configuration.UI_MODE_NIGHT_MASK) == Configuration.UI_MODE_NIGHT_YES;
        bg = night ? 0xFF141A2E : 0xFFFFFFFF;
        text = night ? 0xFFF1F5F9 : 0xFF1E293B;
        muted = night ? 0xFF94A3B8 : 0xFF64748B;
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(bg);
        shape.setCornerRadius(dp(22));
        getWindow().setBackgroundDrawable(shape);

        int pad = dp(20);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(pad, pad, pad, dp(8));

        TextView title = new TextView(this);
        title.setText("Quel compte afficher ?");
        title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 19);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setTextColor(text);
        root.addView(title);

        hint = new TextView(this);
        hint.setText("Chargement des comptes…");
        hint.setPadding(0, dp(6), 0, dp(10));
        hint.setTextColor(muted);
        root.addView(hint);

        list = new ListView(this);
        root.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        Button cancel = new Button(this, null, android.R.attr.borderlessButtonStyle);
        cancel.setText("Annuler");
        cancel.setTextColor(0xFF7552F5);
        cancel.setOnClickListener(v -> finish());
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.gravity = android.view.Gravity.END;
        root.addView(cancel, lp);

        setContentView(root);
        getWindow().setLayout(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);

        final Context app = getApplicationContext();
        new Thread(() -> {
            WalletApi.Result r = WalletApi.load(app, false);
            runOnUiThread(() -> show(r));
        }).start();
    }

    private void show(WalletApi.Result r) {
        if (isFinishing()) return;
        List<Item> items = new ArrayList<>();
        JSONArray accounts = r.data == null ? null : r.data.optJSONArray("accounts");
        for (int i = 0; accounts != null && i < accounts.length(); i++) {
            JSONObject a = accounts.optJSONObject(i);
            if (a == null || !a.has("id")) continue;
            String detail = a.isNull("balance_cents") ? "Solde inconnu" : Fmt.euros(a.optLong("balance_cents"));
            String inst = a.optString("institution", "");
            if (!inst.isEmpty() && !"null".equals(inst)) detail += " · " + inst;
            items.add(new Item(a.optLong("id"), a.optString("name"), detail));
        }
        if (items.isEmpty()) {
            hint.setText(r.data == null ? r.status + "\n\nOuvre l'appli Wallet, connecte-toi, puis pose le widget à nouveau."
                    : accounts != null && accounts.length() > 0 ? "Mets à jour le serveur Wallet (docker compose up -d --build), puis réessaie."
                    : "Aucun compte pour l'instant : ajoute-en un dans l'appli.");
            return;
        }
        hint.setText(r.ok ? "Le widget affichera son solde et ses derniers mouvements." : r.status);
        list.setAdapter(new ArrayAdapter<Item>(this, android.R.layout.simple_list_item_2, android.R.id.text1, items) {
            @Override
            public View getView(int position, View convertView, ViewGroup parent) {
                View v = super.getView(position, convertView, parent);
                Item it = getItem(position);
                TextView t1 = v.findViewById(android.R.id.text1);
                TextView t2 = v.findViewById(android.R.id.text2);
                t1.setText(it.name);
                t1.setTextColor(text);
                t2.setText(it.detail);
                t2.setTextColor(muted);
                return v;
            }
        });
        list.setOnItemClickListener((parent, view, position, id) -> pick(items.get(position)));
    }

    private void pick(Item it) {
        AccountWidget.choose(this, widgetId, it.id, it.name);
        // Dessin immédiat depuis le cache, puis mise à jour de tous les widgets.
        AppWidgetManager manager = AppWidgetManager.getInstance(this);
        JSONObject cached = WalletApi.cached(this);
        new AccountWidget().draw(getApplicationContext(), manager, widgetId,
                new WalletApi.Result(cached, "Chargement…", cached != null));
        BaseWidget.refreshAll(getApplicationContext(), false, null);
        setResult(RESULT_OK, new Intent().putExtra(AppWidgetManager.EXTRA_APPWIDGET_ID, widgetId));
        finish();
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
