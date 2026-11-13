"""Modèle de données de Wallet perso.

Conventions :
- Les montants sont en centimes d'euro (entiers signés) : -1250 = -12,50 €.
- Une dépense est négative, un revenu est positif.
- Les « types » sont stockés en texte ; les valeurs autorisées sont listées ci-dessous.
"""

import datetime as dt
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Column,
    String,
    Table,
    Text,
    UniqueConstraint,
    false,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ACCOUNT_TYPES = ("courant", "epargne", "investissement", "paypal", "especes", "credit", "bien", "titres")  # titres : titres-restaurant (Edenred, Swile…)
PROVIDERS = ("manuel", "csv", "enable_banking", "paypal", "pytr")
CATEGORY_KINDS = ("depense", "revenu", "transfert")
FREQUENCIES = ("hebdomadaire", "mensuelle", "trimestrielle", "annuelle")


# Étiquettes : liens manuels (opération), et liens hérités (vendeur, service).
transaction_tag = Table(
    "transaction_tag",
    Base.metadata,
    Column("transaction_id", ForeignKey("transaction.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)
merchant_tag = Table(
    "merchant_tag",
    Base.metadata,
    Column("merchant_id", ForeignKey("merchant.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)
rule_tag = Table(
    "rule_tag",
    Base.metadata,
    Column("rule_id", ForeignKey("rule.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Connection(Base):
    """Lien vers un fournisseur de données (agrégateur, API, import de fichiers)."""

    __tablename__ = "connection"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(30))
    label: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="actif")
    consent_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(300))  # dernière synchro en échec (effacée au succès suivant)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Jetons / identifiants chiffrés avec Fernet (voir app.security).
    secrets_encrypted: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    accounts: Mapped[list["Account"]] = relationship(back_populates="connection")


class Account(Base):
    __tablename__ = "account"
    __table_args__ = (UniqueConstraint("connection_id", "external_id", name="uq_account_external"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_id: Mapped[int | None] = mapped_column(ForeignKey("connection.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(30))
    institution: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), default="EUR")
    external_id: Mapped[str | None] = mapped_column(String(200))
    include_in_net_worth: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    connection: Mapped[Connection | None] = relationship(back_populates="accounts")
    balances: Mapped[list["BalanceSnapshot"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", order_by="BalanceSnapshot.date"
    )


class BalanceSnapshot(Base):
    """Solde d'un compte à une date donnée (historique du patrimoine)."""

    __tablename__ = "balance_snapshot"
    __table_args__ = (UniqueConstraint("account_id", "date", name="uq_balance_account_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    date: Mapped[dt.date] = mapped_column(Date)
    balance_cents: Mapped[int] = mapped_column(BigInteger)
    # Moment où ce solde a été enregistré : les saisies manuelles faites après, à la même date, s'y ajoutent.
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    account: Mapped[Account] = relationship(back_populates="balances")


class ImportBatch(Base):
    """Trace d'un import (fichier ou synchro) pour pouvoir l'auditer ou l'annuler."""

    __tablename__ = "import_batch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(30))
    filename: Mapped[str | None] = mapped_column(String(255))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list | None] = mapped_column(JSON)


class Category(Base):
    __tablename__ = "category"
    __table_args__ = (UniqueConstraint("parent_id", "name", name="uq_category_parent_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20), default="depense")
    color: Mapped[str | None] = mapped_column(String(7))
    icon: Mapped[str | None] = mapped_column(String(50))
    # Dépenses : fixe (charges), essentiel (courant nécessaire), plaisir (non essentiel). Vide = automatique.
    nature: Mapped[str | None] = mapped_column(String(12))


class Merchant(Base):
    """Marchand normalisé (« CARREFOUR MARKET 1234 » → « Carrefour »)."""

    __tablename__ = "merchant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    aliases: Mapped[list | None] = mapped_column(JSON)
    default_category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id", ondelete="SET NULL"))

    tags: Mapped[list["Tag"]] = relationship(secondary=merchant_tag)


class RecurringSeries(Base):
    """Opération récurrente : abonnement, prélèvement, salaire, virement programmé…

    - source « auto » : détectée dans l'historique (statut « suggere » tant que l'utilisateur ne l'a pas confirmée) ;
      « manuel » : déclarée à la main (ex. assurance annuelle pas encore vue).
    - statut : suggere (détectée, à confirmer), actif (confirmée), ignore (refusée : plus jamais proposée),
      termine (résiliée).
    - montant signé : négatif = sortie d'argent, positif = entrée.
    """

    __tablename__ = "recurring_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(150))
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchant.id", ondelete="SET NULL"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id", ondelete="SET NULL"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id", ondelete="CASCADE", name="fk_recurring_account"))
    expected_amount_cents: Mapped[int] = mapped_column(BigInteger)
    frequency: Mapped[str] = mapped_column(String(20))
    next_expected_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="suggere")
    source: Mapped[str] = mapped_column(String(10), default="auto", server_default="auto")
    # Regroupement : « vendeur », « categorie » (salaire, loyer… aux libellés changeants) ou « montant » (revenu régulier).
    basis: Mapped[str] = mapped_column(String(10), default="vendeur", server_default="vendeur")
    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    first_date: Mapped[date | None] = mapped_column(Date)
    last_date: Mapped[date | None] = mapped_column(Date)
    # Dernière échéance prévue (paiement en 3 fois, abonnement résilié à une date…) ; après : « terminé ».
    end_date: Mapped[date | None] = mapped_column(Date)
    occurrences: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Changement de prix : ancien montant et date du premier prélèvement au nouveau prix.
    previous_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    price_changed_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    merchant: Mapped["Merchant | None"] = relationship()


class Transaction(Base):
    __tablename__ = "transaction"
    __table_args__ = (
        UniqueConstraint("account_id", "dedup_hash", name="uq_transaction_dedup"),
        Index("ix_transaction_account_date", "account_id", "booked_at"),
        Index("ix_transaction_category", "category_id"),
        Index("ix_transaction_recurring", "recurring_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    booked_at: Mapped[date] = mapped_column(Date)
    value_date: Mapped[date | None] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    raw_label: Mapped[str] = mapped_column(Text)
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchant.id", ondelete="SET NULL"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id", ondelete="SET NULL"))
    # Virement entre deux comptes de l'utilisateur : exclu des dépenses / revenus.
    is_transfer: Mapped[bool] = mapped_column(Boolean, default=False)
    transfer_pair_id: Mapped[int | None] = mapped_column(ForeignKey("transaction.id", ondelete="SET NULL"))
    recurring_id: Mapped[int | None] = mapped_column(ForeignKey("recurring_series.id", ondelete="SET NULL"))
    # Empreinte (date + montant + libellé + rang) pour ne jamais importer deux fois la même ligne.
    dedup_hash: Mapped[str] = mapped_column(String(64))
    source: Mapped[str] = mapped_column(String(30), default="manuel")
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("import_batch.id", ondelete="SET NULL"))
    note: Mapped[str | None] = mapped_column(Text)
    # True si l'utilisateur a choisi la catégorie à la main (les règles ne l'écrasent plus).
    category_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    # False : visible mais exclue des statistiques (doublon d'une opération rapprochée, approvisionnement…).
    counted: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Opération jumelle sur un autre compte (ex. prélèvement CA ↔ achat PayPal correspondant).
    linked_id: Mapped[int | None] = mapped_column(
        ForeignKey("transaction.id", ondelete="SET NULL", name="fk_transaction_linked")
    )
    # Infos d'origine (vendeur, objet, n° de transaction…). Jamais d'adresse, de téléphone ni d'e-mail.
    details: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str | None] = mapped_column(String(20))
    # Règle (ou service) qui a donné la catégorie : sert aux étiquettes héritées et aux répartitions.
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("rule.id", ondelete="SET NULL", name="fk_transaction_rule"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    account: Mapped[Account] = relationship()
    merchant: Mapped["Merchant | None"] = relationship()
    category: Mapped["Category | None"] = relationship()
    tags: Mapped[list["Tag"]] = relationship(secondary=transaction_tag)  # étiquettes posées à la main


class Rule(Base):
    """Règle de catégorisation : si le libellé correspond, appliquer la catégorie / le marchand."""

    __tablename__ = "rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(255))
    match_type: Mapped[str] = mapped_column(String(20), default="contient")  # contient | regex | exact
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"))
    # Renseigné = « service » : la règle ne s'applique qu'aux opérations de ce vendeur.
    merchant_id: Mapped[int | None] = mapped_column(ForeignKey("merchant.id", ondelete="CASCADE"))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    from_correction: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    label: Mapped[str | None] = mapped_column(String(100))  # nom du service (« Assurance habitation »)
    # Montant (valeur absolue, en centimes) : condition optionnelle d'un service.
    amount_min_cents: Mapped[int | None] = mapped_column(BigInteger)
    amount_max_cents: Mapped[int | None] = mapped_column(BigInteger)

    tags: Mapped[list["Tag"]] = relationship(secondary=rule_tag)


class Budget(Base):
    __tablename__ = "budget"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id", ondelete="CASCADE"), unique=True)
    monthly_amount_cents: Mapped[int] = mapped_column(BigInteger)
    alert_threshold_pct: Mapped[int] = mapped_column(Integer, default=80)


class Goal(Base):
    __tablename__ = "goal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    target_cents: Mapped[int] = mapped_column(BigInteger)
    target_date: Mapped[date | None] = mapped_column(Date)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("account.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    icon: Mapped[str | None] = mapped_column(String(8))
    # Sans compte rattaché : montant mis de côté, tenu à la main. Avec un compte : son solde, partagé par priorité.
    saved_cents: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    priority: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Holding(Base):
    """Position d'investissement (ETF, action) sur un compte."""

    __tablename__ = "holding"
    __table_args__ = (UniqueConstraint("account_id", "isin", name="uq_holding_account_isin"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"))
    isin: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(150))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PriceSnapshot(Base):
    __tablename__ = "price_snapshot"
    __table_args__ = (UniqueConstraint("isin", "date", name="uq_price_isin_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    isin: Mapped[str] = mapped_column(String(12))
    date: Mapped[dt.date] = mapped_column(Date)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 6))


class AppMeta(Base):
    """Petites valeurs de configuration internes (versions des données par défaut, etc.)."""

    __tablename__ = "app_meta"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Tag(Base):
    """Étiquette transversale (« Assurances », « Vacances 2026 »…). N'influence pas les totaux par catégorie."""

    __tablename__ = "tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    color: Mapped[str | None] = mapped_column(String(7))


class DeviceToken(Base):
    """Appareil autorisé (appli Android, widgets) : jeton long, stocké seulement sous forme d'empreinte."""

    __tablename__ = "device_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # « app » : appli Android / widgets (jeton Bearer) ; « navigateur » : session web (cookie).
    kind: Mapped[str] = mapped_column(String(12), default="app", server_default="app")


class SecurityEvent(Base):
    """Journal de sécurité : connexions, échecs, appareils ajoutés ou révoqués, actions destructrices."""

    __tablename__ = "security_event"
    __table_args__ = (Index("ix_security_event_kind_created", "kind", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str | None] = mapped_column(String(200))


class PendingTransaction(Base):
    """Opération « à venir » d'un compte (vue à la banque, pas encore comptabilisée).

    Remplacée entièrement à chaque synchro du compte ; hors statistiques ; sert au solde prévisionnel."""

    __tablename__ = "pending_transaction"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("account.id", ondelete="CASCADE"), index=True)
    booked_at: Mapped[date] = mapped_column(Date)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    raw_label: Mapped[str] = mapped_column(String(500))
    merchant: Mapped[str | None] = mapped_column(String(150))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("category.id", ondelete="SET NULL"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
