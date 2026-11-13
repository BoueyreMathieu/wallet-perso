"""Connexions bancaires (Enable Banking) : autorisation, association des comptes, synchronisation."""

import hmac
import logging
import secrets as pysecrets
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.connectors import enable_banking as eb
from app.models import Account, Connection
from app.security import decrypt_secrets, encrypt_secrets
from app.services.importing import ImportResult, ingest

log = logging.getLogger("wallet.sync")

PROVIDER = "enable_banking"
CONSENT_SECONDS = 180 * 24 * 3600  # maximum courant ; chaque banque annonce le sien (maximum_consent_validity)
CONSENT_MARGIN = 3600  # marge d'une heure : demander pile le maximum est refusé (décalage d'horloge)
OVERLAP_DAYS = 7  # on refait les derniers jours à chaque synchro (opérations comptabilisées en retard)


class SyncError(RuntimeError):
    pass


# --- Configuration / client ------------------------------------------------------------


def config_status() -> dict:
    s = get_settings()
    key = eb.find_private_key(s.secrets_dir, s.enable_banking_app_id, s.enable_banking_key_path)
    return {
        "app_id_set": bool(s.enable_banking_app_id),
        "key_found": key is not None,
        "configured": bool(s.enable_banking_app_id) and key is not None,
        "redirect_url": s.enable_banking_redirect_url,
        "sync_interval_hours": s.sync_interval_hours,
    }


def get_client() -> eb.EnableBankingClient:
    """Point d'entrée unique (remplacé par un faux client dans les tests)."""
    s = get_settings()
    key = eb.find_private_key(s.secrets_dir, s.enable_banking_app_id, s.enable_banking_key_path)
    if not s.enable_banking_app_id or key is None:
        raise SyncError(
            "Enable Banking n'est pas configuré : renseigne ENABLE_BANKING_APP_ID dans .env et place la clé .pem dans secrets/."
        )
    return eb.EnableBankingClient(s.enable_banking_app_id, key.read_bytes(), s.enable_banking_api)


def _secrets(c: Connection) -> dict:
    return decrypt_secrets(c.secrets_encrypted) if c.secrets_encrypted else {}


def _save(c: Connection, data: dict) -> None:
    c.secrets_encrypted = encrypt_secrets(data)


def public_accounts(c: Connection) -> list[dict]:
    """Comptes de la connexion, sans identifiant sensible (IBAN masqué)."""
    out = []
    for a in _secrets(c).get("accounts", []):
        iban = a.get("iban") or ""
        out.append(
            {
                "uid": a["uid"],
                "name": a.get("name"),
                "currency": a.get("currency"),
                "iban_end": iban[-4:] if iban else None,
                "account_id": a.get("account_id"),
            }
        )
    return out


# --- Autorisation ----------------------------------------------------------------------


def start(db: Session, aspsp_name: str, country: str, connection_id: int | None = None) -> str:
    """Prépare l'autorisation et renvoie l'URL de la banque où l'utilisateur doit se connecter."""
    client = get_client()
    c = db.get(Connection, connection_id) if connection_id else None
    if c is None:
        # Une tentative précédente restée « en attente » pour la même banque est réutilisée.
        c = db.scalar(
            select(Connection).where(
                Connection.provider == PROVIDER, Connection.label == aspsp_name, Connection.status == "en_attente"
            )
        )
    if c is None:
        c = Connection(provider=PROVIDER, label=aspsp_name, status="en_attente")
        db.add(c)
    state = pysecrets.token_urlsafe(24)
    data = _secrets(c)
    data.update({"state": state, "state_at": datetime.now(timezone.utc).isoformat(), "aspsp": {"name": aspsp_name, "country": country}})
    _save(c, data)
    db.flush()
    res = client.start_auth(aspsp_name, country, state, get_settings().enable_banking_redirect_url, consent_seconds(client, aspsp_name, country))
    db.commit()
    return res["url"]


