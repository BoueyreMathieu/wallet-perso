"""Gestion des données : historique des imports et réinitialisations."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Category, ImportBatch
from app.schemas import UpdatedOut
from app.security import require_auth, require_confirmation
from app.services import cleanup

router = APIRouter(prefix="/api/data", tags=["données"], dependencies=[Depends(require_auth)])

CONFIRM_WORD = "EFFACER"
# Actions destructrices : mot de passe redemandé (un cookie ou jeton volé ne suffit pas).
confirm = [Depends(require_confirmation)]


class ImportBatchOut(BaseModel):
    id: int
    source: str
    filename: str | None
    account_id: int | None
    account_name: str | None
    started_at: datetime
    rows_total: int
    rows_imported: int


class WipeIn(BaseModel):
    confirm: str
    keep_accounts: bool = True


@router.get("/imports", response_model=list[ImportBatchOut])
def list_imports(db: Session = Depends(get_db)):
    names = dict(db.execute(select(Account.id, Account.name)).all())
    batches = db.scalars(select(ImportBatch).order_by(ImportBatch.started_at.desc(), ImportBatch.id.desc())).all()
    return [
        ImportBatchOut(
            id=b.id,
            source=b.source,
            filename=b.filename,
            account_id=b.account_id,
            account_name=names.get(b.account_id),
            started_at=b.started_at,
            rows_total=b.rows_total,
            rows_imported=b.rows_imported,
        )
        for b in batches
    ]


@router.delete("/imports/{batch_id}", response_model=UpdatedOut, dependencies=confirm)
def undo_import(batch_id: int, db: Session = Depends(get_db)):
    """Annule un import : supprime les opérations qu'il avait ajoutées."""
    b = db.get(ImportBatch, batch_id)
    if b is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import introuvable")
    n = cleanup.undo_import(db, b)
    db.commit()
    return UpdatedOut(updated=n)


def _account(db: Session, account_id: int) -> Account:
    acc = db.get(Account, account_id)
    if acc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compte introuvable")
    return acc


@router.post("/accounts/{account_id}/clear", response_model=UpdatedOut, dependencies=confirm)
def clear_account(account_id: int, db: Session = Depends(get_db)):
    """Vide un compte (opérations, soldes, imports) en le gardant."""
    n = cleanup.clear_account(db, _account(db, account_id))
    db.commit()
    return UpdatedOut(updated=n)


@router.delete("/accounts/{account_id}", response_model=UpdatedOut, dependencies=confirm)
def delete_account(account_id: int, db: Session = Depends(get_db)):
    """Supprime définitivement un compte et toutes ses données."""
    n = cleanup.delete_account(db, _account(db, account_id))
    db.commit()
    return UpdatedOut(updated=n)


@router.post("/categories/{category_id}/reset", response_model=UpdatedOut, dependencies=confirm)
def reset_category(category_id: int, db: Session = Depends(get_db)):
    if db.get(Category, category_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catégorie introuvable")
    n = cleanup.reset_category(db, category_id)
    db.commit()
    return UpdatedOut(updated=n)


@router.post("/reset-categorization", response_model=UpdatedOut, dependencies=confirm)
def reset_all_categorization(db: Session = Depends(get_db)):
    """Oublie toutes tes catégorisations (vendeurs et corrections) ; les règles par défaut restent."""
    n = cleanup.reset_all_categorization(db)
    db.commit()
    return UpdatedOut(updated=n)


@router.post("/wipe", response_model=UpdatedOut, dependencies=confirm)
def wipe(body: WipeIn, db: Session = Depends(get_db)):
    if body.confirm != CONFIRM_WORD:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Tape {CONFIRM_WORD} pour confirmer")
    cleanup.wipe_all(db, body.keep_accounts)
    db.commit()
    return UpdatedOut(updated=1)
