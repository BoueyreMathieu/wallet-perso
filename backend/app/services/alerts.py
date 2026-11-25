"""Alertes : ce qui mérite ton attention maintenant (affichées dans l'appli, et en notifications sur le téléphone).

Chaque alerte a une clé stable : le téléphone ne notifie qu'une fois chaque clé (un budget dépassé ce mois-ci ne
sonne pas toutes les 30 minutes). Les alertes sont recalculées à la demande, rien n'est stocké côté serveur, à part
les réglages (types activés) et la date de départ du contrôle de solde quand tu as vérifié un écart.

Types (activables un par un dans Paramètres › Notifications) :
- budgets : budget presque atteint ou dépassé (budget global compris) ;
- tresorerie : solde prévu sous zéro dans les 7 jours, grosse dépense inhabituelle ;
- banque : synchro en échec, autorisation bancaire qui expire, écart entre le solde de la banque et les opérations ;
- revenus : salaire / revenu régulier arrivé, nouvel abonnement repéré, hausse de prix, échéance en retard ;
- contrats : date limite de résiliation qui approche (30 jours, puis 7 jours avant) ;
- autres : opérations à catégoriser, objectif d'épargne atteint, livret au plafond, sauvegarde automatique en échec.
Les projets (étiquettes) avec un budget alertent avec les budgets.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.balance_check import Gap, balance_gap
from app.models import Account, BalanceSnapshot, Category, Connection, RecurringSeries, Transaction
from app.seed import get_meta, set_meta

log = logging.getLogger("wallet.alertes")

KINDS: dict[str, str] = {
    "budgets": "Budgets",
    "tresorerie": "Trésorerie",
    "banque": "Synchro et banque",
    "revenus": "Revenus et abonnements",
    "contrats": "Échéances de contrats",
    "autres": "Autres rappels",
}
DETAILS: dict[str, str] = {
    "budgets": "Budget presque atteint (seuil d'alerte) ou dépassé, budget global compris.",
    "tresorerie": "Solde prévu sous zéro dans les 7 prochains jours ; grosse dépense inhabituelle.",
    "banque": "Synchro en échec, autorisation bancaire qui expire, écart entre le solde de la banque et tes opérations.",
    "revenus": "Salaire ou revenu régulier arrivé, nouvel abonnement repéré, hausse de prix, échéance en retard.",
    "contrats": "Date limite pour résilier un contrat (assurance, box, énergie…) : 30 jours puis 7 jours avant.",
    "autres": "Opérations à catégoriser, objectif d'épargne atteint, livret au plafond, sauvegarde automatique en échec.",
}
SETTINGS_KEY = "notify_kinds"
CHECK_FROM_KEY = "balance_check_from"
CHECK_DAYS = 60  # période contrôlée pour l'écart de solde
EXPIRY_WARN_DAYS = 14


@dataclass
class Alert:
    key: str
    kind: str
    level: str  # info | warning | danger
    title: str
    body: str
    link: str  # page de l'appli
    deep: str  # lien walletperso:// ouvert par la notification (voir DEEP_LINKS dans App.tsx)


# --- Réglages ------------------------------------------------------------------------------------


def notify_settings(db: Session) -> dict[str, bool]:
    try:
        saved = json.loads(get_meta(db, SETTINGS_KEY, "{}") or "{}")
    except ValueError:
        saved = {}
    return {k: bool(saved.get(k, True)) for k in KINDS}


def set_notify_settings(db: Session, values: dict[str, bool]) -> dict[str, bool]:
    current = notify_settings(db)
    current.update({k: bool(v) for k, v in values.items() if k in KINDS})
    set_meta(db, SETTINGS_KEY, json.dumps(current))
    return current


# --- Contrôle de cohérence des soldes ----------------------------------------------------------------


def _check_from(db: Session) -> dict[str, str]:
    try:
        return json.loads(get_meta(db, CHECK_FROM_KEY, "{}") or "{}")
    except ValueError:
        return {}


def account_gap(db: Session, acc: Account, today: date) -> Gap | None:
    """Écart entre les soldes donnés par la banque et les opérations, pour un compte synchronisé (hors PayPal, qui ne
    transmet pas ses approvisionnements). None : rien à contrôler."""
    if acc.connection_id is None or acc.type == "paypal" or acc.is_archived:
        return None
    from app.services.balances import SPLIT_SOURCE

    since = today - timedelta(days=CHECK_DAYS)
    checked = _check_from(db).get(str(acc.id))
    if checked:
        try:
            since = max(since, date.fromisoformat(checked))
        except ValueError:
            pass
    snaps = [(d, v) for d, v in db.execute(
        select(BalanceSnapshot.date, BalanceSnapshot.balance_cents).where(BalanceSnapshot.account_id == acc.id, BalanceSnapshot.date >= since)
    )]
    if len(snaps) < 2:
        return None
    ops = [(d, a) for d, a in db.execute(
        select(Transaction.booked_at, Transaction.amount_cents).where(
            Transaction.account_id == acc.id, Transaction.source != SPLIT_SOURCE, Transaction.booked_at >= since - timedelta(days=2)
        )
    )]
    return balance_gap(snaps, ops, since)


def mark_balance_checked(db: Session, acc: Account) -> None:
    """« J'ai vérifié » : le contrôle repart du dernier solde connu."""
    last = db.scalar(select(func.max(BalanceSnapshot.date)).where(BalanceSnapshot.account_id == acc.id))
    data = _check_from(db)
    data[str(acc.id)] = (last or date.today()).isoformat()
    set_meta(db, CHECK_FROM_KEY, json.dumps(data))


