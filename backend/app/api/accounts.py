from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Account, BalanceSnapshot
from app.schemas import AccountIn, AccountOut, AccountPatch, BalanceIn, NetWorthOut
from app.security import require_auth

router = APIRouter(prefix="/api/accounts", tags=["comptes"], dependencies=[Depends(require_auth)])


def _to_out(acc: Account) -> AccountOut:
    last = acc.balances[-1] if acc.balances else None
    return AccountOut(
        id=acc.id,
        name=acc.name,
        type=acc.type,
        institution=acc.institution,
        currency=acc.currency,
        include_in_net_worth=acc.include_in_net_worth,
        is_archived=acc.is_archived,
        provider=acc.connection.provider if acc.connection else "manuel",
        balance_cents=last.balance_cents if last else None,
        balance_date=last.date if last else None,
    )


def _get(db: Session, account_id: int) -> Account:
    acc = db.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable")
    return acc


def _set_balance(db: Session, acc: Account, day: date, cents: int) -> None:
    snap = db.scalar(
        select(BalanceSnapshot).where(BalanceSnapshot.account_id == acc.id, BalanceSnapshot.date == day)
    )
    if snap:
        snap.balance_cents = cents
    else:
        db.add(BalanceSnapshot(account_id=acc.id, date=day, balance_cents=cents))


@router.get("", response_model=list[AccountOut])
def list_accounts(include_archived: bool = False, db: Session = Depends(get_db)):
    q = select(Account).options(selectinload(Account.balances), selectinload(Account.connection))
    if not include_archived:
        q = q.where(Account.is_archived.is_(False))
    return [_to_out(a) for a in db.scalars(q.order_by(Account.type, Account.name))]


@router.get("/net-worth", response_model=NetWorthOut)
def net_worth(db: Session = Depends(get_db)):
    """Patrimoine net = somme du dernier solde connu de chaque compte actif."""
    accounts = db.scalars(
        select(Account)
        .options(selectinload(Account.balances))
        .where(Account.is_archived.is_(False), Account.include_in_net_worth.is_(True))
    )
    by_type: dict[str, int] = {}
    for acc in accounts:
        if acc.balances:
            by_type[acc.type] = by_type.get(acc.type, 0) + acc.balances[-1].balance_cents
    return NetWorthOut(total_cents=sum(by_type.values()), by_type=by_type)


@router.post("", response_model=AccountOut, status_code=status.HTTP_201_CREATED)
def create_account(body: AccountIn, db: Session = Depends(get_db)):
    acc = Account(
        name=body.name,
        type=body.type,
        institution=body.institution,
        include_in_net_worth=body.include_in_net_worth,
    )
    db.add(acc)
    db.flush()
    if body.initial_balance_cents is not None:
        _set_balance(db, acc, date.today(), body.initial_balance_cents)
    db.commit()
    db.refresh(acc)
    return _to_out(acc)


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountPatch, db: Session = Depends(get_db)):
    acc = _get(db, account_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(acc, field, value)
    db.commit()
    db.refresh(acc)
    return _to_out(acc)


@router.post("/{account_id}/balances", response_model=AccountOut)
def set_balance(account_id: int, body: BalanceIn, db: Session = Depends(get_db)):
    acc = _get(db, account_id)
    _set_balance(db, acc, body.date, body.balance_cents)
    db.commit()
    db.refresh(acc)
    return _to_out(acc)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_account(account_id: int, db: Session = Depends(get_db)):
    """Archive le compte (ses données restent en base)."""
    acc = _get(db, account_id)
    acc.is_archived = True
    db.commit()
