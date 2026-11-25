package fr.walletperso.app;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/** Pont entre l'interface (offline/offline.ts) et la copie hors ligne chiffrée (SecureStore). */
@CapacitorPlugin(name = "SecureCache")
public class SecureCachePlugin extends Plugin {
    @PluginMethod
    public void put(PluginCall call) {
        String name = call.getString("name");
        String value = call.getString("value");
        if (name == null || value == null) {
            call.reject("Nom ou valeur manquant");
            return;
        }
        try {
            SecureStore.put(getContext(), name, value);
            call.resolve();
        } catch (Exception e) {
            call.reject("Copie hors ligne impossible", e);
        }
    }

    @PluginMethod
    public void get(PluginCall call) {
        String name = call.getString("name");
        JSObject out = new JSObject();
        String value = name == null ? null : SecureStore.get(getContext(), name);
        if (value != null) out.put("value", value);
        call.resolve(out);
    }

    @PluginMethod
    public void remove(PluginCall call) {
        String name = call.getString("name");
        if (name != null) SecureStore.remove(getContext(), name);
        call.resolve();
    }

    @PluginMethod
    public void clear(PluginCall call) {
        SecureStore.clear(getContext());
        fr.walletperso.app.widget.BaseWidget.refreshFromApp(getContext()); // les widgets se vident aussi
        call.resolve();
    }
}
