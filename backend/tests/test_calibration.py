from decimal import Decimal

import pytest

from src.domain import calibration
from src.domain.analysis import analyze
from src.domain.demo import demo_calibration_rows, demo_rows
from src.services import calibrations


def rows(*items):
    return calibration.validate_rows([
        {"probe": probe, "handoff_date": day, "revision": revision,
         "offset": offset, "calibration_id": calibration_id}
        for probe, day, revision, offset, calibration_id in items
    ])


def test_overlapping_calibrations_keep_highest_revision():
    incoming = rows(
        ("TP-23", "2026-11-16", 1, -0.3, "CAL-A"),
        ("TP-23", "2026-11-16", 2, -0.6, "CAL-B"),
    )
    changes, ignored = calibration.merge({}, incoming)
    assert len(changes) == 1
    assert changes[0]["revision"] == 2
    assert changes[0]["offset"] == -0.6
    assert ignored == 1


def test_same_revision_conflict_rejects_whole_batch():
    with pytest.raises(ValueError, match="同修订冲突"):
        calibration.validate_rows([
            {"probe": "TP-23", "handoff_date": "2026-11-16", "revision": 2, "offset": -0.6, "calibration_id": "CAL-A"},
            {"probe": "TP-23", "handoff_date": "2026-11-16", "revision": 2, "offset": -0.4, "calibration_id": "CAL-B"},
        ])


def test_same_revision_identical_rows_are_deduplicated():
    changes, ignored = calibration.merge({}, rows(
        ("TP-23", "2026-11-16", 2, -0.6, "CAL-A"),
        ("TP-23", "2026-11-16", 2, -0.6, "CAL-A"),
    ))
    assert len(changes) == 1
    assert ignored == 1


def test_late_old_revision_does_not_overwrite_newer():
    current = calibration.index([{"probe": "TP-23", "handoff_date": "2026-11-16",
                                  "revision": 2, "offset": -0.6, "calibration_id": "CAL-B"}])
    changes, ignored = calibration.merge(current, rows(("TP-23", "2026-11-16", 1, -0.3, "CAL-A")))
    assert changes == []
    assert ignored == 1


def test_late_same_revision_with_different_content_conflicts():
    current = calibration.index([{"probe": "TP-23", "handoff_date": "2026-11-16",
                                  "revision": 2, "offset": -0.6, "calibration_id": "CAL-B"}])
    with pytest.raises(ValueError, match="同修订冲突"):
        calibration.merge(current, rows(("TP-23", "2026-11-16", 2, -0.4, "CAL-C")))


def test_apply_batch_is_atomic_and_versioned(db):
    first, created = calibrations.apply_batch(db, "第一批", "a.csv", rows(
        ("TP-23", "2026-11-16", 2, -0.3, "CAL-A"),
        ("TP-31", "2026-11-14", 1, 0.4, "CAL-C"),
    ), "analyst")
    db.commit()
    assert created and first.version == 1
    assert calibrations.current_version(db) == 1

    # 冲突批次整批退回，当前版本保持不变。
    with pytest.raises(ValueError, match="同修订冲突"):
        calibrations.apply_batch(db, "冲突批", "b.csv", rows(
            ("TP-23", "2026-11-16", 2, -0.5, "CAL-X"),
            ("TP-31", "2026-11-14", 1, 0.4, "CAL-C"),
        ), "analyst")
    db.rollback()
    assert calibrations.current_version(db) == 1
    assert set(calibrations.effective_entries(db, 1)) == {
        ("TP-23", "2026-11-16"), ("TP-31", "2026-11-14")}

    # 晚到的旧修订不覆盖已生效的新修订，也不报错。
    second, created = calibrations.apply_batch(db, "旧修订", "c.csv", rows(
        ("TP-23", "2026-11-16", 1, -0.1, "CAL-OLD"),
        ("TP-23", "2026-11-15", 3, -0.2, "CAL-D"),
    ), "analyst")
    db.commit()
    assert created
    effective = calibrations.effective_entries(db, second.version)
    assert effective[("TP-23", "2026-11-16")]["offset"] == -0.3
    assert effective[("TP-23", "2026-11-16")]["revision"] == 2
    assert effective[("TP-23", "2026-11-15")]["revision"] == 3


def test_snapshot_uses_version_at_launch(db):
    first, _ = calibrations.apply_batch(db, "v1", "a.csv", rows(
        ("TP-23", "2026-11-16", 1, -0.3, "CAL-A"),
    ), "analyst")
    db.commit()
    launch_version = first.version
    launch_snapshot = calibrations.snapshot(db, launch_version)

    calibrations.apply_batch(db, "v2", "b.csv", rows(
        ("TP-23", "2026-11-16", 2, -0.9, "CAL-B"),
    ), "analyst")
    db.commit()

    # 发起时锁定的快照不随后续导入变化。
    assert launch_snapshot[("TP-23", "2026-11-16")]["offset"] == -0.3
    assert calibrations.snapshot(db, launch_version)[("TP-23", "2026-11-16")]["offset"] == -0.3
    assert calibrations.snapshot(db, 2)[("TP-23", "2026-11-16")]["offset"] == -0.9


def test_analysis_orders_raw_and_calibrated_temperature():
    cal = calibration.index(calibration.validate_rows(demo_calibration_rows()))
    result = analyze(demo_rows(), {}, cal, 3)
    queue = result["tables"][3]["rows"]
    row = next(item for item in queue if item["handoff_id"] == "MY-20261116-S-P-03")
    assert row["raw_temperature"] == 8.1
    assert row["temperature"] == Decimal("8.1") - Decimal("0.6")
    assert row["calibration_id"] == "CAL-2611-23-R2"
    assert row["calibration_revision"] == 2


def test_uncalibrated_readings_are_listed_and_excluded_from_rate():
    cal = calibration.index(calibration.validate_rows(demo_calibration_rows()))
    result = analyze(demo_rows(), {}, cal, 3)
    missing = result["tables"][4]["rows"]
    assert missing and all(item["probe"] == "TP-17" and item["handoff_date"] == "2026-11-14" for item in missing)
    calibrated = next(metric for metric in result["metrics"] if metric["label"] == "已校准")
    assert calibrated["value"] == 48
    east_early = next(row for row in result["tables"][0]["rows"]
                      if row["route"] == "东线" and row["shift"] == "早班")
    assert east_early["count"] == 6
    assert east_early["missing"] == 3
    # 缺校准读数不进入越界率分母：东线午班 3 条已校准全部偏热，越界率仍是 3/6。
    east_late = next(row for row in result["tables"][0]["rows"]
                     if row["route"] == "东线" and row["shift"] == "午班")
    assert east_late["count"] == 6
    assert east_late["missing"] == 3
    assert east_late["warm"] == 3
    assert east_late["rate"] == "50.0%"


def test_ensure_state_is_idempotent(db, monkeypatch):
    from src.services import calibrations
    calibrations.ensure_state(db)
    calibrations.ensure_state(db)
    db.flush()
    from src.models.calibration import CalibrationState
    from sqlalchemy import select, func
    assert db.scalar(select(func.count()).select_from(CalibrationState)) == 1
    assert calibrations.current_version(db) == 0
