import csv
import hashlib
import io
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.domain import calibration
from src.domain.spec import SPEC
from src.models.calibration import CalibrationBatch, CalibrationEntry, CalibrationState


def ensure_state(db=None):
    """确保单行状态存在。应用启动时调用，避免并发首次导入抢建同一行。"""
    from src.config.database import Session
    own = db is None
    session = Session() if own else db
    try:
        if session.scalar(select(CalibrationState).where(CalibrationState.id == 1)) is None:
            session.add(CalibrationState(id=1, version=0))
            try:
                with session.begin_nested():
                    session.flush()
            except IntegrityError:
                pass
        if own:
            session.commit()
    finally:
        if own:
            session.close()


def _state(db, lock):
    """取单行状态；导入时加行锁，切换批次串行执行。"""
    state = db.scalar(select(CalibrationState).where(CalibrationState.id == 1).with_for_update()
                      if lock else select(CalibrationState).where(CalibrationState.id == 1))
    if state is None:
        ensure_state(db)
        state = db.scalar(select(CalibrationState).where(CalibrationState.id == 1).with_for_update()
                          if lock else select(CalibrationState).where(CalibrationState.id == 1))
    return state


def checksum(rows):
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def current_version(db):
    return _state(db, lock=False).version


def effective_entries(db, version):
    """某版本生效的校准偏差：每个探针日期取该版本内修订号最高的记录。"""
    rows = db.scalars(
        select(CalibrationEntry)
        .where(CalibrationEntry.version <= version)
        .order_by(CalibrationEntry.id)
    ).all()
    latest = {}
    for row in rows:
        item_key = calibration.key(row.probe, row.handoff_date)
        current = latest.get(item_key)
        if current is None or row.revision >= current.revision:
            latest[item_key] = row
    return {
        item_key: {
            "probe": row.probe,
            "handoff_date": row.handoff_date,
            "revision": row.revision,
            "offset": row.offset,
            "calibration_id": row.calibration_id,
        }
        for item_key, row in latest.items()
    }


def apply_batch(db, name, filename, rows, actor):
    """整批校验后一次性切换。任何失败都不改动当前生效版本。"""
    state = _state(db, lock=True)
    signature = checksum(rows)
    existing = db.scalar(select(CalibrationBatch).where(CalibrationBatch.checksum == signature))
    if existing:
        return existing, False

    current = effective_entries(db, state.version)
    changes, ignored = calibration.merge(current, rows)
    version = state.version + 1
    batch = CalibrationBatch(
        name=name, filename=filename, checksum=signature, row_count=len(rows),
        applied_count=len(changes), ignored_count=ignored, version=version,
        status='applied', author=actor,
    )
    try:
        with db.begin_nested():
            db.add(batch)
            db.flush()
            for change in changes:
                db.add(CalibrationEntry(
                    batch_id=batch.id, version=version, probe=change['probe'],
                    handoff_date=change['handoff_date'], revision=change['revision'],
                    offset=change['offset'], calibration_id=change['calibration_id'],
                ))
            state.version = version
            db.flush()
    except IntegrityError:
        # 并发导入同一份校准单：保存点已回滚，重读已提交的批次，当前版本保持不变。
        existing = db.scalar(select(CalibrationBatch).where(CalibrationBatch.checksum == signature))
        if existing:
            return existing, False
        raise
    return batch, True


def snapshot(db, version):
    """把生效校准整理为分析用的不可变快照。"""
    return effective_entries(db, version)


def template():
    fields = [field['key'] for field in SPEC['calibration_fields']]
    buffer = io.StringIO(newline='')
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    writer.writerows([
        {'probe': 'TP-23', 'handoff_date': '2026-11-16', 'revision': 2, 'offset': -0.6, 'calibration_id': 'CAL-2611-23-R2'},
        {'probe': 'TP-31', 'handoff_date': '2026-11-15', 'revision': 1, 'offset': 0.4, 'calibration_id': 'CAL-2611-31-R1'},
    ])
    return '﻿' + buffer.getvalue()


def batches(db):
    return db.scalars(select(CalibrationBatch).order_by(CalibrationBatch.id.desc()).limit(100)).all()


def entries_for_version(db, version):
    return list(effective_entries(db, version).values())
