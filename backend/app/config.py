from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis les variables d'environnement (fichier .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://wallet:wallet@db:5432/wallet"

    # Mot de passe unique de l'appli (un seul utilisateur).
    app_password: str
    # Sert à signer le cookie de session.
    secret_key: str
    # Clé Fernet qui chiffre les secrets bancaires stockés en base.
    encryption_key: str

    session_max_age_days: int = 30
    # Mettre à true quand l'appli est servie en HTTPS.
    cookie_secure: bool = False

    @field_validator("app_password", "secret_key", "encryption_key", "database_url", mode="before")
    @classmethod
    def _strip(cls, v: str) -> str:
        # Un .env aux fins de ligne Windows peut laisser un "\r" invisible en fin de valeur.
        return v.strip() if isinstance(v, str) else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
