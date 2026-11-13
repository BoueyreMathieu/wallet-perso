package fr.walletperso.app;

import com.getcapacitor.BridgeActivity;

import fr.walletperso.app.widget.BaseWidget;

/** Activité principale (Capacitor). Remplace celle générée par « npx cap add android » (voir prepare-android.mjs). */
public class MainActivity extends BridgeActivity {
    @Override
    public void onStop() {
        super.onStop();
        // En quittant l'appli : les widgets se mettent à jour (opération ajoutée, connexion faite…).
        BaseWidget.refreshFromApp(this);
    }
}
