"""Pipeline d'ingestion commun à toutes les sources (fichiers, API…).

Statement (format commun) → compte → doublons / mises à jour → marchands → catégories → solde
→ rapprochements entre comptes.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.connectors.base import Statement
from app.importers import credit_agricole as ca
from app.importers import paypal as pp
from app.models import Account, BalanceSnapshot, Category, ImportBatch, Merchant, Transaction, utcnow
from app.seed import category_paths
from app.services.categorizing import Categorizer, remember_owner
from app.services.reconcile import reconcile_paypal


class ImportError_(ValueError):
    """Erreur métier lisible par l'utilisateur."""


class AccountNeeded(ImportError_):
    pass


@dataclass
class ImportResult:
    account_id: int
    account_name: str
    rows_total: int
    imported: int
    skipped: int
    updated: int
    categorized: int
    reconciled: int
    merged_manual: int
    period_start: date | None
    period_end: date | None
    balance_cents: int | None
    balance_date: date | None


def _describe(stmt: Statement) -> str:
    ext = stmt.account_external_id or ""
    suffix = f" …{ext[-4:]}" if ext and not ext.startswith("paypal:") else ""
    return f"« {stmt.account_label or 'compte'}{suffix} »"


def _find_account(db: Session, stmt: Statement, account_id: int | None) -> Account:
    if account_id is not None:
        acc = db.get(Account, account_id)
        if acc is None:
            raise ImportError_("Compte introuvable.")
        if acc.external_id and stmt.account_external_id and acc.external_id != stmt.account_external_id:
            raise ImportError_(f"Ce fichier concerne le compte {_describe(stmt)}, pas « {acc.name} ».")
        return acc
    if stmt.account_external_id:
        acc = db.scalar(select(Account).where(Account.external_id == stmt.account_external_id))
        if acc:
            return acc
    raise AccountNeeded(f"Aucun compte de l'appli n'est encore associé à {_describe(stmt)}. Choisis-le dans la liste.")


def known_merchant_aliases(db: Session) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for m in db.scalars(select(Merchant)):
        for key in m.aliases or []:
            aliases[key] = m.name
    return aliases


MANUAL_MATCH_DAYS = 3


def merge_manual_entries(db: Session, account_id: int, imported: list[Transaction]) -> int:
    """Une opération saisie à la main puis retrouvée dans un import (même compte, même montant, ±3 jours)
    est fusionnée : on garde la ligne importée, avec la catégorie, la note et les étiquettes saisies."""
    manual = list(
        db.scalars(
            select(Transaction)
            .options(selectinload(Transaction.tags))
            .where(Transaction.account_id == account_id, Transaction.source == "manuel")
        )
    )
    if not manual:
        return 0
    merged = 0
    for t in sorted(imported, key=lambda x: x.booked_at):
        cands = [m for m in manual if m.amount_cents == t.amount_cents and abs((m.booked_at - t.booked_at).days) <= MANUAL_MATCH_DAYS]
        if not cands:
            continue
        m = min(cands, key=lambda x: (abs((x.booked_at - t.booked_at).days), x.id))
        if m.category_locked:
            t.category_id, t.category_locked, t.is_transfer, t.rule_id = m.category_id, True, m.is_transfer, None
        if m.note:
            t.note = m.note
        t.tags = list({tg.id: tg for tg in [*t.tags, *m.tags]}.values())
        t.details = {**(t.details or {}), "saisie_manuelle": m.raw_label}
        manual.remove(m)
        db.delete(m)
        merged += 1
    db.flush()
    return merged


