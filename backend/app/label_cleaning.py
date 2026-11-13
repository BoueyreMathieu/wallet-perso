"""Nettoyage des libellés bancaires génériques pour en extraire le vrai vendeur (pur Python).

Les synchros bancaires donnent souvent des libellés du type
  « PAIEMENT PAR CARTE X1234 MONOP PARIS 01/11 », « VIREMENT EMIS VERS MONSIEUR DUPONT JEAN »,
  « PRLV SEPA EDF CLIENTS PARTICULIERS REF123 », « VIREMENT EN VOTRE FAVEUR DE ACME SAS ».
Le début (type d'opération), le n° de carte, les dates et les références ne désignent pas le vendeur :
on les retire. Sans ce nettoyage, tous les paiements par carte avaient l'air d'être « le même vendeur ».
"""

from __future__ import annotations

import re
import unicodedata

# Types d'opération en début de libellé (testés sur un texte en majuscules sans accents, même longueur).
_OP = (
    r"(?:PAIEMENT|ACHAT|REGLEMENT)\s+(?:PAR\s+)?(?:CARTE|CB)(?:\s+BANCAIRE)?"
    r"|PAIEMENT\s+(?:SANS\s+CONTACT|MOBILE|EN\s+LIGNE)"
    # mots seuls (« CB », « CARTE »…) : seulement si le libellé contient un n° de carte ou une date
    # (« CB CARREFOUR 4973XXXXXXXX1234 12/11 » oui ; « Carte Grise Express » non)
    r"|(?:PAIEMENT|CARTE|CB|ACHAT|FACTURE\s+CARTE|FACT(?:URE)?\s+CB)(?=\s.*(?:\bX{1,4}\d{4}\b|\b\d{4}X{4,}|\b\d{2}[/.-]\d{2}\b))"
    r"|PRELEVEMENT(?:\s+SEPA)?(?:\s+(?:EUROPEEN|ECHEANCE))?|PRLV(?:\s+SEPA)?"
    r"|VIREMENT(?:\s+SEPA)?(?:\s+(?:INSTANTANE|INST|PERMANENT|PERIODIQUE))?(?:\s+(?:EMIS|RECU|EN\s+VOTRE\s+FAVEUR|EN\s+FAVEUR))?"
    r"|VIR(?:\s+SEPA)?(?:\s+(?:INST|PERM))?(?:\s+(?:EMIS|RECU|FAV))?"
    r"|RETRAIT(?:\s+(?:AU\s+)?(?:DAB|GAB|DISTRIBUTEUR|ESPECES))?"
    r"|AVOIR\s+(?:CARTE|CB)|REMBOURSEMENT\s+(?:CARTE|CB)|REMISE(?:\s+DE)?\s+CHEQUES?|CHEQUE(?=\s+(?:N\S*\s*)?\d)"
    r"|WERO(?=\s+(?:DE|VERS|A)\b)"
)
_PREFIX_RE = re.compile(rf"^(?:{_OP})\b[\s:.\-*]*")
_LINK_RE = re.compile(r"^(?:DE|DU|DES|VERS|A|AU|POUR|CHEZ|FAVEUR\s+DE)\b\s*")
_CARD_RE = re.compile(r"\b(?:X{1,4}\d{4}|\d{4}X{4,12}|\d{4}\*+\d{0,4}|CARTE\s+N?O?\s*\d+)\b")
_DATE_RE = re.compile(r"\b\d{2}[/.-]\d{2}(?:[/.-]\d{2,4})?\b|\b\d{2}H\d{2}\b")
CASH_WITHDRAWAL = "Retrait d'espèces"
_TAIL_REF_RE = re.compile(r"(?:\s+[A-Z0-9]*\d[A-Z0-9/]*)+$")


def _fold(text: str) -> str:
    """Majuscules sans accents, MÊME longueur que le texte d'origine (pour découper l'original)."""
    return "".join(unicodedata.normalize("NFKD", c)[0] if c.strip() else " " for c in text).upper()


def is_generic(name: str | None) -> bool:
    """Le nom commence par un type d'opération bancaire (« Paiement par carte … », « Virement émis … »)."""
    return bool(name) and bool(_PREFIX_RE.match(_fold(name.strip())))


def clean_payee(label: str | None) -> str:
    """Le vendeur contenu dans un libellé bancaire, ou "" s'il n'y en a pas."""
    if not label:
        return ""
    text = re.sub(r"\s+", " ", label).strip()
    if re.match(r"RETRAIT\b", _fold(text)):
        return CASH_WITHDRAWAL  # tous les retraits sous un même « vendeur »
    for _ in range(4):  # préfixes empilés : « VIR SEPA RECU DE … »
        folded = _fold(text)
        m = _PREFIX_RE.match(folded) or _LINK_RE.match(folded)
        if not m or m.end() == 0:
            break
        text = text[m.end():].strip()
    folded = _fold(text)
    # Retire n° de carte et dates où qu'ils soient (positions trouvées sur le texte replié).
    for rx in (_CARD_RE, _DATE_RE):
        spans = [m.span() for m in rx.finditer(folded)]
        for a, b in reversed(spans):
            text, folded = text[:a] + " " + text[b:], folded[:a] + " " + folded[b:]
    text = re.sub(r"\s+", " ", text).strip(" -*:/.")
    text = text[: len(text) - len(_TAIL_REF_RE.search(_fold(text)).group(0))] if _TAIL_REF_RE.search(_fold(text)) else text
    return text.strip(" -*:/.")
