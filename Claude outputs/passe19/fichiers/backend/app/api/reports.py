"""Bilan du mois et export des opérations (CSV lisible par Excel)."""

from __future__ import annotations

import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Category, Transaction
from app.security import require_auth
from app.services.recap import recap

router = APIRouter(prefix="/api", tags=["bilan"], dependencies=[Depends(require_auth)])


def _month(value: str | None, today: date) -> date:
    if not value:
        # Par défaut : le mois précédent (complet).
        return date(today.year - (today.month == 1), (today.month - 2) % 12 + 1, 1)
    try:
        y, m = (int(x) for x in value.split("-"))
        return date(y, m, 1)
    except (ValueError, TypeError) as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "month : AAAA-MM attendu") from e


@router.get("/recap")
def get_recap(month: str | None = None, db: Session = Depends(get_db)) -> dict:
    today = date.today()
    m = _month(month, today)
    if m > today:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Ce mois n'a pas encore commencé")
    return recap(db, m, today)


DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def safe(text: str | None) -> str:
    """Neutralise les formules (un libellé « =HYPERLINK(…) » ne doit pas s'exécuter dans Excel)."""
    text = (text or "").replace("\n", " ")
    return "'" + text if text.startswith(DANGEROUS) else text


@router.get("/export/transactions.csv")
def export_transactions(
    date_from: date | None = None,
    date_to: date | None = None,
    account_id: int | None = None,
    include_transfers: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> Response:
    """Toutes les opérations (ou une période / un compte) : séparateur « ; », virgule décimale, UTF-8 avec BOM (Excel)."""
    q = select(Transaction).options(selectinload(Transaction.account), selectinload(Transaction.merchant), selectinload(Transaction.tags))
    if date_from:
        q = q.where(Transaction.booked_at >= date_from)
    if date_to:
        q = q.where(Transaction.booked_at <= date_to)
    if account_id is not None:
        q = q.where(Transaction.account_id == account_id)
    if not include_transfers:
        q = q.where(Transaction.is_transfer.is_(False))
    cats = {c.id: c for c in db.scalars(select(Category))}
    paths = {cid: (f"{cats[c.parent_id].name} › {c.name}" if c.parent_id in cats else c.name) for cid, c in cats.items()}
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Date", "Compte", "Libellé", "Vendeur", "Catégorie", "Montant", "Note", "Étiquettes", "Virement entre mes comptes", "Compté"])
    for t in db.scalars(q.order_by(Transaction.booked_at, Transaction.id)):
        w.writerow([
            t.booked_at.strftime("%d/%m/%Y"), safe(t.account.name if t.account else ""), safe(t.raw_label.split(" | ")[0]),
            safe(t.merchant.name if t.merchant else ""), safe(paths.get(t.category_id, "")), f"{t.amount_cents / 100:.2f}".replace(".", ","),
            safe(t.note), safe(", ".join(tag.name for tag in getattr(t, "tags", []) or [])), "oui" if t.is_transfer else "non",
            "oui" if t.counted else "non",
        ])
    name = f"wallet-operations-{date.today().isoformat()}.csv"
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store"})
