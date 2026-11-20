from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.config.database import connection
from src.constants.enums import Role
from src.controllers.auth import allow, current
from src.domain.spec import SPEC
from src.models.identity import User
from src.models.source import Dataset
from src.schemas.requests import CalibrationUpload, Upload
from src.services.audit import record
from src.services import calibrations
from src.services.datasets import save, template
from src.services.validation import parse_calibrations, parse_rows
from src.utils import views

router = APIRouter()


@router.get('/spec')
def spec():
    return {key: value for key, value in SPEC.items() if key != 'fixture'}


@router.get('/template')
def sample(actor: User = Depends(current)):
    filename = quote(SPEC['sample_name'])
    return Response(template(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})


@router.get('/datasets')
def datasets(db: Session = Depends(connection), actor: User = Depends(current)):
    return [views.dataset(item) for item in db.scalars(select(Dataset).order_by(Dataset.id.desc()).limit(100))]


@router.get('/datasets/{dataset_id}')
def details(dataset_id: int, offset: int = Query(0, ge=0), limit: int = Query(16, ge=1, le=100),
            db: Session = Depends(connection), actor: User = Depends(current)):
    item = db.get(Dataset, dataset_id)
    if not item:
        raise HTTPException(404, '找不到该数据批次')
    return {**views.dataset(item), 'rows': item.rows[offset:offset + limit]}


@router.post('/datasets', status_code=201)
def upload(body: Upload, db: Session = Depends(connection),
           actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    rows = parse_rows(body.csv_text)
    item, created = save(db, body.name, body.filename, rows, actor.username)
    if created:
        record(db, actor.username, 'dataset.imported', item.id, rows=item.row_count)
    db.commit()
    return {**views.dataset(item), 'created': created}


@router.get('/calibration')
def calibration_state(db: Session = Depends(connection), actor: User = Depends(current)):
    version = calibrations.current_version(db)
    return {**views.calibration_state(version, calibrations.entries_for_version(db, version)),
            'batches': [views.calibration_batch(item) for item in calibrations.batches(db)]}


@router.get('/calibration/template')
def calibration_template(actor: User = Depends(current)):
    filename = quote(SPEC['calibration_sample_name'])
    return Response(calibrations.template(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})


@router.post('/calibrations', status_code=201)
def upload_calibration(body: CalibrationUpload, db: Session = Depends(connection),
                       actor: User = Depends(allow(Role.ADMIN, Role.ANALYST))):
    rows = parse_calibrations(body.csv_text)
    try:
        item, created = calibrations.apply_batch(db, body.name, body.filename, rows, actor.username)
    except ValueError:
        db.rollback()
        raise
    if created:
        record(db, actor.username, 'calibration.imported', item.id, rows=item.row_count,
               applied=item.applied_count, ignored=item.ignored_count, version=item.version)
    db.commit()
    return {**views.calibration_batch(item), 'created': created,
            'current_version': calibrations.current_version(db)}