def ingest(
    db: Session,
    stmt: Statement,
    account_id: int | None,
    filename: str | None,
    institution: str,
    required_type: str | None = None,
) -> ImportResult:
    acc = _find_account(db, stmt, account_id)
    if required_type and acc.type != required_type:
        raise ImportError_(f"« {acc.name} » n'est pas un compte de type {required_type}. Choisis ton compte PayPal (ou crée-le dans Comptes avec le type PayPal).")
    if not acc.external_id and stmt.account_external_id:
        acc.external_id = stmt.account_external_id
    acc.institution = acc.institution or institution
    remember_owner(db, stmt.holder)

    merchants = {m.name: m for m in db.scalars(select(Merchant))}

    def merchant_for(name: str | None) -> Merchant | None:
        if not name:
            return None
        name = name.strip()[:150]
        m = merchants.get(name)
        if m is None:
            m = Merchant(name=name, aliases=[])
            db.add(m)
            merchants[name] = m
        return m

    for key, name in stmt.merchant_aliases.items():
        m = merchant_for(name)
        if m is not None and key not in (m.aliases or []):
            m.aliases = [*(m.aliases or []), key]  # nouvelle liste : SQLAlchemy détecte le changement

    existing = {
        t.dedup_hash: t
        for t in db.scalars(select(Transaction).where(Transaction.account_id == acc.id))
    }
    paths = category_paths(db)
    kinds = dict(db.execute(select(Category.id, Category.kind)).all())
    batch = ImportBatch(source=stmt.source, filename=filename, account_id=acc.id, rows_total=len(stmt.transactions))
    db.add(batch)
    db.flush()

    new: list[Transaction] = []
    updated = 0
    for raw in stmt.transactions:
        old = existing.get(raw.dedup_key)
        if old is not None:
            # Même opération déjà connue : on met à jour ce qui peut évoluer (statut « en attente » → « terminé »).
            if raw.status and old.status != raw.status:
                old.status = raw.status
                old.amount_cents = raw.amount_cents
                updated += 1
            continue
        t = Transaction(
            account_id=acc.id,
            booked_at=raw.booked_at,
            amount_cents=raw.amount_cents,
            raw_label=raw.raw_label,
            merchant=merchant_for(raw.merchant_hint),
            dedup_hash=raw.dedup_key,
            source=stmt.source,
            import_batch_id=batch.id,
            is_transfer=False,
            category_locked=False,
            counted=raw.counted,
            details=raw.details,
            status=raw.status,
        )
        if raw.force_category_path and raw.force_category_path in paths:
            t.category_id = paths[raw.force_category_path]
            t.category_locked = True
            t.is_transfer = kinds.get(t.category_id) == "transfert"
        db.add(t)
        existing[raw.dedup_key] = t
        new.append(t)

    db.flush()
    Categorizer(db).apply(new)
    merged_manual = merge_manual_entries(db, acc.id, new)
    categorized = sum(1 for t in new if t.category_id is not None)

    if stmt.balance_date is not None and stmt.balance_cents is not None:
        snap = db.scalar(
            select(BalanceSnapshot).where(BalanceSnapshot.account_id == acc.id, BalanceSnapshot.date == stmt.balance_date)
        )
        if snap:
            snap.balance_cents = stmt.balance_cents
            snap.recorded_at = utcnow()
        else:
            db.add(BalanceSnapshot(account_id=acc.id, date=stmt.balance_date, balance_cents=stmt.balance_cents))

    batch.rows_imported = len(new)
    batch.rows_skipped = len(stmt.transactions) - len(new)
    db.flush()
    reconciled = reconcile_paypal(db)
    db.commit()

    period = stmt.period
    return ImportResult(
        account_id=acc.id,
        account_name=acc.name,
        rows_total=len(stmt.transactions),
        imported=len(new),
        skipped=len(stmt.transactions) - len(new),
        updated=updated,
        categorized=categorized,
        reconciled=reconciled,
        merged_manual=merged_manual,
        period_start=period[0] if period else None,
        period_end=period[1] if period else None,
        balance_cents=stmt.balance_cents,
        balance_date=stmt.balance_date,
    )


def import_credit_agricole(db: Session, raw: bytes, filename: str | None, account_id: int | None) -> ImportResult:
    try:
        stmt = ca.to_statement(raw, known_merchant_aliases(db))
    except ca.CAParseError as e:
        raise ImportError_(str(e)) from e
    return ingest(db, stmt, account_id, filename, "Crédit Agricole")


def import_paypal(db: Session, raw: bytes, filename: str | None, account_id: int | None) -> ImportResult:
    try:
        stmt = pp.parse(raw)
    except (pp.PayPalParseError, ca.CAParseError) as e:
        raise ImportError_(str(e)) from e
    return ingest(db, stmt, account_id, filename, "PayPal", required_type="paypal")


IMPORTERS = {"credit-agricole": import_credit_agricole, "paypal": import_paypal}
