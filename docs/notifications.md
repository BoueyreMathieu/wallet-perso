# Alertes et notifications

L'appli calcule les **alertes du moment** (`GET /api/alerts`, `backend/app/services/alerts.py`). Elles s'affichent :

- dans l'appli : carte « À faire » de l'accueil (trésorerie, grosses dépenses, écarts de solde, synchro, revenus,
  échéances en retard, objectifs) et **Paramètres › Notifications › En ce moment** (toutes) ;
- sur le téléphone, en **notifications** : l'appli Android vérifie toutes les 30 minutes environ (WorkManager, réseau
  disponible, Tailscale actif). Aucun service extérieur.

## Types (chacun activable dans Paramètres › Notifications)

| Type | Alertes |
|---|---|
| Budgets | budget presque atteint (seuil d'alerte, ou fin de mois prévue au-dessus) ou dépassé, budget global compris |
| Trésorerie | solde prévu sous zéro dans les 7 jours ; grosse dépense (≥ 100 € et au moins 2× la plus grosse de sa catégorie sur 3 mois) |
| Synchro et banque | connexion expirée ou en erreur, synchro en échec, autorisation qui expire (14 jours, puis 3 jours, puis le jour même), écart entre le solde de la banque et tes opérations |
| Revenus et abonnements | salaire ou revenu régulier arrivé, nouveau prélèvement régulier repéré, hausse de prix, échéance en retard |
| Échéances de contrats | date limite pour résilier (échéance − préavis) : 30 jours, puis 7 jours avant |
| Autres rappels | 10 opérations ou plus à catégoriser (une fois par semaine), objectif d'épargne atteint, livret au plafond, sauvegarde automatique en échec |

Les projets (Prévoir › Projets) qui ont un budget alertent avec les budgets (80 %, puis dépassé).

## Une seule fois par alerte

Chaque alerte a une clé stable (ex. `budget:12:2026-11:depasse`). Le téléphone ne notifie qu'une fois chaque clé et
s'en souvient 60 jours. Au premier passage, les alertes déjà présentes sont marquées vues sans sonner. Au plus
5 notifications par passage.

## Confidentialité

Sur l'écran verrouillé, la notification n'affiche que « Wallet perso · Nouvelle alerte » (montants et vendeurs visibles
une fois le téléphone déverrouillé). Android 13+ demande l'autorisation d'afficher des notifications au premier
lancement : si tu l'as refusée, réactive-la dans les réglages Android de l'appli.

## Écart de solde (comptes synchronisés)

La banque donne un solde à chaque synchro. Sur les 60 derniers jours, la différence entre le premier et le dernier
solde doit égaler la somme des opérations reçues entre les deux (un décalage d'un jour est toléré). Sinon, la page
Comptes l'affiche sur le compte (« une opération manque ou est en double ? ») et une alerte part. « J'ai vérifié »
fait repartir le contrôle du dernier solde. Pas de contrôle pour PayPal, qui ne transmet pas ses approvisionnements.

## Code

- Serveur : `app/balance_check.py` (pur), `app/services/alerts.py`, `app/api/alerts.py` (`/api/alerts`,
  `/api/settings/notifications`, `/api/accounts/{id}/balance-check/ok`).
- Android : `android-overlay/…/notify/AlertsWorker.java` (lecture des alertes, mémoire des clés vues) et
  `notify/Notifier.java` (canal, permission, planification, affichage) ; lancé par `MainActivity`.
  `scripts/prepare-android.mjs` ajoute WorkManager au `build.gradle` et la permission au manifeste.
