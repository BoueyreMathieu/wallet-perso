"""Services d'un vendeur (règles rattachées à un vendeur) et étiquettes."""

import re
from collections import defaultdict

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.categorize import normalize
from app.models import Rule, Tag, Transaction, merchant_tag, rule_tag, transaction_tag
from app.services.categorizing import SERVICE_PRIORITY, recategorize

# Mots trop courants pour distinguer un service d'un autre.
STOP_WORDS = {
    "PRELEVEMENT", "PAIEMENT", "PAR", "CARTE", "VIREMENT", "EMIS", "FAVEUR", "VOTRE", "VOTRE", "POUR", "AVEC",
    "SA", "SAS", "SARL", "SCA", "ECHEANCE", "COTISATION", "CONTRAT", "FACTURE", "NUMERO", "CLIENT", "COMPTE",
    "WEB", "INST", "VERS", "DES", "LES", "DU", "DE", "LA", "LE", "ET", "EN", "AU", "AUX", "ABONNEMENT",
}


def _tokens(label: str, merchant: str | None) -> set[str]:
    merchant_words = set(normalize(merchant).split()) if merchant else set()
    out = set()
    for tok in re.findall(r"[A-Z0-9][A-Z0-9'.&-]{2,}", normalize(label)):
        tok = tok.strip(".-'")
        if len(tok) < 3 or tok in STOP_WORDS or tok in merchant_words:
            continue
        if tok.isdigit() and len(tok) < 5:  # années, jours… mais on garde les n° de contrat
            continue
        out.add(tok)
    return out


def suggest_service(db: Session, t: Transaction) -> dict:
    """Propose le mot (ou n° de contrat) qui distingue cette opération des autres du même vendeur."""
    name = t.merchant.name if t.merchant else None
    others = db.scalars(select(Transaction).where(Transaction.merchant_id == t.merchant_id, Transaction.id != t.id)).all()
    mine = _tokens(t.raw_label, name)
    other_tokens = [_tokens(o.raw_label, name) for o in others]
    best: tuple | None = None
    for tok in mine:
        shared = sum(1 for ot in other_tokens if tok in ot)
        if others and shared == len(others):
            continue  # présent partout : ne distingue rien
        score = (shared, tok.isalpha(), len(tok))
        if best is None or score > best[0]:
            best = (score, tok, shared)
    if best is None:
        return {"pattern": "", "label": "", "matches": 1, "amount_cents": abs(t.amount_cents)}
    _, tok, shared = best
    return {"pattern": tok, "label": tok.capitalize() if tok.isalpha() else "", "matches": shared + 1, "amount_cents": abs(t.amount_cents)}


def save_service(db: Session, rule: Rule, data: dict) -> int:
    """Crée / met à jour un service puis recatégorise les opérations du vendeur."""
    for field in ("label", "pattern", "match_type", "amount_min_cents", "amount_max_cents", "category_id"):
        if field in data:
            setattr(rule, field, data[field])
    rule.pattern = (rule.pattern or "").strip()
    if rule.match_type == "regex":
        re.compile(rule.pattern)  # lève une erreur si l'expression est invalide
    if "tag_ids" in data:
        rule.tags = list(db.scalars(select(Tag).where(Tag.id.in_(data["tag_ids"] or []))))
    rule.priority = SERVICE_PRIORITY
    rule.from_correction = True
    db.add(rule)
    db.flush()
    return recategorize(db, rule.merchant_id)


# --- Étiquettes ----------------------------------------------------------------------


def tag_condition(tag_id: int):
    """Condition SQL : l'opération porte l'étiquette (posée à la main, via son vendeur ou son service)."""
    return or_(
        Transaction.id.in_(select(transaction_tag.c.transaction_id).where(transaction_tag.c.tag_id == tag_id)),
        Transaction.merchant_id.in_(select(merchant_tag.c.merchant_id).where(merchant_tag.c.tag_id == tag_id)),
        Transaction.rule_id.in_(select(rule_tag.c.rule_id).where(rule_tag.c.tag_id == tag_id)),
    )


def effective_tags(db: Session, txns: list[Transaction]) -> dict[int, list[dict]]:
    """Étiquettes de chaque opération : {id: [{id, name, color, source}]} (source = manuel | vendeur | service)."""
    if not txns:
        return {}
    ids = [t.id for t in txns]
    merchant_ids = {t.merchant_id for t in txns if t.merchant_id}
    rule_ids = {t.rule_id for t in txns if t.rule_id}
    manual = defaultdict(set)
    for tid, tag in db.execute(select(transaction_tag.c.transaction_id, transaction_tag.c.tag_id).where(transaction_tag.c.transaction_id.in_(ids))):
        manual[tid].add(tag)
    by_merchant = defaultdict(set)
    if merchant_ids:
        for mid, tag in db.execute(select(merchant_tag.c.merchant_id, merchant_tag.c.tag_id).where(merchant_tag.c.merchant_id.in_(merchant_ids))):
            by_merchant[mid].add(tag)
    by_rule = defaultdict(set)
    if rule_ids:
        for rid, tag in db.execute(select(rule_tag.c.rule_id, rule_tag.c.tag_id).where(rule_tag.c.rule_id.in_(rule_ids))):
            by_rule[rid].add(tag)
    tags = {tg.id: tg for tg in db.scalars(select(Tag))}
    out: dict[int, list[dict]] = {}
    for t in txns:
        seen: dict[int, str] = {}
        for tag in manual[t.id]:
            seen[tag] = "manuel"
        for tag in by_rule.get(t.rule_id, ()):
            seen.setdefault(tag, "service")
        for tag in by_merchant.get(t.merchant_id, ()):
            seen.setdefault(tag, "vendeur")
        out[t.id] = [
            {"id": tag, "name": tags[tag].name, "color": tags[tag].color, "source": src}
            for tag, src in sorted(seen.items(), key=lambda kv: tags[kv[0]].name.lower())
            if tag in tags
        ]
    return out


def bulk_tags(db: Session, txns: list[Transaction], add: list[int], remove: list[int]) -> dict:
    """Ajoute / retire des étiquettes posées à la main. Une étiquette héritée (vendeur, service) ne peut
    pas être retirée d'une seule opération : on le signale."""
    add_tags = list(db.scalars(select(Tag).where(Tag.id.in_(add or []))))
    remove_set = set(remove or [])
    changed = 0
    for t in txns:
        before = {tg.id for tg in t.tags}
        current = [tg for tg in t.tags if tg.id not in remove_set] + [tg for tg in add_tags if tg.id not in before]
        if {tg.id for tg in current} != before:
            t.tags = current
            changed += 1
    db.flush()
    inherited = 0
    if remove_set:
        eff = effective_tags(db, txns)
        inherited = sum(1 for t in txns for tg in eff[t.id] if tg["id"] in remove_set)
    return {"updated": changed, "inherited_kept": inherited}
