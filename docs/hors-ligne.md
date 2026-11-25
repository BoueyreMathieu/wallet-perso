# Mode hors ligne (appli Android)

Quand le serveur est injoignable (Tailscale coupé, serveur éteint, pas de réseau), l'appli Android affiche **tes
dernières données reçues**, en lecture seule, avec un bandeau 📴 « Hors ligne » et la date de ces données. Dès que le
serveur répond (vérifié toutes les 15 s), l'appli se recharge et repasse en direct.

## Ce qui est gardé

- Chaque écran tel qu'il a été vu la dernière fois avec la connexion (même adresse, mêmes réglages : mois, filtres…).
  Un écran jamais ouvert avec la connexion n'est pas disponible hors ligne. Un même écran avec d'autres réglages
  affiche la version gardée la plus proche.
- Les opérations vues sont réunies et filtrées sur le téléphone (compte, catégorie, vendeur, recherche, dates).
- Au plus 250 écrans : les plus anciens sont oubliés.
- Les widgets gardent aussi leur dernier résumé et affichent « Hors ligne · données du 24/11 à 14:05 ».

## Sécurité

- Tout est chiffré (AES-GCM) avec une clé du **Keystore Android** : elle ne quitte jamais le téléphone et n'est pas
  sauvegardée. Les fichiers (dossier privé de l'appli, `files/offline`) ont des noms qui ne révèlent rien.
- Rien de tout ça ne part dans les sauvegardes Google ni lors d'un transfert de téléphone
  (`wallet_data_extraction.xml`).
- **Déconnexion** = copie hors ligne effacée (appli et widgets).
- Hors ligne, rien n'est modifiable : « Hors ligne : rien n'est enregistré ».

## Code

- `frontend/src/offline/offline.ts` : garde les réponses (`remember`), répond hors ligne (`offlineAnswer`), efface
  (`clearOfflineData`). Branché dans `frontend/src/api.ts`.
- `android-overlay/…/SecureStore.java` (chiffrement) et `SecureCachePlugin.java` (plugin Capacitor « SecureCache »,
  enregistré dans `MainActivity`). `widget/WalletApi.java` utilise `SecureStore` pour le résumé des widgets.
- Ordre de secours quand le serveur ne répond pas : copie hors ligne, sinon jeu de test (`docs/demo.md`), sinon erreur.
- Dans le navigateur, pas de copie hors ligne : le jeu de test prend le relais comme avant.
