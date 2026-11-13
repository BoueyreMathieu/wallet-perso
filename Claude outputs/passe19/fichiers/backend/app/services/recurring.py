"""Opérations récurrentes : détection dans l'historique, liaison des opérations, suivi des échéances.

Appelé à la fin de chaque import / synchro, au démarrage et à la demande (« Relancer la détection »).
Le cœur de la détection (sans base) est dans app/recurrence.py.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Account, Category, Merchant, RecurringSeries, Transaction
from app.recurrence import FREQUENCIES, Point, detect, detect_regular_income, grace_days, monthly_cost, next_after

log = logging.getLogger("wallet.recurrents")

WINDOW_DAYS = 430  # un peu plus d'un an : deux échéances annuelles
MATCH_TOLERANCE = 0.35  # un montant à ±35 % reste la même série (hausse de prix, salaire variable)
ACTIVE_STATUSES = ("suggere", "actif")


def _close(a: int, b: int) -> bool:
    return (a > 0) == (b > 0) and abs(abs(a) - abs(b)) <= MATCH_TOLERANCE * max(abs(a), abs(b)) + 100


def _unlink_others(db: Session, series_id: int, keep: list[int]) -> None:
    q = update(Transaction).where(Transaction.recurring_id == series_id)
    if keep:
        q = q.where(Transaction.id.not_in(keep))
    db.execute(q.values(recurring_id=None))


def _link(db: Session, series_id: int, ids: list[int]) -> None:
    if ids:
        db.execute(update(Transaction).where(Transaction.id.in_(ids)).values(recurring_id=series_id))


def _delete(db: Session, s: RecurringSeries) -> None:
    _unlink_others(db, s.id, [])
    db.delete(s)


def _key(s: RecurringSeries) -> tuple | None:
    """Clé de regroupement d'une série : par vendeur, ou par catégorie (salaire, loyer… aux libellés changeants)."""
    if s.account_id is None:
        return None
    if s.basis == "categorie":
        return ("c", s.account_id, s.category_id, s.expected_amount_cents > 0) if s.category_id is not None else None
    if s.basis == "montant":
        return ("a", s.account_id, None, True)
    return ("m", s.account_id, s.merchant_id, s.expected_amount_cents > 0) if s.merchant_id is not None else None


def _category_eligible(db: Session) -> set[int]:
    """Catégories où un récurrent se repère aussi sans vendeur commun : revenus (salaire…), charges fixes et
    transferts (épargne mise de côté chaque mois)."""
    from app.layers import effective_natures  # import local : pas de dépendance au démarrage
    from app.seed import resolve_paths

    cats = db.execute(select(Category.id, Category.parent_id, Category.kind, Category.nature)).all()
    natures = effective_natures({c.id: c.nature for c in cats}, {c.id: c.parent_id for c in cats}, resolve_paths(db))
    return {c.id for c in cats if c.kind in ("revenu", "transfert") or (c.kind == "depense" and natures.get(c.id) == "fixe")}


