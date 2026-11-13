"""Garde-fous sur les expressions régulières saisies dans l'appli (règles, services).

Python n'a pas de délai maximal pour une regex : une expression « catastrophique » (ex. (a+)+$) peut bloquer
l'API. On refuse donc les formes connues pour ça et les expressions trop longues.
"""

import re

MAX_LENGTH = 200
# Un groupe qui contient un quantificateur et qui est lui-même répété : (a+)+, (\w*)*, (x+){2,}…
_NESTED = re.compile(r"\((?:[^()\\]|\\.)*[+*}](?:[^()\\]|\\.)*\)\s*(?:[+*]|\{\d*,)")
# Une alternative répétée dont les branches peuvent se chevaucher : (a|a)+, (\w|\d)*…
_ALT_REPEATED = re.compile(r"\((?:[^()\\]|\\.)*\|(?:[^()\\]|\\.)*\)\s*(?:[+*]|\{\d*,)")


def check_regex(pattern: str) -> str | None:
    """None si l'expression est acceptable, sinon le message d'erreur à afficher."""
    if len(pattern) > MAX_LENGTH:
        return f"Expression trop longue ({MAX_LENGTH} caractères maximum)"
    try:
        re.compile(pattern)
    except re.error as e:
        return f"Expression régulière invalide : {e}"
    if _NESTED.search(pattern) or _ALT_REPEATED.search(pattern):
        return "Expression refusée : une répétition imbriquée (ex. (a+)+) peut bloquer l'appli. Simplifie-la."
    return None