# --- Alertes -------------------------------------------------------------------------------------


def _euros(cents: int) -> str:
    s = f"{abs(cents) / 100:,.2f}".replace(",", " ").replace(".", ",")
    return f"{'-' if cents < 0 else ''}{s} €"


def _day(d: date) -> str:
    return d.strftime("%d/%m")


def _paths(db: Session) -> dict[int, str]:
    rows = db.execute(select(Category.id, Category.parent_id, Category.name)).all()
    names = {r.id: r.name for r in rows}
    return {r.id: (f"{names.get(r.parent_id)} › {r.name}" if r.parent_id else r.name) for r in rows}


def _budgets(db: Session, today: date) -> list[Alert]:
    from app.services.planning import budgets_overview

    ov = budgets_overview(db, today, today)
    month, paths, out = ov["month"], _paths(db), []
    items = list(ov["items"])
    if ov.get("global"):
        items.append({**ov["global"], "category_id": None, "alert_threshold_pct": 80})
    for it in items:
        if it["level"] == "ok":
            continue
        name = "global" if it["category_id"] is None else f"« {paths.get(it['category_id'], '?')} »"
        spent, budget = it["spent_cents"], it["budget_cents"]
        if it["level"] == "depasse":
            title, body, level = f"🎯 Budget {name} dépassé", f"{_euros(spent)} dépensés sur {_euros(budget)} ce mois-ci.", "danger"
        else:
            title, level = f"🎯 Budget {name} bientôt atteint", "warning"
            body = f"{_euros(spent)} sur {_euros(budget)}"
            if it.get("projected_cents", 0) > budget:
                body += f", fin de mois prévue vers {_euros(it['projected_cents'])}"
            body += "."
        cid = it["category_id"] if it["category_id"] is not None else "global"
        out.append(Alert(f"budget:{cid}:{month}:{it['level']}", "budgets", level, title, body, "/prevoir/budgets", "budgets"))
    # Projets suivis par étiquette, avec un budget total.
    from app.services.projects import projects_list

    for p in projects_list(db, today):
        if p["budget_cents"] and p["level"] != "ok":
            over = p["level"] == "depasse"
            out.append(Alert(f"projet:{p['id']}:{p['level']}", "budgets", "danger" if over else "warning",
                             f"🧳 Projet « {p['name']} » {'au-delà du budget' if over else 'bientôt au budget'}",
                             f"{_euros(p['net_cents'])} sur {_euros(p['budget_cents'])}.", "/prevoir/projets", "prevoir"))
    return out


def _treasury(db: Session, today: date) -> list[Alert]:
    from app.services.planning import forecast

    out = []
    fc = forecast(db, today, today + timedelta(days=7))
    low = fc["lowest"]
    if low["balance_cents"] < 0:
        out.append(Alert(
            f"tresorerie:negatif:{low['date']}", "tresorerie", "danger", "⚠️ Solde prévu sous zéro",
            f"Vers le {_day(low['date'])}, tes comptes du quotidien passeraient à {_euros(low['balance_cents'])}.", "/prevoir", "prevoir",
        ))
    # Grosse dépense inhabituelle (3 derniers jours) : au moins 100 € et 2× la plus grosse de sa catégorie sur 90 jours.
    recent = db.execute(
        select(Transaction.id, Transaction.amount_cents, Transaction.category_id, Transaction.booked_at, Transaction.raw_label, Transaction.merchant_id)
        .where(Transaction.booked_at >= today - timedelta(days=3), Transaction.counted.is_(True), Transaction.is_transfer.is_(False),
               Transaction.amount_cents <= -10000, Transaction.recurring_id.is_(None))
    ).all()
    if recent:
        from app.models import Merchant

        names = dict(db.execute(select(Merchant.id, Merchant.name)).all())
        for t in recent:
            q = select(func.min(Transaction.amount_cents)).where(
                Transaction.booked_at >= today - timedelta(days=93), Transaction.booked_at < today - timedelta(days=3),
                Transaction.counted.is_(True), Transaction.is_transfer.is_(False), Transaction.amount_cents < 0,
            )
            q = q.where(Transaction.category_id == t.category_id) if t.category_id is not None else q.where(Transaction.category_id.is_(None))
            biggest = db.scalar(q)
            usual = -biggest if biggest is not None else 0
            if -t.amount_cents >= max(2 * usual, 10000 if t.category_id is not None else 30000):
                who = names.get(t.merchant_id) or t.raw_label.split(" | ")[0][:40]
                out.append(Alert(f"depense:{t.id}", "tresorerie", "warning", f"💸 Grosse dépense : {who}",
                                 f"{_euros(t.amount_cents)} le {_day(t.booked_at)}, bien plus que d'habitude dans cette catégorie.",
                                 "/operations", "operations"))
    return out


