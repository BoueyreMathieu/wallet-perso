package fr.walletperso.app;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.util.Arrays;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Copie hors ligne chiffrée (appli + widgets) : un fichier par entrée dans le dossier privé de l'appli
 * (files/offline), chiffré en AES-GCM avec une clé du Keystore Android. La clé ne quitte jamais le téléphone et
 * n'est pas sauvegardée : un fichier copié ailleurs est illisible. Tout est effacé à la déconnexion (clear).
 */
public final class SecureStore {
    private static final String ALIAS = "wallet_offline_v1";
    private static final String DIR = "offline";

    private SecureStore() {}

    private static SecretKey key() throws Exception {
        KeyStore ks = KeyStore.getInstance("AndroidKeyStore");
        ks.load(null);
        KeyStore.Entry entry = ks.getEntry(ALIAS, null);
        if (entry instanceof KeyStore.SecretKeyEntry) return ((KeyStore.SecretKeyEntry) entry).getSecretKey();
        KeyGenerator gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
        gen.init(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build());
        return gen.generateKey();
    }

    /** Nom de fichier sûr : les noms simples (empreintes, « __index__ ») tels quels, les autres hachés. */
    private static File file(Context ctx, String name) throws Exception {
        File dir = new File(ctx.getFilesDir(), DIR);
        if (!dir.exists() && !dir.mkdirs()) throw new IllegalStateException("Dossier hors ligne impossible à créer");
        String safe = name.matches("[A-Za-z0-9_]{1,80}") ? name : hex(MessageDigest.getInstance("SHA-256").digest(name.getBytes(StandardCharsets.UTF_8)));
        return new File(dir, safe);
    }

    private static String hex(byte[] b) {
        StringBuilder sb = new StringBuilder();
        for (byte x : b) sb.append(String.format("%02x", x));
        return sb.toString();
    }

    public static synchronized void put(Context ctx, String name, String value) throws Exception {
        Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.ENCRYPT_MODE, key());
        byte[] iv = c.getIV();
        byte[] data = c.doFinal(value.getBytes(StandardCharsets.UTF_8));
        File f = file(ctx, name);
        File tmp = new File(f.getPath() + ".tmp");
        try (FileOutputStream out = new FileOutputStream(tmp)) {
            out.write(iv.length);
            out.write(iv);
            out.write(data);
        }
        if (!tmp.renameTo(f)) {
            //noinspection ResultOfMethodCallIgnored
            f.delete();
            if (!tmp.renameTo(f)) throw new IllegalStateException("Écriture hors ligne impossible");
        }
    }

    /** Contenu déchiffré, ou null (absent, illisible, clé changée). Jamais d'exception. */
    public static synchronized String get(Context ctx, String name) {
        try {
            File f = file(ctx, name);
            if (!f.exists()) return null;
            byte[] all = readAll(f);
            int n = all[0];
            byte[] iv = Arrays.copyOfRange(all, 1, 1 + n);
            byte[] data = Arrays.copyOfRange(all, 1 + n, all.length);
            Cipher c = Cipher.getInstance("AES/GCM/NoPadding");
            c.init(Cipher.DECRYPT_MODE, key(), new GCMParameterSpec(128, iv));
            return new String(c.doFinal(data), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return null;
        }
    }

    public static synchronized void remove(Context ctx, String name) {
        try {
            //noinspection ResultOfMethodCallIgnored
            file(ctx, name).delete();
        } catch (Exception ignored) {
            // rien à effacer
        }
    }

    /** Efface toute la copie hors ligne (déconnexion). */
    public static synchronized void clear(Context ctx) {
        File[] files = new File(ctx.getFilesDir(), DIR).listFiles();
        if (files == null) return;
        for (File f : files) {
            //noinspection ResultOfMethodCallIgnored
            f.delete();
        }
    }

    private static byte[] readAll(File f) throws Exception {
        try (InputStream in = new FileInputStream(f); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[16384];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
            return out.toByteArray();
        }
    }
}
