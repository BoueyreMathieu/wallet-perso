import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, advice, auth, categories, connections, dashboard, data, goals, imports, merchants, planning, reports, settings, splits, tags, transactions, widgets
from app.config import get_settings
from app.db import get_sessionmaker
from app.log_filters import MaskQueryFilter
from app.seed import seed_all

log = logging.getLogger("wallet")
# Les messages de l'appli (wallet.*) s'affichent dans `docker compose logs api`.
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)
    log.propagate = False
# Logs d'accès sans paramètres sensibles (code/state du retour bancaire, recherches).
logging.getLogger("uvicorn.access").addFilter(MaskQueryFilter())


async def _sync_loop(hours: int) -> None:
    """Synchro bancaire automatique : toute connexion pas synchronisée depuis `hours` heures l'est (vérifié 2 minutes
    après le démarrage puis tous les quarts d'heure : un redémarrage ou une mise en veille ne fait plus sauter la synchro).
    Dans un fil séparé : appels réseau bloquants."""
    from datetime import timedelta

    from app.services.sync import sync_stale

    def run() -> None:
        with get_sessionmaker()() as db:
            sync_stale(db, timedelta(hours=hours))

    delay = 120
    while True:
        await asyncio.sleep(delay)
        delay = 900
        try:
            await asyncio.to_thread(run)
        except Exception as e:  # noqa: BLE001 - la boucle ne doit jamais s'arrêter
            log.warning("Synchro automatique en échec : %s", e)


def _catch_up(db) -> None:
    """Au démarrage : rapprochements PayPal et virements internes sur les données déjà en base
    (utile après une mise à jour de ces règles)."""
    from app.services.merchant_merge import auto_merge
    from app.services.merchant_repair import fix_generic_merchants
    from app.services.reconcile import reconcile_paypal
    from app.services.transfers import detect

    try:
        n_fixed = fix_generic_merchants(db)
        if n_fixed:
            log.info("Démarrage : vendeur recalculé pour %d opération(s) au libellé bancaire générique", n_fixed)
        n_merge = auto_merge(db)
        n_pp, n_vir = reconcile_paypal(db), detect(db)
        db.commit()
        from app.services.recurring import refresh as refresh_recurring

        res = refresh_recurring(db)
        db.commit()
        if res["created"]:
            log.info("Démarrage : %d opération(s) récurrente(s) détectée(s)", res["created"])
        if n_pp or n_vir or n_merge:
            log.info("Démarrage : %d rapprochement(s) PayPal, %d virement(s) apparié(s), %d vendeur(s) similaire(s) fusionné(s)", n_pp, n_vir, n_merge)
    except Exception:  # noqa: BLE001 - ne jamais empêcher l'appli de démarrer
        db.rollback()
        log.exception("Rattrapage au démarrage impossible")


def _security_startup(db) -> None:
    """Sessions/appareils expirés supprimés ; sessions fermées si le mot de passe a changé."""
    from app.security import check_password_change, purge_expired

    try:
        n = purge_expired(db)
        check_password_change(db)
        db.commit()
        if n:
            log.info("Démarrage : %d session(s) ou appareil(s) expiré(s) supprimé(s)", n)
    except Exception:  # noqa: BLE001 - ne jamais empêcher l'appli de démarrer
        db.rollback()
        log.exception("Contrôles de sécurité au démarrage impossibles")


@asynccontextmanager
async def lifespan(_: FastAPI):
    with get_sessionmaker()() as db:
        seed_all(db)
        _security_startup(db)
        _catch_up(db)
    hours = get_settings().sync_interval_hours
    task = asyncio.create_task(_sync_loop(hours)) if hours > 0 else None
    yield
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


_docs = get_settings().api_docs
# Pas de documentation publique de l'API en production (API_DOCS=true pour la réactiver en développement).
app = FastAPI(
    title="Wallet perso",
    version="0.9.0",
    lifespan=lifespan,
    docs_url="/api/docs" if _docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if _docs else None,
)


@app.middleware("http")
async def no_store(request: Request, call_next):
    """Les réponses de l'API (données financières) ne sont jamais gardées en cache."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# Appli Android (Capacitor) : servie depuis https://localhost, elle appelle l'API avec un jeton d'appareil.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-Confirm-Password"],
)

app.include_router(auth.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(dashboard.router)
app.include_router(settings.router)
app.include_router(imports.router)
app.include_router(transactions.router)
app.include_router(merchants.router)
app.include_router(data.router)
app.include_router(tags.router)
app.include_router(connections.router)
app.include_router(widgets.router)
app.include_router(planning.router)
app.include_router(advice.router)
app.include_router(reports.router)
app.include_router(goals.router)
app.include_router(splits.router)


@app.get("/api/health", tags=["système"])
def health() -> dict:
    return {"status": "ok"}
