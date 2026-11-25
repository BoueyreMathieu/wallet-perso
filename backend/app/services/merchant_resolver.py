"""Nom de vendeur brut (import, synchro) → vendeur en base.

1. Libellé bancaire générique (« Paiement par carte X1234 MONOP 01/11 ») → vendeur qu'il contient (« Monop »),
   ou aucun vendeur s'il n'y en a pas ;
2. nom déjà connu → ce vendeur ;
3. même vendeur à une troncature / référence près (« … JEA » / « … JEAN 12 ») → ce vendeur ;
4. sinon : nouveau vendeur.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.importers.credit_agricole import smart_title
from app.label_cleaning import clean_payee, is_generic
from app.merchant_similarity import ALIAS_PREFIX, bucket, relation
from app.models import Merchant
from app.services.merchant_merge import find_existing


class MerchantResolver:
    def __init__(self, db: Session):
        self.db = db
        merchants = list(db.scalars(select(Merchant)))
        # Les anciens vendeurs au nom générique (« Paiement Par Carte X1234 … ») ne servent jamais de cible :
        # ils sont justement en train d'être remplacés (services/merchant_repair).
        self.by_name: dict[str, Merchant] = {m.name: m for m in merchants if not is_generic(m.name)}
        self.index: dict[str, list[Merchant]] = {}
        for m in self.by_name.values():
            self.index.setdefault(bucket(m.name), []).append(m)
        # Noms d'origine de vendeurs fusionnés ou renommés : ils désignent toujours le vendeur gardé.
        self.remembered: dict[str, list[tuple[str, Merchant]]] = {}
        for m in self.by_name.values():
            for key in m.aliases or []:
                if key.startswith(ALIAS_PREFIX):
                    old = key[len(ALIAS_PREFIX):]
                    self.remembered.setdefault(bucket(old), []).append((old, m))

    def _remembered(self, name: str) -> Merchant | None:
        for old, m in self.remembered.get(bucket(name), []):
            if relation(name, old) == "sure":
                return m
        return None

    def _known(self, name: str) -> Merchant | None:
        """Vendeur existant : même nom, nom d'un vendeur fusionné / renommé, ou même nom à une troncature près."""
        return self.by_name.get(name) or self._remembered(name) or find_existing(name, self.index)

    @staticmethod
    def clean(name: str | None) -> str | None:
        if not name:
            return None
        name = name.strip()
        if is_generic(name):
            name = smart_title(clean_payee(name))
        return name[:150] or None

    def lookup(self, raw_name: str | None) -> str | None:
        """Nom de vendeur à afficher (vendeur existant si reconnu), sans rien créer en base."""
        name = self.clean(raw_name)
        if name is None:
            return None
        m = self._known(name)
        return m.name if m is not None else name

    def __call__(self, raw_name: str | None) -> Merchant | None:
        name = self.clean(raw_name)
        if name is None:
            return None
        m = self._known(name)
        if m is None:
            m = Merchant(name=name, aliases=[])
            self.db.add(m)
            self.index.setdefault(bucket(name), []).append(m)
            self.by_name[name] = m
        else:
            self.by_name[name] = m  # ce nom désigne désormais ce vendeur sans autre recherche
        return m