def _bank(db: Session, today: date) -> list[Alert]:
    out = []
    now = datetime.now(timezone.utc)
    for c in db.scalars(select(Connection)):
        if c.status == "en_attente":
            continue
        if c.status in ("expire", "erreur"):
            what = "a expiré" if c.status == "expire" else "est en erreur"
            out.append(Alert(f"connexion:{c.id}:{c.status}", "banque", "danger", f"🔑 Connexion {c.label} : à renouveler",
                             f"L'autorisation {what} : la synchro est arrêtée. Renouvelle-la dans Comptes.", "/comptes", "comptes"))
        elif c.last_error:
            at = c.last_error_at.date() if c.last_error_at else today
            out.append(Alert(f"synchro:{c.id}:{at}", "banque", "warning", f"🔄 Synchro {c.label} en échec", c.last_error, "/comptes", "comptes"))
        if c.consent_expires_at and c.status == "actif":
            exp = c.consent_expires_at if c.consent_expires_at.tzinfo else c.consent_expires_at.replace(tzinfo=timezone.utc)
            left = (exp - now).days
            if left <= EXPIRY_WARN_DAYS:
                stage = 0 if left <= 0 else 3 if left <= 3 else EXPIRY_WARN_DAYS
                when = "aujourd'hui" if left <= 0 else f"dans {left} jour{'s' if left > 1 else ''}"
                out.append(Alert(f"expiration:{c.id}:{exp.date()}:{stage}", "banque", "danger" if left <= 3 else "warning",
                                 f"🔑 Autorisation {c.label} : expire {when}",
                                 f"Renouvelle-la (Comptes › {c.label} › Renouveler) pour que la synchro continue.", "/comptes", "comptes"))
    for acc in db.scalars(select(Account).where(Account.connection_id.is_not(None), Account.is_archived.is_(False))):
        g = account_gap(db, acc, today)
        if g is not None and g.gap_cents != 0:
            out.append(Alert(f"ecart:{acc.id}:{g.until}:{g.gap_cents}", "banque", "warning", f"🧮 Écart de solde : {acc.name}",
                             f"Le solde de la banque et tes opérations diffèrent de {_euros(g.gap_cents)} depuis le {_day(g.since)} : "
                             "une opération manque ou est en double ?", "/comptes", "comptes"))
    return out


def _income_and_subscriptions(db: Session, today: date) -> list[Alert]:
    from app.recurrence import grace_days

    out = []
    series = {s.id: s for s in db.scalars(select(RecurringSeries))}
    arrived = db.execute(
        select(Transaction.id, Transaction.amount_cents, Transaction.recurring_id, Transaction.booked_at)
        .where(Transaction.booked_at >= today - timedelta(days=3), Transaction.amount_cents >= 20000, Transaction.recurring_id.is_not(None),
               Transaction.counted.is_(True), Transaction.is_transfer.is_(False))
    ).all()
    for t in arrived:
        s = series.get(t.recurring_id)
        if s is not None and s.expected_amount_cents > 0:
            out.append(Alert(f"revenu:{t.id}", "revenus", "info", f"💶 {s.label} arrivé", f"+{_euros(t.amount_cents)} le {_day(t.booked_at)}.",
                             "/operations", "operations"))
    for s in series.values():
        if s.is_transfer or s.expected_amount_cents >= 0:
            continue
        if s.status == "suggere" and s.source == "auto":
            out.append(Alert(f"abonnement:{s.id}", "revenus", "info", f"🔁 Nouveau prélèvement régulier : {s.label}",
                             f"{_euros(s.expected_amount_cents)} ({s.frequency}). À confirmer dans Prévoir › Récurrents.",
                             "/prevoir/recurrents", "prevoir"))
        if s.status not in ("actif", "suggere"):
            continue
        if (s.price_changed_on and s.previous_amount_cents is not None and abs(s.expected_amount_cents) > abs(s.previous_amount_cents)
                and (today - s.price_changed_on).days <= 45):
            out.append(Alert(f"hausse:{s.id}:{s.price_changed_on}", "revenus", "warning", f"📈 Hausse de prix : {s.label}",
                             f"{_euros(s.previous_amount_cents)} → {_euros(s.expected_amount_cents)} depuis le {_day(s.price_changed_on)}.",
                             "/prevoir/recurrents", "prevoir"))
        if s.status == "actif" and s.next_expected_date and s.frequency:
            late = (today - s.next_expected_date).days
            try:
                grace = grace_days(s.frequency)
            except KeyError:
                grace = 7
            if 3 <= late <= grace:
                out.append(Alert(f"retard:{s.id}:{s.next_expected_date}", "revenus", "info", f"⏰ Échéance en retard : {s.label}",
                                 f"Attendue le {_day(s.next_expected_date)} ({_euros(s.expected_amount_cents)}), toujours pas vue.",
                                 "/prevoir/recurrents", "prevoir"))
    return out


