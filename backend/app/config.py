from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration lue depuis les variables d'environnement (fichier .env)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://wallet:wallet@db:5432/wallet"

    # Mot de passe unique de l'appli (un seul utilisateur). De préférence son empreinte (APP_PASSWORD_HASH,
    # générée par `python -m app.tools.hash_password`) plutôt que le mot de passe en clair (APP_PASSWORD).
    app_password: str = ""
    app_password_hash: str = ""
    # Clé secrète du serveur (empreintes internes).
    secret_key: str
    # Clé Fernet qui chiffre les secrets bancaires stockés en base.
    encryption_key: str

    # Session du navigateur : expire après N jours sans utilisation, et au plus tard après M jours.
    session_idle_days: int = 14
    session_max_days: int = 90
    # Appli Android / widgets : jeton expiré après N jours sans utilisation.
    device_idle_days: int = 90
    # Cookie « Secure » (HTTPS seulement). Laisser true : Tailscale sert l'appli en HTTPS et les navigateurs
    # acceptent aussi ce cookie sur http://localhost. false uniquement pour un accès en HTTP par une autre adresse.
    cookie_secure: bool = True
    # Échecs de mot de passe tolérés avant blocage progressif (1 min, 2, 4… jusqu'à 1 h).
    login_max_failures: int = 5
    # Pages /docs et /openapi.json de l'API (utile en développement seulement).
    api_docs: bool = False

    # --- Enable Banking (synchro bancaire DSP2) ---
    enable_banking_app_id: str = ""
    # Clé privée .pem ; vide = on cherche <app_id>.pem puis un seul .pem dans secrets_dir.
    enable_banking_key_path: str = ""
    enable_banking_api: str = "https://api.enablebanking.com"
    enable_banking_redirect_url: str = "http://localhost:8080/api/connections/callback"
    secrets_dir: str = "/app/secrets"
    # Origines autorisées à appeler l'API depuis une autre adresse (l'appli Android Capacitor), séparées par des virgules.
    cors_origins: str = "https://localhost,capacitor://localhost"
    # Synchro automatique toutes les N heures (0 = désactivée). Les banques limitent souvent à ~4 par jour.
    sync_interval_hours: int = 6

    @field_validator(
        "app_password", "app_password_hash", "secret_key", "encryption_key", "database_url", "enable_banking_app_id",
        "enable_banking_key_path", "enable_banking_redirect_url", mode="before",
    )
    @classmethod
    def _strip(cls, v: str) -> str:
        # Un .env aux fins de ligne Windows peut laisser un "\r" invisible en fin de valeur.
        return v.strip() if isinstance(v, str) else v


@lru_cache
def get_settings() -> Settings:
    return Settings()
