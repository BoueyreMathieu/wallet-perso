"""Historique refusé par la banque (« Wrong transactions period requested ») : période raccourcie (pur Python)."""

from datetime import date, timedelta

import pytest

from app.connectors.enable_banking import EnableBankingClient, EnableBankingError


class LimitedBank(EnableBankingClient):
    """Banque qui n'accepte que 90 jours d'historique."""

    def __init__(self):
        super().__init__("app", b"", "https://exemple.invalid")
        self.asked: list[str] = []

    def _request(self, method, path, params=None, body=None):
        self.asked.append(params["date_from"])
        if date.fromisoformat(params["date_from"]) < date.today() - timedelta(days=90):
            raise EnableBankingError("Enable Banking 422 : Wrong transactions period requested", 422)
        return {"transactions": [{"entry_reference": "x"}]}


def test_shorter_period_after_refusal():
    bank = LimitedBank()
    assert bank.transactions("uid", date.today() - timedelta(days=120)) == [{"entry_reference": "x"}]
    assert bank.asked == [(date.today() - timedelta(days=120)).isoformat(), (date.today() - timedelta(days=89)).isoformat()]


def test_recent_period_untouched_and_other_errors_raised():
    bank = LimitedBank()
    bank.transactions("uid", date.today() - timedelta(days=7))
    assert len(bank.asked) == 1

    class Broken(LimitedBank):
        def _request(self, method, path, params=None, body=None):
            raise EnableBankingError("Enable Banking 500 : panne", 500)

    with pytest.raises(EnableBankingError):
        Broken().transactions("uid", date.today() - timedelta(days=120))