def _contracts(db: Session, today: date) -> list[Alert]:
    from app.services.projects import contracts_list

    out = []
    for c in contracts_list(db, today):
        days = c["days_to_deadline"]
        if c["state"] == "termine" or days < 0 or days > 30:
            continue
        stage = 7 if days <= 7 else 30
        when = "aujourd'hui" if days == 0 else f"dans {days} jour{'s' if days > 1 else ''}"
        renew = "se reconduit" if c["renew_months"] else "arrive à échéance"
        out.append(Alert(f"contrat:{c['id']}:{c['renewal_date']}:{stage}", "contrats", "warning" if days <= 7 else "info",
                         f"📄 {c['label']} : résiliation possible jusqu'au {_day(c['deadline'])}",
                         f"Le contrat {renew} le {_day(c['renewal_date'])} ; date limite {when}.", "/prevoir/contrats", "prevoir"))
    return out


def _others(db: Session, today: date) -> list[Alert]:
    out = []
    todo = db.scalar(select(func.count(Transaction.id)).where(
        Transaction.booked_at >= today - timedelta(days=30), Transaction.category_id.is_(None), Transaction.counted.is_(True)
    )) or 0
    if todo >= 10:
        week = today.isocalendar()
        out.append(Alert(f"a_categoriser:{week[0]}-{week[1]}", "autres", "info", f"🗂️ {todo} opérations à catégoriser",
                         "Sur les 30 derniers jours : quelques secondes pour des statistiques justes.", "/operations?a_categoriser=1", "categoriser"))
    from app.services.goals import goals_view

    for g in goals_view(db, today):
        if g.get("status") == "atteint":
            out.append(Alert(f"objectif:{g['id']}:atteint", "autres", "info", f"🏁 Objectif atteint : {g['name']}",
                             f"{_euros(g['target_cents'])} mis de côté. Bravo !", "/prevoir/objectifs", "prevoir"))
    from app.services.wealth import overview

    for acc in overview(db, today)["accounts"]:
        d = acc["details"]
        if d.get("at_ceiling"):
            out.append(Alert(f"plafond:{acc['id']}:{today.year}", "autres", "info", f"🐷 {acc['name']} au plafond",
                             "Les versements au-delà ne rapportent plus : pense à un autre placement.", "/patrimoine", "home"))
    from app.services.backup_status import backup_status

    b = backup_status(db)
    if b.get("warning") and b.get("last_error_at"):
        out.append(Alert(f"sauvegarde:{b['last_error_at'].date()}", "autres", "warning", "💾 Sauvegarde en échec", b["warning"],
                         "/parametres", "home"))
    return out


SECTIONS = {"budgets": _budgets, "tresorerie": _treasury, "banque": _bank, "revenus": _income_and_subscriptions, "contrats": _contracts,
            "autres": _others}


def build_alerts(db: Session, today: date, only_enabled: bool = True) -> list[dict]:
    """Toutes les alertes du moment (types activés seulement, sauf only_enabled=False). Une partie en erreur n'empêche
    jamais les autres."""
    enabled = notify_settings(db)
    out: list[Alert] = []
    for kind, fn in SECTIONS.items():
        if only_enabled and not enabled[kind]:
            continue
        try:
            with db.begin_nested():
                out.extend(fn(db, today))
        except Exception:  # noqa: BLE001
            log.exception("Alertes « %s » impossibles à calculer", kind)
    order = {"danger": 0, "warning": 1, "info": 2}
    out.sort(key=lambda a: (order.get(a.level, 3), list(KINDS).index(a.kind)))
    return [asdict(a) for a in out]
