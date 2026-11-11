#!/usr/bin/env python3
"""Décrit la STRUCTURE d'un export CSV sans en révéler le contenu.

Sortie en Markdown, à copier-coller à Claude pour écrire un nouvel import.

Ce qui est affiché :
  - encodage, séparateur, fins de ligne, lignes d'en-tête libres (avant le tableau) ;
  - pour chaque colonne : nom, taux de remplissage, type deviné (date, montant, nombre, texte…),
    et des « formes » masquées : chaque suite de lettres devient A/a, chaque chiffre devient 9.
    Ex. « Paiement CB 12/03 Boulangerie » → « Aa A 99/99 Aa ».
Ce qui n'est JAMAIS affiché : les valeurs réelles, SAUF pour les colonnes que tu cites
explicitement avec --show-values (utile pour une colonne « Type » ou « Statut », pas pour un libellé).

Usage :
  python scripts/csv_structure.py imports/export.csv
  python scripts/csv_structure.py imports/export.csv --show-values "Type" "État"
  python scripts/csv_structure.py imports/export.csv --out structure.md
  python scripts/csv_structure.py imports/export.csv --crosstab "Type" "État" --profile-by "Type"

Sans Python sous Windows, via Docker (depuis le dossier wallet-perso) :
  docker run --rm -v "${PWD}:/w" -w /w python:3.12-slim python scripts/csv_structure.py imports/export.csv
"""

import argparse
import csv
import io
import os
import re
import sys
from collections import Counter

DELIMITERS = [";", ",", "\t", "|"]
SAMPLE_SHAPES = 4

