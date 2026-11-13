"""Connecteur Enable Banking (accès DSP2 aux comptes bancaires, dont le Crédit Agricole).

Doc : https://enablebanking.com/docs/api/reference/
- Authentification : JWT RS256 signé avec la clé privée de l'application (kid = id de l'application).
- Flux : GET /aspsps → POST /auth (URL de la banque) → retour avec ?code= → POST /sessions
  → comptes → GET /accounts/{uid}/transactions (paginé) et /balances.

La signature JWT n'utilise que `cryptography` (déjà présent pour le chiffrement des secrets).
"""

from __future__ import annotations

import base64
import json
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from app.connectors.base import RawTransaction, Statement, stable_hash
from app.importers.credit_agricole import smart_title

JWT_LIFETIME = 3600  # 1 h (maximum autorisé : 24 h)
BALANCE_PREFERENCE = ("CLBD", "ITBD", "XPCD", "ITAV", "CLAV", "OPBD")


class EnableBankingError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_jwt(app_id: str, private_key_pem: bytes, now: int | None = None) -> str:
    now = int(now if now is not None else time.time())
    header = {"typ": "JWT", "alg": "RS256", "kid": app_id}
    body = {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + JWT_LIFETIME}
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(body, separators=(',', ':')).encode())}"
    key = serialization.load_pem_private_key(private_key_pem, password=None)
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(signature)}"


def find_private_key(secrets_dir: str, app_id: str, explicit_path: str = "") -> Path | None:
    if explicit_path:
        p = Path(explicit_path)
        return p if p.is_file() else None
    d = Path(secrets_dir)
    if not d.is_dir():
        return None
    named = d / f"{app_id}.pem"
    if app_id and named.is_file():
        return named
    pems = sorted(d.glob("*.pem"))
    return pems[0] if len(pems) == 1 else None


class EnableBankingClient:
    def __init__(self, app_id: str, private_key_pem: bytes, api_base: str):
        self.app_id = app_id
        self.key = private_key_pem
        self.api = api_base.rstrip("/")
        self._token: tuple[str, float] | None = None

    def _auth_header(self) -> dict:
        if self._token is None or self._token[1] < time.time() + 60:
            self._token = (make_jwt(self.app_id, self.key), time.time() + JWT_LIFETIME)
        return {"Authorization": f"Bearer {self._token[0]}"}

    def _request(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        import httpx  # importé ici : inutile pour les tests qui remplacent cette méthode

        r = httpx.request(method, f"{self.api}{path}", params=params, json=body, headers=self._auth_header(), timeout=60)
        if r.status_code >= 400:
            try:
                detail = r.json()
                msg = detail.get("message") or detail.get("error") or str(detail)
            except ValueError:
                msg = r.text[:300]
            raise EnableBankingError(f"Enable Banking {r.status_code} : {msg}", r.status_code)
        return r.json() if r.content else {}

    # --- API ------------------------------------------------------------------

    def aspsps(self, country: str = "FR") -> list[dict]:
        return self._request("GET", "/aspsps", params={"country": country, "psu_type": "personal"}).get("aspsps", [])

    def start_auth(self, aspsp_name: str, country: str, state: str, redirect_url: str, valid_seconds: int) -> dict:
        valid_until = (datetime.now(timezone.utc) + timedelta(seconds=valid_seconds)).isoformat()
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": aspsp_name, "country": country},
            "state": state,
            "redirect_url": redirect_url,
            "psu_type": "personal",
        }
        return self._request("POST", "/auth", body=body)

    def create_session(self, code: str) -> dict:
        return self._request("POST", "/sessions", body={"code": code})

    def delete_session(self, session_id: str) -> None:
        self._request("DELETE", f"/sessions/{session_id}")

    def transactions(self, account_uid: str, date_from: date | None, status: str | None = None) -> list[dict]:
        """Toutes les pages. Sans date : stratégie « longest » (le plus d'historique possible).

        Passé la première heure de l'autorisation, beaucoup de banques (dont le Crédit Agricole) n'acceptent plus
        qu'environ 90 jours d'historique (« Wrong transactions period requested ») : on réessaie alors sur une
        période plus courte (89 jours, puis 30)."""
        if date_from is not None:
            last_error: EnableBankingError | None = None
            for days in (None, 89, 30):
                start = date_from if days is None else max(date_from, date.today() - timedelta(days=days))
                if days is not None and start == date_from:
                    continue  # déjà essayé avec cette date
                try:
                    return self._all_pages(account_uid, {"date_from": start.isoformat(), **({"transaction_status": status} if status else {})})
                except EnableBankingError as e:
                    if e.status != 422 or "period" not in str(e).lower():
                        raise
                    last_error = e
            assert last_error is not None
            raise last_error
        return self._all_pages(account_uid, {"strategy": "longest", **({"transaction_status": status} if status else {})})

    def _all_pages(self, account_uid: str, params: dict) -> list[dict]:
        out: list[dict] = []
        for _ in range(500):  # garde-fou
            page = self._request("GET", f"/accounts/{account_uid}/transactions", params=params)
            out.extend(page.get("transactions") or [])
            key = page.get("continuation_key")
            if not key:
                break
            params = {**params, "continuation_key": key}
        return out

    def balances(self, account_uid: str) -> list[dict]:
        return self._request("GET", f"/accounts/{account_uid}/balances").get("balances", [])