def consent_seconds(client: eb.EnableBankingClient, aspsp_name: str, country: str) -> int:
    """Durée d'autorisation demandée : le maximum accepté par la banque, moins une marge."""
    maximum = CONSENT_SECONDS
    try:
        for b in client.aspsps(country):
            if b.get("name") == aspsp_name and b.get("maximum_consent_validity"):
                maximum = min(maximum, int(b["maximum_consent_validity"]))
                break
    except eb.EnableBankingError:
        pass
    return max(maximum - CONSENT_MARGIN, 3600)


STATE_MAX_AGE = timedelta(hours=1)


def _state_fresh(data: dict) -> bool:
    """Un retour de banque n'est accepté que dans l'heure qui suit le départ."""
    started = data.get("state_at")
    if not started:
        return True  # autorisation lancée avant cette version
    try:
        at = datetime.fromisoformat(started)
    except ValueError:
        return False
    return datetime.now(timezone.utc) - at <= STATE_MAX_AGE


def finish(db: Session, code: str, state: str) -> Connection:
    """Retour de la banque : on échange le code contre une session et on récupère la liste des comptes."""
    target = None
    for c in db.scalars(select(Connection).where(Connection.provider == PROVIDER)):
        expected = _secrets(c).get("state")
        if expected and hmac.compare_digest(str(expected), state):
            target = c
            break
    if target is None or not _state_fresh(_secrets(target)):
        raise SyncError("Retour de banque inconnu ou expiré : relance la connexion depuis l'appli.")
    client = get_client()
    session = client.create_session(code)
    data = _secrets(target)
    old_accounts = {a.get("identification_hash") or a["uid"]: a for a in data.get("accounts", [])}
    accounts = []
    for a in eb.session_accounts(session):
        previous = old_accounts.get(a.get("identification_hash") or a["uid"], {})
        a["account_id"] = previous.get("account_id") or _guess_account(db, a)
        accounts.append(a)
    old_session = data.get("session_id")
    data.update({"session_id": session["session_id"], "accounts": accounts})
    data.pop("state", None)
    data.pop("state_at", None)
    _save(target, data)
    valid = (session.get("access") or {}).get("valid_until")
    target.consent_expires_at = datetime.fromisoformat(valid.replace("Z", "+00:00")) if valid else None
    target.status = "actif"
    db.commit()
    if old_session and old_session != session["session_id"]:
        try:
            client.delete_session(old_session)
        except eb.EnableBankingError:
            pass
    return target


def _guess_account(db: Session, a: dict) -> int | None:
    """Associe automatiquement un compte de l'appli dont le n° (import CSV) figure dans l'IBAN."""
    iban = a.get("iban") or ""
    if not iban:
        return None
    for acc in db.scalars(select(Account).where(Account.external_id.is_not(None))):
        if acc.external_id and acc.external_id.isdigit() and len(acc.external_id) >= 8 and acc.external_id in iban:
            return acc.id
    return None


def map_accounts(db: Session, c: Connection, mapping: dict[str, int | None | str]) -> None:
    """mapping : uid → id de compte local, « new » (créer un compte) ou None (ignorer)."""
    data = _secrets(c)
    for a in data.get("accounts", []):
        if a["uid"] not in mapping:
            continue
        target = mapping[a["uid"]]
        if target == "new":
            acc = Account(name=a.get("name") or "Compte", type="courant", institution=c.label, connection_id=c.id)
            db.add(acc)
            db.flush()
            a["account_id"] = acc.id
        elif target is None:
            a["account_id"] = None
        else:
            if db.get(Account, int(target)) is None:
                raise SyncError("Compte inconnu")
            a["account_id"] = int(target)
    _save(c, data)
    db.commit()


# --- Synchronisation -------------------------------------------------------------------