def refresh(db: Session, today: date | None = None) -> dict:
    """Détecte / met à jour les séries et relie les opérations. Ne fait pas de commit.

    1er passage : par vendeur (compte × vendeur × sens). 2e passage, pour les opérations restantes des catégories
    de revenus et de charges fixes : par catégorie (un salaire dont le libellé change chaque mois, un loyer payé
    par virements aux intitulés différents…)."""
    today = today or date.today()
    lo = today - timedelta(days=WINDOW_DAYS)
    archived = {aid for aid, arch in db.execute(select(Account.id, Account.is_archived)).all() if arch}
    names = dict(db.execute(select(Merchant.id, Merchant.name)).all())
    cat_names = dict(db.execute(select(Category.id, Category.name)).all())

    rows = db.execute(
        select(
            Transaction.id, Transaction.account_id, Transaction.merchant_id, Transaction.booked_at,
            Transaction.amount_cents, Transaction.is_transfer, Transaction.category_id,
        ).where(Transaction.booked_at >= lo, Transaction.counted.is_(True), Transaction.amount_cents != 0)
    ).all()
    info = {r.id: r for r in rows if r.account_id not in archived}

    series = list(db.scalars(select(RecurringSeries)).all())
    # Séries détectées dont le vendeur / la catégorie a disparu (fusion, suppression) : la détection les recréera.
    for s in [s for s in series if s.source == "auto" and _key(s) is None]:
        _delete(db, s)
        series.remove(s)
    by_key: dict[tuple, list[RecurringSeries]] = defaultdict(list)
    for s in series:
        k = _key(s)
        if k is not None:
            by_key[k].append(s)

    touched: set[int] = set()
    used: set[int] = set()
    counts = {"created": 0, "updated": 0}

    def process(key: tuple, pts: list[Point], detector=detect) -> None:
        for d in detector(pts, today):
            candidates = [s for s in by_key[key] if s.id not in touched and _close(s.expected_amount_cents, d.expected_amount_cents)]
            match = min(candidates, key=lambda s: abs(s.expected_amount_cents - d.expected_amount_cents), default=None)
            if match is None:
                if not d.active:
                    continue  # série terminée depuis longtemps : rien à proposer
                txs = [info[i] for i in d.ids]
                basis = {"c": "categorie", "a": "montant"}.get(key[0], "vendeur")
                cats = Counter(t.category_id for t in txs if t.category_id is not None)
                merchants = Counter(t.merchant_id for t in txs if t.merchant_id is not None)
                top_cat = cats.most_common(1)[0][0] if cats else None
                if basis == "categorie":
                    label = cat_names.get(key[2], "?")
                elif basis == "montant":  # revenu régulier repéré par son montant et sa date
                    label = cat_names.get(top_cat) if top_cat else names.get(merchants.most_common(1)[0][0]) if merchants else "Revenu régulier"
                else:
                    label = names.get(key[2], "?")
                match = RecurringSeries(
                    label=label or "Revenu régulier",
                    merchant_id=key[2] if basis == "vendeur" else None, account_id=key[1], source="auto", status="suggere",
                    basis=basis, frequency=d.frequency, expected_amount_cents=d.expected_amount_cents,
                    category_id=key[2] if basis == "categorie" else top_cat,
                    is_transfer=sum(t.is_transfer for t in txs) * 2 > len(txs),
                )
                db.add(match)
                db.flush()
                by_key[key].append(match)
                counts["created"] += 1
            else:
                counts["updated"] += 1
            touched.add(match.id)
            used.update(d.ids)
            if match.status == "ignore":
                _unlink_others(db, match.id, [])
                continue
            if match.status == "termine" and match.last_date and d.last_date > match.last_date:
                match.status = "suggere"  # marquée terminée, mais de nouveaux prélèvements arrivent : on la repropose
            if match.status == "suggere":
                match.frequency = d.frequency  # confirmée par l'utilisateur : sa fréquence est gardée
                if not d.active:
                    match.status = "termine"
            match.expected_amount_cents = d.expected_amount_cents
            match.first_date, match.last_date, match.occurrences = d.first_date, d.last_date, len(d.ids)
            match.previous_amount_cents, match.price_changed_on = d.previous_amount_cents, d.price_changed_on
            match.next_expected_date = next_after(d.last_date, match.frequency)
            _unlink_others(db, match.id, d.ids)
            _link(db, match.id, d.ids)

    groups: dict[tuple, list[Point]] = defaultdict(list)
    for r in info.values():
        if r.merchant_id is not None:
            groups[("m", r.account_id, r.merchant_id, r.amount_cents > 0)].append(Point(r.id, r.booked_at, r.amount_cents))
    for key, pts in groups.items():
        process(key, pts)

    eligible = _category_eligible(db)
    by_category: dict[tuple, list[Point]] = defaultdict(list)
    for r in info.values():
        if r.id not in used and r.category_id in eligible:
            by_category[("c", r.account_id, r.category_id, r.amount_cents > 0)].append(Point(r.id, r.booked_at, r.amount_cents))
    for key, pts in by_category.items():
        process(key, pts)

    # 3e passage : revenus mensuels réguliers restants, repérés par montant et date (salaire jamais catégorisé,
    # au libellé différent chaque mois…).
    by_account: dict[tuple, list[Point]] = defaultdict(list)
    for r in info.values():
        if r.id not in used and r.amount_cents > 0 and not r.is_transfer:
            by_account[("a", r.account_id, None, True)].append(Point(r.id, r.booked_at, r.amount_cents))
    for key, pts in by_account.items():
        process(key, pts, detect_regular_income)

    # Date de fin dépassée : la série est terminée (plus d'échéance prévue).
    for s in series:
        if s.end_date is not None and s.end_date < today and s.status in ("actif", "suggere"):
            s.status = "termine"
            touched.add(s.id)

    # Séries non retrouvées par la détection.
    for s in series:
        if s.id in touched:
            continue
        if s.source == "auto" and s.status == "suggere":
            _delete(db, s)  # plus assez d'indices : on ne la propose plus
        elif s.status == "actif" and _key(s) is not None and (s.merchant_id is not None or s.basis in ("categorie", "montant")):
            _follow(db, s, info)
        elif s.status == "actif" and s.merchant_id is None and s.next_expected_date and s.next_expected_date < today:
            # Déclarée à la main sans vendeur : impossible de la reconnaître, on la suppose payée à l'échéance.
            while s.next_expected_date < today:
                s.last_date = s.next_expected_date
                s.next_expected_date = next_after(s.next_expected_date, s.frequency)
    db.flush()
    return counts


