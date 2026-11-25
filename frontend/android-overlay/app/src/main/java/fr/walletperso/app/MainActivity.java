package fr.walletperso.app;

import android.os.Bundle;

import com.getcapacitor.BridgeActivity;

import fr.walletperso.app.notify.Notifier;
import fr.walletperso.app.widget.BaseWidget;

/** Activité principale (Capacitor). Remplace celle générée par « npx cap add android » (voir prepare-android.mjs). */
public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(SecureCachePlugin.class); // copie hors ligne chiffrée (offline/offline.ts)
        super.onCreate(savedInstanceState);
        Notifier.setup(this); // alertes en notifications (toutes les 30 min environ)
    }

    @Override
    public void onStop() {
        super.onStop();
        // En quittant l'appli : les widgets se mettent à jour (opération ajoutée, connexion faite…).
        BaseWidget.refreshFromApp(this);
    }
}
