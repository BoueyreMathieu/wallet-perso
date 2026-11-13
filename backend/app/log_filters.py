"""Filtres de journalisation : rien de sensible dans `docker compose logs`."""

import logging
import re

# Paramètres d'URL masqués dans les logs d'accès (code et state du retour bancaire, recherches).
_SENSITIVE = re.compile(r"((?:^|[?&])(?:code|state|q|search|recherche)=)[^&\s]*", re.IGNORECASE)


def mask_query(path: str) -> str:
    return _SENSITIVE.sub(r"\1***", path)


class MaskQueryFilter(logging.Filter):
    """Pour le logger « uvicorn.access » : args = (client, méthode, chemin, version HTTP, statut)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            record.args = (*args[:2], mask_query(args[2]), *args[3:])
        return True