def _follow(db: Session, s: RecurringSeries, info: dict) -> None:
    """Série confirmée ou déclarée à la main : on y rattache les nouvelles opérations (même vendeur ou même catégorie)."""
    since = s.last_date or (s.next_expected_date - timedelta(days=grace_days(s.frequency)) if s.next_expected_date else None)
    if s.basis == "categorie":
        same = lambda r: r.category_id == s.category_id  # noqa: E731
    elif s.basis == "montant":
        same = lambda r: not r.is_transfer  # noqa: E731 - même compte, même sens et montant proche (vérifiés ensuite)
    else:
        same = lambda r: r.merchant_id == s.merchant_id  # noqa: E731
    new = sorted(
        (
            r for r in info.values()
            if r.account_id == s.account_id and same(r) and (since is None or r.booked_at > since)
            and _close(r.amount_cents, s.expected_amount_cents)
            and db.get(Transaction, r.id).recurring_id in (None, s.id)
        ),
        key=lambda r: r.booked_at,
    )
    if not new:
        return
    _link(db, s.id, [r.id for r in new])
    last = new[-1]
    if s.first_date is None:
        s.first_date = new[0].booked_at
    if not _same(last.amount_cents, s.expected_amount_cents):
        s.previous_amount_cents, s.price_changed_on = s.expected_amount_cents, last.booked_at
    s.expected_amount_cents = last.amount_cents
    s.last_date = last.booked_at
    s.occurrences = (s.occurrences or 0) + len(new)
    s.next_expected_date = next_after(last.booked_at, s.frequency)


def _same(a: int, b: int) -> bool:
    return abs(a - b) <= max(10, abs(b) // 100)


# --- Présentation -------------------------------------------------------------------------------


def kind_of(s: RecurringSeries) -> str:
    if s.is_transfer:
        return "virement"
    return "revenu" if s.expected_amount_cents > 0 else "depense"


def describe(db: Session, s: RecurringSeries, today: date, totals: dict[int, int], accounts: dict[int, str]) -> dict:
    late_days = (today - s.next_expected_date).days if s.next_expected_date and s.next_expected_date < today else 0
    increase = (
        s.previous_amount_cents is not None
        and abs(s.expected_amount_cents) > abs(s.previous_amount_cents)
        and s.price_changed_on is not None
    )
    return {
        "id": s.id,
        "label": s.label,
        "merchant_id": s.merchant_id,
        "merchant": s.merchant.name if s.merchant else None,
        "account_id": s.account_id,
        "account_name": accounts.get(s.account_id) if s.account_id else None,
        "category_id": s.category_id,
        "amount_cents": s.expected_amount_cents,
        "frequency": s.frequency,
        "frequency_label": FREQUENCIES[s.frequency].label if s.frequency in FREQUENCIES else s.frequency,
        "monthly_cents": monthly_cost(s.expected_amount_cents, s.frequency),
        "yearly_cents": round(monthly_cost(s.expected_amount_cents, s.frequency) * 12),
        "next_date": s.next_expected_date,
        "last_date": s.last_date,
        "first_date": s.first_date,
        "end_date": s.end_date,
        "occurrences": s.occurrences or 0,
        "total_cents": totals.get(s.id, 0),
        "status": s.status,
        "source": s.source,
        "basis": s.basis,
        "kind": kind_of(s),
        "late_days": late_days,
        # Très en retard : probablement résiliée (à confirmer par l'utilisateur).
        "maybe_ended": late_days > grace_days(s.frequency) if s.frequency in FREQUENCIES else False,
        "previous_amount_cents": s.previous_amount_cents,
        "price_changed_on": s.price_changed_on,
        "price_increase": increase,
    }
