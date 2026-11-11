"""Solde d'un compte = dernier solde connu + opérations postérieures.

- Un solde « connu » vient d'un export bancaire, d'une synchro ou d'une saisie dans Comptes.
- Les opérations datées APRÈS ce solde s'y ajoutent (saisies manuelles, imports plus récents sans solde…).
- Une opération saisie à la main le même jour, mais après l'enregistrement du solde, s'y ajoute aussi.
- Sans solde connu : somme de toutes les opérations du compte.
"""

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BalanceSnapshot, Transaction


def _aware(d: datetime | None) -> datetime | None:
    if d is None:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def current_balance(db: Session, account_id: int) -> tuple[int | None, date | None]:
    snap = db.scalar(
        select(BalanceSnapshot)
        .where(BalanceSnapshot.account_id == account_id)
        .order_by(BalanceSnapshot.date.desc(), BalanceSnapshot.recorded_at.desc())
        .limit(1)
    )
    q = select(Transaction.booked_at, Transaction.amount_cents, Transaction.source, Transaction.created_at).where(
        Transaction.account_id == account_id
    )
    if snap is not None:
        q = q.where(Transaction.booked_at >= snap.date)
    rows = db.execute(q).all()
    if snap is None:
        if not rows:
            return None, None
        return sum(r.amount_cents for r in rows), max(r.booked_at for r in rows)

    recorded = _aware(snap.recorded_at)
    total, last = snap.balance_cents, snap.date
    for r in rows:
        later_same_day = r.booked_at == snap.date and r.source == "manuel" and recorded and _aware(r.created_at) > recorded
        if r.booked_at > snap.date or later_same_day:
            total += r.amount_cents
            last = max(last, r.booked_at)
    return total, last
