"""探针校准单校验、合并与套用。"""

import math
from datetime import date
from decimal import Decimal

from .spec import SPEC


CALIBRATION_FIELDS = SPEC["calibration_fields"]


def key(probe, handoff_date):
    """校准单以探针编号与交接日期定位。"""
    return probe, handoff_date


def _same_content(left, right):
    return (
        Decimal(str(left["offset"])) == Decimal(str(right["offset"]))
        and left["calibration_id"] == right["calibration_id"]
    )


def validate_rows(rows):
    """校验校准明细，同修订内容冲突时整批退回。"""
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("校准明细为空，请导入至少一条探针校准记录。")

    normalized = []
    for index, row in enumerate(rows, start=1):
        context = f"第 {index} 条校准记录"
        if not isinstance(row, dict):
            raise ValueError(f"{context}格式有误，请按校准单模板的列名重新导入。")
        record = {}
        for field in CALIBRATION_FIELDS:
            value = row.get(field["key"])
            if field["type"] in ("string", "date"):
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{context}缺少「{field['label']}」，请补填后重新导入。")
                if field["type"] == "date":
                    try:
                        if date.fromisoformat(value).isoformat() != value:
                            raise ValueError
                    except ValueError:
                        raise ValueError(f"{context}的交接日期有误，请填写有效的 YYYY-MM-DD 日期。") from None
                record[field["key"]] = value.strip()
            elif field["type"] == "int":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f"{context}的「{field['label']}」须为整数。")
                record[field["key"]] = value
            elif field["type"] == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"{context}的「{field['label']}」须为数值。")
                record[field["key"]] = float(value)
            else:
                raise ValueError(f"{context}的「{field['label']}」类型无法识别。")
            if field.get("min") is not None and record[field["key"]] < field["min"]:
                raise ValueError(f"{context}的「{field['label']}」须不小于 {field['min']}，请修正后重试。")
            if field.get("max") is not None and record[field["key"]] > field["max"]:
                raise ValueError(f"{context}的「{field['label']}」须不大于 {field['max']}，请修正后重试。")
        normalized.append(record)

    by_key = {}
    for record in normalized:
        by_key.setdefault(key(record["probe"], record["handoff_date"]), []).append(record)
    for (probe, handoff_date), group in by_key.items():
        revisions = {}
        for record in group:
            revision = record["revision"]
            if revision in revisions and not _same_content(revisions[revision], record):
                raise ValueError(
                    f"探针 {probe} 在 {handoff_date} 的修订 {revision} 出现多条内容不同的校准单，"
                    "同修订冲突已整批退回，请核对后重新导入。"
                )
            revisions.setdefault(revision, record)
    return normalized


def merge(existing, incoming):
    """把新批次并入当前校准。返回 (变更列表, 忽略数)。

    existing: {(probe, date): {revision, offset, calibration_id}}
    同修订但内容不同视为冲突，整批退回；晚到的旧修订不覆盖已生效修订。
    """
    grouped = {}
    for record in incoming:
        grouped.setdefault(key(record["probe"], record["handoff_date"]), []).append(record)

    changes = []
    ignored = 0
    for item_key, group in grouped.items():
        current = existing.get(item_key)
        if current is not None:
            same_revision = [row for row in group if row["revision"] == current["revision"]]
            for record in same_revision:
                if not _same_content(record, current):
                    raise ValueError(
                        f"探针 {record['probe']} 在 {record['handoff_date']} 已有修订 "
                        f"{current['revision']}（校准单 {current['calibration_id']}，偏差 {current['offset']}），"
                        f"本次同修订内容为校准单 {record['calibration_id']}、偏差 {record['offset']}，"
                        "同修订冲突已整批退回。"
                    )
        candidate = max(group, key=lambda row: row["revision"])
        if current is None or candidate["revision"] > current["revision"]:
            changes.append(candidate)
            ignored += len(group) - 1
        else:
            ignored += len(group)
    return changes, ignored


def index(entries):
    """把生效校准整理为 {(probe, date): entry}。"""
    return {key(entry["probe"], entry["handoff_date"]): entry for entry in entries or []}


def calibrated_temperature(temperature, offset):
    return float(Decimal(str(temperature)) + Decimal(str(offset)))
