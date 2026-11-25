"""Patrimoine : calculs purs (sans base) pour les biens, les crédits et l'épargne.

- Bien (voiture, matériel…) : valeur d'achat qui perd un pourcentage par an (dépréciation dégressive, au jour près).
- Crédit amortissable : mensualité constante, tableau d'amortissement, capital restant dû à une date.
- Épargne rémunérée : intérêts estimés sur un an au taux indiqué, place restante sous le plafond.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date


def _add_months(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    y, m = idx // 12, idx % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


# --- Bien qui se déprécie ------------------------------------------------------------------------


def depreciated_value(purchase_cents: int, purchase_date: date, rate_pct: float, on: date) -> int:
    """Valeur à la date `on` : achat × (1 − taux)^(années écoulées). Avant l'achat : valeur d'achat."""
    if on <= purchase_date or rate_pct <= 0:
        return purchase_cents
    years = (on - purchase_date).days / 365.25
    return max(0, round(purchase_cents * (1 - min(rate_pct, 100) / 100) ** years))


# --- Crédit amortissable -------------------------------------------------------------------------


@dataclass(frozen=True)
class Installment:
    n: int
    date: date
    payment_cents: int  # capital + intérêts (hors assurance)
    interest_cents: int
    principal_cents: int
    remaining_cents: int  # capital restant dû après cette échéance


def monthly_payment(principal_cents: int, rate_pct: float, months: int) -> int:
    if months <= 0:
        return principal_cents
    r = rate_pct / 100 / 12
    if r == 0:
        return round(principal_cents / months)
    return round(principal_cents * r / (1 - (1 + r) ** -months))


def loan_schedule(principal_cents: int, rate_pct: float, months: int, first_payment: date) -> list[Installment]:
    """Tableau d'amortissement à mensualités constantes (la dernière solde le reste)."""
    pay = monthly_payment(principal_cents, rate_pct, months)
    r = rate_pct / 100 / 12
    left = principal_cents
    out = []
    for i in range(months):
        interest = round(left * r)
        part = left if i == months - 1 else min(left, pay - interest)
        left -= part
        out.append(Installment(i + 1, _add_months(first_payment, i), part + interest, interest, part, left))
    return out


def loan_remaining(principal_cents: int, rate_pct: float, months: int, first_payment: date, on: date) -> int:
    """Capital restant dû à la date `on` (échéances passées déduites)."""
    left = principal_cents
    for inst in loan_schedule(principal_cents, rate_pct, months, first_payment):
        if inst.date > on:
            break
        left = inst.remaining_cents
    return left


# --- Épargne -------------------------------------------------------------------------------------


def yearly_interest(balance_cents: int, rate_pct: float, ceiling_cents: int | None = None) -> int:
    """Intérêts sur un an si le solde ne bouge pas (au-delà du plafond, rien n'est rémunéré)."""
    base = min(balance_cents, ceiling_cents) if ceiling_cents else balance_cents
    return max(0, round(base * rate_pct / 100))


# --- Valeur d'un compte à une date, d'après ses réglages ----------------------------------------------


def _date(v) -> date | None:
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)) if v else None
    except ValueError:
        return None


def computed_value(account_type: str, params: dict | None, on: date) -> int | None:
    """Valeur calculée (bien : valeur dépréciée ; crédit : − capital restant dû), ou None si pas de réglage."""
    p = params or {}
    if account_type == "bien" and p.get("purchase_cents") and _date(p.get("purchase_date")):
        return depreciated_value(int(p["purchase_cents"]), _date(p["purchase_date"]), float(p.get("depreciation_pct") or 0), on)
    if account_type == "credit" and p.get("principal_cents") and p.get("months") and _date(p.get("first_payment")):
        start = _date(p["first_payment"])
        if on < _add_months(start, -1):
            return None  # crédit pas encore souscrit à cette date
        return -loan_remaining(int(p["principal_cents"]), float(p.get("rate_pct") or 0), int(p["months"]), start, on)
    return None