DATE_PATTERNS = [
    (re.compile(r"^\d{2}/\d{2}/\d{4}$"), "date JJ/MM/AAAA"),
    (re.compile(r"^\d{2}/\d{2}/\d{2}$"), "date JJ/MM/AA"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}$"), "date AAAA-MM-JJ"),
    (re.compile(r"^\d{2}\.\d{2}\.\d{4}$"), "date JJ.MM.AAAA"),
    (re.compile(r"^\d{2}-\d{2}-\d{4}$"), "date JJ-MM-AAAA"),
    (re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"), "date-heure ISO"),
    (re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}(:\d{2})?$"), "date-heure JJ/MM/AAAA hh:mm"),
    (re.compile(r"^\d{2}:\d{2}(:\d{2})?$"), "heure hh:mm(:ss)"),
]
AMOUNT_COMMA = re.compile(r"^[-+]?\d{1,3}([   .]?\d{3})*,\d{1,4}\s*€?$")
AMOUNT_DOT = re.compile(r"^[-+]?\d{1,3}([   ,]?\d{3})*\.\d{1,4}\s*€?$")
INTEGER = re.compile(r"^[-+]?\d+$")
CURRENCY = re.compile(r"^[A-Z]{3}$")


def shape(value: str, limit: int = 50) -> str:
    """Masque une valeur : lettres → A/a (une par mot), chiffres → 9, ponctuation conservée."""
    out = re.sub(r"[^\W\d_]+", lambda m: "A" if m.group(0)[0].isupper() else "a", value)
    out = re.sub(r"\d", "9", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out if len(out) <= limit else out[: limit - 1] + "…"


def decode(raw: bytes):
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8"), "UTF-8 avec BOM"
    for enc, label in (("utf-8", "UTF-8"), ("cp1252", "Windows-1252"), ("latin-1", "ISO-8859-1")):
        try:
            return raw.decode(enc), label
        except UnicodeDecodeError:
            continue
    raise ValueError("encodage inconnu")


def guess_delimiter(text: str) -> str:
    lines = [l for l in text.splitlines() if l.strip()][:200]
    best, best_score = ";", -1
    for d in DELIMITERS:
        counts = Counter(l.count(d) for l in lines if l.count(d) > 0)
        if not counts:
            continue
        n, freq = counts.most_common(1)[0]
        score = freq * n
        if score > best_score:
            best, best_score = d, score
    return best


def find_header(rows: list) -> int:
    """Première ligne d'au moins 2 cellules non vides suivie de lignes de même largeur."""
    for i, row in enumerate(rows):
        filled = [c for c in row if c.strip()]
        if len(filled) < 2:
            continue
        width = len(row)
        following = [r for r in rows[i + 1 : i + 6] if any(c.strip() for c in r)]
        if following and all(abs(len(r) - width) <= 1 for r in following):
            return i
    return 0


def infer_type(values: list) -> str:
    vals = [v.strip() for v in values if v.strip()]
    if not vals:
        return "vide"
    for pattern, label in DATE_PATTERNS:
        if all(pattern.match(v) for v in vals):
            return label
    if all(AMOUNT_COMMA.match(v) for v in vals):
        seps = {m for v in vals for m in re.findall(r"\d([   .])\d{3}", v)}
        th = {" ": "espace", " ": "espace insécable", " ": "espace fine", ".": "point"}
        return "montant (décimale « , »" + (f", milliers : {', '.join(th[s] for s in seps)})" if seps else ")")
    if all(AMOUNT_DOT.match(v) for v in vals):
        return "montant (décimale « . »)"
    if all(INTEGER.match(v) for v in vals):
        return "entier"
    if all(CURRENCY.match(v) for v in vals):
        return "code de 3 lettres (devise, fuseau…)"
    return "texte"


def describe(path: str, show_values: list, max_values: int, encoding: str = None, delimiter: str = None,
             crosstab: list = None, profile_by: str = None, ref: list = None) -> str:
    if not os.path.exists(path) and "\\" in path:
        path = path.replace("\\", "/")  # chemin Windows (.\\imports\\x.csv) passé dans Docker
    raw = open(path, "rb").read()
    if encoding:
        text, enc_label = raw.decode(encoding), encoding
    else:
        text, enc_label = decode(raw)
    eol = "CRLF (Windows)" if "\r\n" in text else ("CR" if "\r" in text else "LF (Unix)")
    delim = delimiter or guess_delimiter(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    h = find_header(rows)
    header = rows[h] if rows else []
    data = [r for r in rows[h + 1 :] if any(c.strip() for c in r)]

    out = [f"## Structure de `{path.replace(chr(92), '/').split('/')[-1]}`", ""]
    out.append(f"- Encodage : {enc_label} · fins de ligne : {eol} · séparateur : `{repr(delim)[1:-1]}`")
    out.append(f"- Lignes de données : {len(data)} · ligne d'en-tête du tableau : {h + 1}")
    widths = Counter(len(r) for r in data)
    out.append(f"- Nombre de cellules par ligne : {dict(widths)}")
    if h > 0:
        out += ["", "### Lignes avant le tableau (masquées)", "```"]
        for r in rows[:h]:
            line = delim.join(r)
            out.append(shape(line, 80) if line.strip() else "(vide)")
        out.append("```")

    out += ["", "### Colonnes", "", "| # | Nom | Rempli | Distincts | Type deviné | Multiligne | Formes (masquées) |", "|---|---|---|---|---|---|---|"]
    multiline_detail = []
    for i, name in enumerate(header):
        col = [r[i] if i < len(r) else "" for r in data]
        filled = [v for v in col if v.strip()]
        pct = f"{100 * len(filled) // max(len(col), 1)} %"
        multi = [v for v in filled if "\n" in v]
        first_lines = [v.split("\n")[0] for v in filled]
        typ = infer_type(first_lines)
        shapes = [s for s, _ in Counter(shape(v.replace("\n", " ⏎ ")) for v in filled).most_common(SAMPLE_SHAPES)]
        out.append(
            f"| {i + 1} | {name or '(sans nom)'} | {pct} | {len(set(filled))} | {typ} | "
            f"{f'{len(multi)} cellules' if multi else 'non'} | {' · '.join(f'`{s}`' for s in shapes)} |"
        )
        if multi:
            nb = Counter(v.count("\n") + 1 for v in multi)
            per_line = []
            for k in range(max(nb)):
                parts = [v.split("\n")[k] for v in multi if len(v.split("\n")) > k]
                ne = [p for p in parts if p.strip()]
                per_line.append(
                    f"  - ligne {k + 1} : remplie {100 * len(ne) // max(len(parts), 1)} %, "
                    f"formes {' · '.join(f'`{s}`' for s, _ in Counter(shape(p) for p in ne).most_common(3)) or '—'}"
                )
            multiline_detail.append(f"- **{name}** : {dict(nb)} lignes par cellule\n" + "\n".join(per_line))

    if multiline_detail:
        out += ["", "### Détail des cellules multilignes", *multiline_detail]

    for wanted in show_values:
        if wanted not in header:
            out += ["", f"⚠️ Colonne « {wanted} » introuvable (noms : {', '.join(header)})"]
            continue
        i = header.index(wanted)
        counts = Counter((r[i] if i < len(r) else "").strip() for r in data)
        out += ["", f"### Valeurs de « {wanted} » (affichées à ta demande)", ""]
        for v, n in counts.most_common(max_values):
            out.append(f"- `{v or '(vide)'}` × {n}")
        if len(counts) > max_values:
            out.append(f"- … {len(counts) - max_values} autres valeurs")

    if crosstab:
        missing = [c for c in crosstab if c not in header]
        if missing:
            out += ["", f"⚠️ Colonnes introuvables pour --crosstab : {', '.join(missing)}"]
        else:
            idx = [header.index(c) for c in crosstab]
            combos = Counter(tuple((r[i] if i < len(r) else "").strip() or "(vide)" for i in idx) for r in data)
            out += ["", f"### Combinaisons {' × '.join(crosstab)} (affichées à ta demande)", "",
                    "| " + " | ".join(crosstab) + " | Nb |", "|" + "---|" * (len(crosstab) + 1)]
            for combo, n in combos.most_common():
                out.append("| " + " | ".join(combo) + f" | {n} |")

    if profile_by:
        if profile_by not in header:
            out += ["", f"⚠️ Colonne « {profile_by} » introuvable pour --profile-by"]
        else:
            k = header.index(profile_by)
            groups = {}
            for r in data:
                groups.setdefault((r[k] if k < len(r) else "").strip() or "(vide)", []).append(r)
            out += ["", f"### Remplissage des colonnes selon « {profile_by} » (valeurs masquées)", "",
                    "Pour chaque valeur : colonnes remplies (%), et signe des montants (+ / − / 0)."]
            for value, rows_ in sorted(groups.items(), key=lambda kv: -len(kv[1])):
                parts = []
                for i, name in enumerate(header):
                    if i == k or not name:
                        continue
                    vals = [(r[i] if i < len(r) else "").strip() for r in rows_]
                    filled = [v for v in vals if v]
                    if not filled:
                        continue
                    pct = 100 * len(filled) // len(vals)
                    note = ""
                    if all(AMOUNT_COMMA.match(v) or AMOUNT_DOT.match(v) for v in filled):
                        neg = sum(v.startswith("-") for v in filled)
                        zero = sum(not re.search(r"[1-9]", v) for v in filled)
                        note = f" [+{len(filled) - neg - zero} / −{neg} / 0:{zero}]"
                    parts.append(f"{name} {pct} %{note}")
                out += ["", f"- **{value}** ({len(rows_)} lignes) : " + " · ".join(parts)]
    if ref and profile_by in header:
        ref_col, id_col = ref
        if ref_col not in header or id_col not in header:
            out += ["", f"⚠️ Colonnes introuvables pour --ref : {ref_col}, {id_col}"]
        else:
            ri, ii, k = header.index(ref_col), header.index(id_col), header.index(profile_by)
            by_id = {r[ii].strip(): r for r in data if ii < len(r) and r[ii].strip()}
            links = Counter()
            for r in data:
                rv = r[ri].strip() if ri < len(r) else ""
                if not rv:
                    continue
                target = by_id.get(rv) or by_id.get(re.sub(r"^[A-Z]-", "", rv))
                links[(r[k].strip(), target[k].strip() if target else "(introuvable dans le fichier)")] += 1
            out += ["", f"### Liens « {ref_col} » → « {id_col} » (par {profile_by})", "",
                    f"| {profile_by} de la ligne | {profile_by} de la ligne référencée | Nb |", "|---|---|---|"]
            for (a_, b_), n in links.most_common():
                out.append(f"| {a_} | {b_} | {n} |")
    return "\n".join(out) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--show-values", nargs="*", default=[], metavar="COLONNE", help="colonnes dont afficher les valeurs réelles")
    p.add_argument("--max-values", type=int, default=30)
    p.add_argument("--crosstab", nargs="*", default=[], metavar="COLONNE", help="compter les combinaisons de valeurs de ces colonnes")
    p.add_argument("--ref", nargs=2, metavar=("COL_REFERENCE", "COL_ID"), help="avec --profile-by : vers quel type de ligne pointe la colonne de référence")
    p.add_argument("--profile-by", metavar="COLONNE", help="remplissage des autres colonnes pour chaque valeur de cette colonne")
    p.add_argument("--encoding")
    p.add_argument("--delimiter")
    p.add_argument("--out", help="écrire le résultat dans ce fichier (en plus de l'écran)")
    a = p.parse_args()
    report = "\n".join(describe(f, a.show_values, a.max_values, a.encoding, a.delimiter, a.crosstab, a.profile_by, a.ref)
        for f in a.files)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(report)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(report)


if __name__ == "__main__":
    main()
