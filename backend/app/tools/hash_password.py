"""Génère l'empreinte du mot de passe de l'appli, à mettre dans .env (APP_PASSWORD_HASH=…).

Usage (le mot de passe est demandé sans s'afficher, il n'est jamais écrit nulle part) :
    docker compose exec api python -m app.tools.hash_password
Ou par scripts/securiser-env.ps1, qui transmet le mot de passe sur l'entrée standard (--stdin) et met .env à jour.
"""

import getpass
import sys

from app.passwords import hash_password


def main() -> int:
    if "--stdin" in sys.argv:
        # Mode script : mot de passe lu sur l'entrée standard, seule l'empreinte est affichée.
        password = sys.stdin.buffer.read().decode("utf-8").rstrip("\r\n")
        if len(password) < 12:
            print("ERREUR: 12 caractères minimum", file=sys.stderr)
            return 1
        print(hash_password(password))
        return 0
    first = getpass.getpass("Nouveau mot de passe de l'appli : ")
    if len(first) < 12:
        print("Trop court : 12 caractères minimum (16 ou plus conseillé, généré par un gestionnaire de mots de passe).")
        return 1
    if getpass.getpass("Encore une fois : ") != first:
        print("Les deux saisies ne correspondent pas.")
        return 1
    print("\nAjoute cette ligne dans .env (et supprime la ligne APP_PASSWORD=…) :\n")
    print(f"APP_PASSWORD_HASH={hash_password(first)}")
    print("\nPuis : docker compose up -d   (les sessions ouvertes dans les navigateurs seront fermées)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