# --- Conversion au format commun ------------------------------------------------------


def session_accounts(session: dict) -> list[dict]:
    """Normalise la liste des comptes renvoyée par POST /sessions."""
    accounts = session.get("accounts") or []
    data = session.get("accounts_data") or []
    out = []
    for i, a in enumerate(accounts):
        if isinstance(a, str):  # ancien format : liste d'uid + accounts_data à côté
            a = {"uid": a, **(data[i] if i < len(data) else {})}
        iban = ((a.get("account_id") or {}).get("iban") or "").replace(" ", "")
        out.append(
            {
                "uid": a.get("uid"),
                "identification_hash": a.get("identification_hash"),
                "name": a.get("name") or a.get("product") or "Compte",
                "currency": a.get("currency") or "EUR",
                "iban": iban,
            }
        )
    return out


def _cents(amount: str | float | int) -> int:
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1")))


def pick_balance(balances: list[dict]) -> tuple[int, date] | None:
    if not balances:
        return None
    ranked = sorted(
        balances,
        key=lambda b: BALANCE_PREFERENCE.index(b.get("balance_type")) if b.get("balance_type") in BALANCE_PREFERENCE else 99,
    )
    b = ranked[0]
    amount = (b.get("balance_amount") or {}).get("amount")
    if amount is None:
        return None
    ref = b.get("reference_date") or b.get("last_change_date") or date.today().isoformat()
    return _cents(amount), date.fromisoformat(str(ref)[:10])


def to_statement(transactions: list[dict], balances: list[dict], label: str) -> Statement:
    """Opérations Enable Banking → Statement.
    - comptabilisées (BOOK) → opérations ;
    - « à venir » (PDNG : paiement par carte pas encore débité…) → `pending`, gardées à part et remplacées
      à chaque synchro : leur identifiant change souvent au moment où elles sont comptabilisées."""
    seen: Counter = Counter()
    txs: list[RawTransaction] = []
    pending: list[RawTransaction] = []
    for t in transactions:
        status = (t.get("status") or "BOOK").upper()
        if status not in ("BOOK", "PDNG"):
            continue
        amount = _cents((t.get("transaction_amount") or {}).get("amount", "0"))
        if (t.get("credit_debit_indicator") or "").upper() == "DBIT":
            amount = -abs(amount)
        elif (t.get("credit_debit_indicator") or "").upper() == "CRDT":
            amount = abs(amount)
        if status == "PDNG":
            day = str(t.get("transaction_date") or t.get("value_date") or t.get("booking_date") or date.today().isoformat())[:10]
        else:
            day = str(t.get("booking_date") or t.get("value_date") or t.get("transaction_date"))[:10]
        booked = date.fromisoformat(day)
        info = [str(x).strip() for x in (t.get("remittance_information") or []) if str(x).strip()]
        party = (t.get("creditor") if amount < 0 else t.get("debtor")) or {}
        party_name = (party.get("name") or "").strip() or None
        raw_label = " | ".join(info) or party_name or "Opération bancaire"
        ref = t.get("entry_reference") or t.get("transaction_id")
        if ref:
            key = stable_hash("eb", ref)
        else:
            base = (booked.isoformat(), amount, raw_label.upper())
            key = stable_hash("eb", *base, seen[base])
            seen[base] += 1
        (txs if status == "BOOK" else pending).append(
            RawTransaction(
                booked_at=booked,
                amount_cents=amount,
                raw_label=raw_label,
                dedup_key=key,
                merchant_hint=smart_title(party_name) if party_name else (smart_title(info[0][:60]) if info else None),
                status="terminé" if status == "BOOK" else "à venir",
                details={k: v for k, v in {"source": "Enable Banking", "vendeur": party_name, "transaction": ref}.items() if v},
            )
        )
    bal = pick_balance(balances)
    return Statement(
        source="enable_banking",
        account_external_id=None,
        account_label=label,
        balance_date=bal[1] if bal else None,
        balance_cents=bal[0] if bal else None,
        transactions=txs,
        pending=pending,
        has_pending=True,
    )
