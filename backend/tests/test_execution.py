from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.constants.enums import Status
from src.models.jobs import Run
from src.models.source import Dataset
from src.services import calibrations, execution


def _patch_session(monkeypatch, db):
    engine = db.get_bind()
    monkeypatch.setattr(execution, "Session", sessionmaker(engine, expire_on_commit=False))
    # 让工作线程与测试共享同一个连接，SQLite 内存库才能看到测试写入。
    monkeypatch.setattr(execution, "write_report", lambda job_id, attempt, result: f"report-{job_id}.csv")


def _cal(probe, day, revision, offset, calibration_id):
    return {"probe": probe, "handoff_date": day, "revision": revision,
            "offset": offset, "calibration_id": calibration_id}


def _dataset(db):
    from src.domain.demo import demo_rows
    rows = demo_rows()
    item = Dataset(name="批次", filename="a.csv", checksum="x" * 64, rows=rows,
                   row_count=len(rows), author="analyst")
    db.add(item)
    db.flush()
    return item


def _run(db, dataset, version):
    item = Run(name="复核", dataset_id=dataset.id, params={}, calibration_version=version, author="analyst")
    db.add(item)
    db.flush()
    return item


def test_claim_takes_snapshot_of_version_at_launch(db, monkeypatch):
    _patch_session(monkeypatch, db)
    dataset = _dataset(db)
    first, _ = calibrations.apply_batch(db, "v1", "a.csv", [_cal("TP-23", "2026-11-16", 1, -0.3, "CAL-A")], "analyst")
    db.commit()
    job = _run(db, dataset, first.version)
    db.commit()

    calibrations.apply_batch(db, "v2", "b.csv", [_cal("TP-23", "2026-11-16", 2, -0.9, "CAL-B")], "analyst")
    db.commit()

    lease = execution.claim()
    assert lease is not None
    job_id, attempt, _rows, _params, version, snapshot = lease
    assert version == 1
    assert snapshot[("TP-23", "2026-11-16")]["offset"] == -0.3


def test_requeued_run_keeps_launch_version_after_interruption(db, monkeypatch):
    from src.utils.time import now
    from datetime import timedelta

    _patch_session(monkeypatch, db)
    dataset = _dataset(db)
    first, _ = calibrations.apply_batch(db, "v1", "a.csv", [_cal("TP-23", "2026-11-16", 1, -0.3, "CAL-A")], "analyst")
    db.commit()

    # 模拟排队后先被领取、进程中断，租约过期；期间有新校准导入。
    job = _run(db, dataset, first.version)
    job.status = Status.RUNNING
    job.attempt = 1
    job.lease_until = now() - timedelta(minutes=5)
    db.commit()

    calibrations.apply_batch(db, "v2", "b.csv", [_cal("TP-23", "2026-11-16", 2, -0.9, "CAL-B")], "analyst")
    db.commit()

    lease = execution.claim()
    assert lease is not None
    job_id, attempt, _rows, _params, version, snapshot = lease
    assert job_id == job.id and attempt == 2
    assert version == 1
    assert snapshot[("TP-23", "2026-11-16")]["offset"] == -0.3


def test_completed_result_does_not_change_with_new_calibration(db, monkeypatch):
    _patch_session(monkeypatch, db)
    dataset = _dataset(db)
    first, _ = calibrations.apply_batch(db, "v1", "a.csv", [_cal("TP-23", "2026-11-16", 1, -0.3, "CAL-A")], "analyst")
    db.commit()
    job = _run(db, dataset, first.version)
    db.commit()

    execution.execute(execution.claim())
    db.expire_all()
    job = db.get(Run, job.id)
    assert job.status == Status.COMPLETE
    original = job.result["tables"][3]["rows"]
    target = next(row for row in original if row["handoff_id"] == "MY-20261116-S-P-03")
    assert target["calibration_id"] == "CAL-A"

    calibrations.apply_batch(db, "v2", "b.csv", [_cal("TP-23", "2026-11-16", 2, -0.9, "CAL-B")], "analyst")
    db.commit()
    db.expire_all()
    job = db.get(Run, job.id)
    target = next(row for row in job.result["tables"][3]["rows"]
                  if row["handoff_id"] == "MY-20261116-S-P-03")
    assert target["calibration_id"] == "CAL-A"


def test_legacy_run_without_version_adopts_current_at_claim(db, monkeypatch):
    _patch_session(monkeypatch, db)
    dataset = _dataset(db)
    first, _ = calibrations.apply_batch(db, "v1", "a.csv", [_cal("TP-23", "2026-11-16", 1, -0.3, "CAL-A")], "analyst")
    db.commit()
    job = _run(db, dataset, None)
    db.commit()

    lease = execution.claim()
    assert lease is not None
    assert lease[4] == first.version
    db.expire_all()
    assert db.get(Run, job.id).calibration_version == first.version
