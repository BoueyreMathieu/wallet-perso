# Projets, contrats, comparaison annuelle, patrimoine

## Projets par étiquette (Prévoir › Projets)

Un projet suit une **étiquette** (« Voyage », « Travaux »…) : toutes les opérations qui la portent (posée à la main, via
le vendeur ou un service), toutes catégories confondues. Budget **total** facultatif, dates de début et de fin
facultatives (hors dates : pas compté). Les remboursements portant l'étiquette sont déduits. Détail par catégorie et
par mois, lien vers les opérations (`/operations?etiquette=<id>`). « Terminé » archive le projet ; « Ne plus suivre »
le supprime, l'étiquette reste. Table `project` (migration 0014), `services/projects.py`, `api/projects.py`.

## Contrats (Prévoir › Contrats, ou « 📄 Infos du contrat » sur un récurrent)

Échéance (ou date de renouvellement), préavis en jours, reconduction tacite (chaque mois, an, 2 ans, ou aucune), note.
Date limite pour résilier = échéance − préavis. Avec reconduction tacite, une échéance passée avance toute seule d'une
période. Rattaché à un récurrent, le contrat en reprend le nom et le montant. Table `contract`.

## Comparaison d'une année sur l'autre (Bilan › Comparer à l'an dernier)

Depuis le 1er janvier (contre la même période l'an dernier) ou 12 derniers mois (contre les 12 d'avant). Dépenses et
revenus, graphique mois par mois, catégories (avec sous-catégories au toucher). Hors virements entre tes comptes.
`GET /api/compare?mode=ytd|rolling`.

## Patrimoine (page 💎 Patrimoine)

- Patrimoine net, ce que tu possèdes, ce que tu dois, intérêts estimés de l'épargne, évolution sur 24 mois.
- **Bien** (type « Bien ») : prix et date d'achat, perte de valeur par an (voiture ≈ 15 %). Valeur calculée chaque jour.
- **Crédit** (type « Crédit ») : capital, taux, durée, date de la 1re échéance, assurance. Mensualité, capital restant dû
  (calculé chaque jour, en négatif), intérêts restant à payer, tableau d'amortissement.
- **Épargne** : taux et plafond → intérêts estimés sur un an, place restante, alerte au plafond.
- Les valeurs calculées des biens et crédits sont enregistrées comme solde du jour : elles comptent partout (accueil,
  widgets, Comptes). Réglages stockés dans `account.params` (JSON). Calculs purs : `app/wealth.py`.
