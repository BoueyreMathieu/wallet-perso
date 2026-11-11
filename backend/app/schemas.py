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
