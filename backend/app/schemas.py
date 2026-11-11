import datetime as dt
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccountType = Literal["courant", "epargne", "investissement", "paypal", "especes", "credit", "bien"]


class LoginIn(BaseModel):
    password: str


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    type: AccountType
    institution: str | None = Field(default=None, max_length=100)
    include_in_net_worth: bool = True
    # Solde de départ optionnel (en centimes), enregistré à la date du jour.
    initial_balance_cents: int | None = None


class AccountPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    type: AccountType | None = None
    institution: str | None = None
    include_in_net_worth: bool | None = None
    is_archived: bool | None = None


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: str
    institution: str | None
    currency: str
    include_in_net_worth: bool
    is_archived: bool
    provider: str
    balance_cents: int | None
    balance_date: date | None


class BalanceIn(BaseModel):
    date: dt.date
    balance_cents: int


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    name: str
    kind: str
    color: str | None


class NetWorthOut(BaseModel):
    total_cents: int
    by_type: dict[str, int]


class ImportResultOut(BaseModel):
    account_id: int
    account_name: str
    rows_total: int
    imported: int
    skipped: int
    updated: int
    categorized: int
    reconciled: int
    merged_manual: int = 0
    period_start: date | None
    period_end: date | None
    balance_cents: int | None
    balance_date: date | None


class TagRef(BaseModel):
    id: int
    name: str
    color: str | None
    source: str  # manuel | vendeur | service


class TransactionOut(BaseModel):
    id: int
    account_id: int
    account_name: str
    booked_at: date
    amount_cents: int
    label: str
    raw_label: str
    merchant_id: int | None
    merchant: str | None
    category_id: int | None
    category_locked: bool
    is_transfer: bool
    note: str | None
    counted: bool
    linked_id: int | None
    status: str | None
    details: dict | None
    rule_id: int | None = None
    source: str = ""
    tags: list[TagRef] = []


class TransactionPage(BaseModel):
    items: list[TransactionOut]
    total: int


class TransactionPatch(BaseModel):
    category_id: int | None = None
    # True : la catégorie s'applique à toutes les opérations de ce marchand (et aux futures).
    apply_to_merchant: bool = False
    note: str | None = None
    # Modifiables uniquement pour une opération saisie à la main :
    account_id: int | None = None
    booked_at: date | None = None
    amount_cents: int | None = None
    label: str | None = Field(default=None, min_length=1, max_length=255)
    merchant: str | None = Field(default=None, max_length=150)


class ManualTransactionIn(BaseModel):
    account_id: int
    booked_at: date
    amount_cents: int  # négatif = dépense, positif = revenu
    label: str = Field(min_length=1, max_length=255)
    merchant: str | None = Field(default=None, max_length=150)
    category_id: int | None = None
    note: str | None = None
    tag_ids: list[int] = []


class MerchantGroupOut(BaseModel):
    merchant_id: int | None
    merchant: str | None
    count: int
    total_cents: int
    last_date: date
    sample_label: str


class CategoryAssign(BaseModel):
    category_id: int | None


class UpdatedOut(BaseModel):
    updated: int


class RuleOut(BaseModel):
    id: int
    pattern: str
    match_type: str
    category_id: int | None
    priority: int
    from_correction: bool


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=2000)
    add_tag_ids: list[int] = []
    remove_tag_ids: list[int] = []
    # Si présent : catégorie posée à la main sur toutes les opérations sélectionnées (None = « à catégoriser »).
    set_category: bool = False
    category_id: int | None = None


class BulkOut(BaseModel):
    updated: int
    inherited_kept: int = 0


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class TagOut(BaseModel):
    id: int
    name: str
    color: str | None
    transactions: int  # opérations portant l'étiquette (à la main ou héritée)
    spent_cents: int  # dépenses comptées
    merchants: int
    services: int


class ServiceIn(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    pattern: str = Field(default="", max_length=255)
    match_type: Literal["contient", "regex"] = "contient"
    amount_min_cents: int | None = Field(default=None, ge=0)
    amount_max_cents: int | None = Field(default=None, ge=0)
    category_id: int
    tag_ids: list[int] = []


class ServicePatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    pattern: str | None = Field(default=None, max_length=255)
    match_type: Literal["contient", "regex"] | None = None
    amount_min_cents: int | None = Field(default=None, ge=0)
    amount_max_cents: int | None = Field(default=None, ge=0)
    category_id: int | None = None
    tag_ids: list[int] | None = None


class ServiceOut(BaseModel):
    id: int
    merchant_id: int
    label: str | None
    pattern: str
    match_type: str
    amount_min_cents: int | None
    amount_max_cents: int | None
    category_id: int | None
    tag_ids: list[int]


class ServiceSuggestion(BaseModel):
    pattern: str
    label: str
    matches: int
    amount_cents: int


class TagIds(BaseModel):
    tag_ids: list[int]
