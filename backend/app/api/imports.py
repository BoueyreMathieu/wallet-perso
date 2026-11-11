from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import ImportResultOut
from app.security import require_auth
from app.services.importing import IMPORTERS, AccountNeeded, ImportError_

router = APIRouter(prefix="/api/imports", tags=["imports"], dependencies=[Depends(require_auth)])

MAX_SIZE = 10 * 1024 * 1024


@router.post("/{source}", response_model=ImportResultOut)
async def import_file(
    source: str,
    file: UploadFile = File(...),
    account_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
):
    importer = IMPORTERS.get(source)
    if importer is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Source inconnue : {source}")
    raw = await file.read()
    if len(raw) > MAX_SIZE:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Fichier trop gros (10 Mo max).")
    try:
        return importer(db, raw, file.filename, account_id)
    except AccountNeeded as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    except ImportError_ as e:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