def sync_connection(db: Session, c: Connection, client: eb.EnableBankingClient | None = None) -> list[ImportResult]:
    data = _secrets(c)
    if not data.get("session_id"):
        raise SyncError("Connexion pas encore autorisée.")
    if c.consent_expires_at and c.consent_expires_at.replace(tzinfo=c.consent_expires_at.tzinfo or timezone.utc) < datetime.now(timezone.utc):
        c.status = "expire"
        db.commit()
        raise SyncError("L'autorisation de la banque a expiré : reconnecte-toi.")
    client = client or get_client()
    since = (c.last_sync_at - timedelta(days=OVERLAP_DAYS)).date() if c.last_sync_at else None
    results = []
    for a in data.get("accounts", []):
        if not a.get("account_id"):
            continue
        acc = db.get(Account, a["account_id"])
        if acc is None:
            continue
        txs = client.transactions(a["uid"], since)
        balances = client.balances(a["uid"])
        stmt = eb.to_statement(txs, balances, a.get("name") or c.label)
        if acc.connection_id is None:
            acc.connection_id = c.id
        results.append(ingest(db, stmt, acc.id, None, c.label))
    c.last_sync_at = datetime.now(timezone.utc)
    c.status = "actif"
    c.last_error = None
    c.last_error_at = None
    db.commit()
    return results


def record_error(db: Session, connection_id: int, e: Exception) -> None:
    """Garde la dernière erreur (affichée dans Connexions) ; autorisation refusée : la connexion passe « en erreur »."""
    c = db.get(Connection, connection_id)
    if c is None:
        return
    if isinstance(e, eb.EnableBankingError) and e.status == 429:
        c.last_error = "La banque limite le nombre de synchros par jour : nouvel essai plus tard."
    else:
        c.last_error = str(e)[:300] or e.__class__.__name__
    c.last_error_at = datetime.now(timezone.utc)
    if isinstance(e, eb.EnableBankingError) and e.status in (401, 403):
        c.status = "erreur"
    db.commit()


def _aware(d: datetime | None) -> datetime | None:
    return d.replace(tzinfo=timezone.utc) if d is not None and d.tzinfo is None else d


# Une seule synchro à la fois (boucle automatique, ouverture de l'appli, bouton).
_RUNNING = threading.Lock()


def sync_stale(db: Session, max_age: timedelta) -> dict:
    """Synchronise les connexions actives dont la dernière synchro date de plus de `max_age`, sans s'arrêter sur une
    erreur. Les banques limitent souvent les synchros sans l'utilisateur (souvent 4 par jour et par compte)."""
    if not _RUNNING.acquire(blocking=False):
        return {"running": True, "synced": [], "imported": 0, "errors": []}
    try:
        now = datetime.now(timezone.utc)
        out = {"running": False, "synced": [], "imported": 0, "errors": []}
        for c in db.scalars(select(Connection).where(Connection.provider == PROVIDER, Connection.status == "actif")).all():
            last = _aware(c.last_sync_at)
            if last is not None and now - last < max_age:
                continue
            cid, label = c.id, c.label
            try:
                results = sync_connection(db, c)
                out["synced"].append(label)
                out["imported"] += sum(r.imported for r in results)
            except Exception as e:  # noqa: BLE001 - on note l'erreur et on passe à la suivante
                db.rollback()
                log.warning("Synchro %s impossible : %s", label, e)
                record_error(db, cid, e)
                out["errors"].append({"label": label, "error": db.get(Connection, cid).last_error if db.get(Connection, cid) else str(e)})
        return out
    finally:
        _RUNNING.release()


def sync_all(db: Session) -> None:
    """Toutes les connexions actives, quelle que soit la date de leur dernière synchro."""
    sync_stale(db, timedelta(0))


def disconnect(db: Session, c: Connection) -> None:
    sid = _secrets(c).get("session_id")
    if sid:
        try:
            get_client().delete_session(sid)
        except (eb.EnableBankingError, SyncError):
            pass
    for acc in db.scalars(select(Account).where(Account.connection_id == c.id)):
        acc.connection_id = None
    db.delete(c)
    db.commit()
