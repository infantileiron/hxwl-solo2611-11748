"""交接读数校验、分布计算及巡检清单。"""

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, ROUND_FLOOR
from statistics import fmean, pstdev

from .spec import SPEC


_TEXT_FIELDS = tuple(field for field in SPEC["fields"] if field["type"] == "string")
_SHIFT_OPTIONS = next(field["options"] for field in SPEC["fields"] if field["key"] == "shift")
_TEMPERATURE_FIELD = next(field for field in SPEC["fields"] if field["key"] == "temperature")

_RISK_COLUMNS = (
    ("count", "交接数"),
    ("p05", "P05（°C）"),
    ("p50", "P50（°C）"),
    ("p95", "P95（°C）"),
    ("cold", "偏冷数"),
    ("warm", "偏热数"),
    ("rate", "越界率"),
    ("max_delta", "最远越界（°C）"),
    ("next_step", "复核建议"),
)
_INSPECTION_COLUMNS = (
    ("handoff_id", "交接单号"),
    ("handoff_date", "交接日期"),
    ("route", "路线"),
    ("shift", "班次"),
    ("store", "门店"),
    ("batch", "馅料批次"),
    ("probe", "探针"),
    ("temperature", "点温（°C）"),
    ("direction", "越界方向"),
    ("delta", "越界幅度（°C）"),
    ("next_step", "现场巡检"),
)


def _bounded_number(value, field, context):
    value_type = (int,) if field["type"] == "int" else (int, float)
    if type(value) not in value_type or not field["min"] <= value <= field["max"]:
        unit = "整数" if field["type"] == "int" else "数值"
        raise ValueError(
            f"{context}的「{field['label']}」须为 {field['min']} 至 {field['max']} 的{unit}，请修正后重试。"
        )
    return value


def validate_rows(rows):
    """校验并返回独立的规范化读数，供导入与复核共用。"""
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("交接明细为空，请导入至少一条到店点温记录。")

    normalized = []
    seen = {}
    for index, row in enumerate(rows, start=1):
        context = f"第 {index} 条交接记录"
        if not isinstance(row, dict):
            raise ValueError(f"{context}格式有误，请按样例 CSV 的列名重新导入。")

        record = {}
        for field in _TEXT_FIELDS:
            value = row.get(field["key"])
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{context}缺少「{field['label']}」，请补填后重新导入。")
            record[field["key"]] = value.strip()

        handoff_id = record["handoff_id"]
        unique_id = handoff_id.casefold()
        if unique_id in seen:
            raise ValueError(
                f"{context}的交接单号「{handoff_id}」与第 {seen[unique_id]} 条重复，请保留该交接单的唯一读数。"
            )
        seen[unique_id] = index
        context = f"{context}（{handoff_id}）"

        raw_date = row.get("handoff_date")
        try:
            if not isinstance(raw_date, str) or date.fromisoformat(raw_date).isoformat() != raw_date:
                raise ValueError
        except ValueError:
            raise ValueError(f"{context}的交接日期有误，请填写有效的 YYYY-MM-DD 日期。") from None
        record["handoff_date"] = raw_date

        shift = row.get("shift")
        if shift not in _SHIFT_OPTIONS:
            raise ValueError(f"{context}的配送班次有误，请填写「早班」或「午班」。")
        record["shift"] = shift
        record["temperature"] = _bounded_number(row.get("temperature"), _TEMPERATURE_FIELD, context)
        normalized.append(record)
    return normalized


def _run_parameters(params):
    if not isinstance(params, dict):
        raise ValueError("复核参数格式有误，请在温控复核页重新设置。")
    values = {}
    for field in SPEC["params"]:
        key = field["key"]
        value = params.get(key, field["default"])
        if field["type"] in ("number", "int"):
            value = _bounded_number(value, field, "复核参数")
        elif field["type"] == "select" and value not in field["options"]:
            raise ValueError("指定班次无效，请选择「全部班次」、「早班」或「午班」。")
        elif field["type"] == "string":
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise ValueError("指定路线须使用交接明细中的路线名称，留空可复核全部路线。")
            value = value.strip()
        values[key] = value
    if values["lower_limit"] >= values["upper_limit"]:
        raise ValueError("温区下限须小于上限，请修改可接受温区后重跑。")
    return values


def _quantile(sorted_values, percentile):
    index, fraction = divmod((len(sorted_values) - 1) * percentile, 100)
    if fraction == 0:
        return sorted_values[index]
    low, high = sorted_values[index:index + 2]
    return low + fraction * (high - low) / 100


def _format_decimal(value):
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _histogram(temperatures, width):
    step = Decimal(str(width))
    counts = Counter(
        int((Decimal(str(value)) / step).to_integral_value(rounding=ROUND_FLOOR))
        for value in temperatures
    )
    return {
        "title": "到店点温直方图（°C）",
        "kind": "bar",
        "series": [
            {
                "label": f"[{_format_decimal(bucket * step)}, {_format_decimal((bucket + 1) * step)})",
                "value": counts[bucket],
            }
            for bucket in range(min(counts), max(counts) + 1)
        ],
    }


def _inspection(reading, lower, upper):
    temperature = Decimal(str(reading["temperature"]))
    if temperature < lower:
        return {
            **reading, "direction": "偏冷", "delta": float(lower - temperature),
            "next_step": "核对货箱是否贴近冷风口或冰板，换已校验探针复测同批次并回填。",
        }
    if temperature > upper:
        return {
            **reading, "direction": "偏热", "delta": float(temperature - upper),
            "next_step": "查卸货口停留和箱盖闭合记录，换已校验探针复测同批次并回填。",
        }
    return None


def _summarize_groups(readings, inspections, keys, min_size):
    groups = defaultdict(list)
    for reading in readings:
        groups[tuple(reading[key] for key in keys)].append(reading)

    summaries = []
    for labels, group in groups.items():
        temperatures = sorted(reading["temperature"] for reading in group)
        exceptions = [inspections[reading["handoff_id"]] for reading in group if reading["handoff_id"] in inspections]
        cold = sum(item["direction"] == "偏冷" for item in exceptions)
        warm = len(exceptions) - cold
        count = len(group)
        enough = count >= min_size
        if exceptions:
            next_step = "逐单复测，补齐本组交接样本。" if not enough else "按越界清单逐单排查。"
        else:
            next_step = "补齐本组交接样本后重跑。" if not enough else "按常规频率抽查。"
        summaries.append({
            **dict(zip(keys, labels)),
            "count": count,
            "p05": round(_quantile(temperatures, 5), 2) if enough else "样本不足",
            "p50": round(_quantile(temperatures, 50), 2) if enough else "样本不足",
            "p95": round(_quantile(temperatures, 95), 2) if enough else "样本不足",
            "cold": cold,
            "warm": warm,
            "rate": f"{len(exceptions) / count:.1%}",
            "max_delta": max((item["delta"] for item in exceptions), default=0),
            "next_step": next_step,
        })
    return sorted(summaries, key=lambda row: (
        -(row["cold"] + row["warm"]) / row["count"], -row["max_delta"], -row["count"],
        *(row[key] for key in keys),
    ))


def _table(title, columns, rows):
    return {
        "title": title,
        "columns": [{"key": key, "label": label} for key, label in columns],
        "rows": rows,
    }


def analyze(rows, params):
    readings = validate_rows(rows)
    options = _run_parameters(params)
    route_scope = options["route_scope"]
    shift_scope = options["shift_scope"]
    selected = [
        reading for reading in readings
        if (not route_scope or reading["route"] == route_scope)
        and (shift_scope == "全部班次" or reading["shift"] == shift_scope)
    ]
    scope = f"{route_scope or '全部路线'} · {shift_scope}"
    if not selected:
        available = "、".join(sorted({reading["route"] for reading in readings}))
        raise ValueError(f"「{scope}」筛不到交接读数，请核对班次或调整路线。明细中的路线有 {available}。")

    lower = Decimal(str(options["lower_limit"]))
    upper = Decimal(str(options["upper_limit"]))
    inspections = {}
    for reading in selected:
        item = _inspection(reading, lower, upper)
        if item is not None:
            inspections[item["handoff_id"]] = item
    queue = sorted(inspections.values(), key=lambda item: (-item["delta"], item["handoff_date"], item["handoff_id"]))

    temperatures = sorted(reading["temperature"] for reading in selected)
    min_size = options["min_group_size"]
    routes = _summarize_groups(selected, inspections, ("route",), min_size)
    shifts = _summarize_groups(selected, inspections, ("shift",), min_size)
    route_shifts = _summarize_groups(selected, inspections, ("route", "shift"), min_size)
    sparse_groups = sum(row["count"] < min_size for row in route_shifts)
    cold = sum(item["direction"] == "偏冷" for item in queue)
    warm = len(queue) - cold
    note = (
        f"{scope}纳入 {len(selected)}/{len(readings)} 条交接。"
        f"温区为 {_format_decimal(lower)} 至 {_format_decimal(upper)} °C，含上下限。"
        "读数为收货点测。"
    )
    if sparse_groups:
        note += f" 有 {sparse_groups} 个路线班次组少于 {min_size} 条，分组分位标为样本不足。"

    if queue:
        focus = route_shifts[0]
        headline = (
            f"发现 {len(queue)} 条温度越界，{focus['route']}{focus['shift']}的越界率最高"
            f"（{focus['cold'] + focus['warm']}/{focus['count']}）。"
        )
        first = queue[0]
        rerun = (
            f"优先复测「{first['route']}」{first['shift']}的交接单 {first['handoff_id']}，"
            "回填新读数与探针编号。"
        )
        if route_scope == focus["route"] and shift_scope == focus["shift"]:
            rerun += "更新交接明细后，沿用当前温区与筛选重跑。"
        else:
            rerun += f"在温控复核页指定「{focus['route']}」和「{focus['shift']}」，沿用温区重跑。"
    else:
        headline = f"{len(selected)} 条交接均落在当前温区。"
        rerun = "下一批到货后补录交接单，沿用温区与筛选重跑，核对分位和越界计数。"
    if sparse_groups:
        rerun += " 对样本不足的班次补录该路线的交接单后再比较分位。"

    tables = [
        _table("路线 × 班次尾部风险", (("route", "路线"), ("shift", "班次")) + _RISK_COLUMNS, route_shifts),
        _table("路线尾部风险", (("route", "路线"),) + _RISK_COLUMNS, routes),
        _table("班次尾部风险", (("shift", "班次"),) + _RISK_COLUMNS, shifts),
        _table("越界交接巡检清单", _INSPECTION_COLUMNS, queue),
    ]
    return {
        "state": "warning" if queue or sparse_groups else "ok",
        "headline": headline,
        "note": note,
        "metrics": [
            {"label": "纳入交接", "value": len(selected), "detail": f"整份明细 {len(readings)} 条"},
            {"label": "温度越界", "value": len(queue), "detail": f"偏冷 {cold} 条 · 偏热 {warm} 条 · 越界率 {len(queue) / len(selected):.1%}"},
            {"label": "平均点温（°C）", "value": round(fmean(temperatures), 2), "detail": f"总体标准差 {pstdev(temperatures):.2f} °C"},
            {"label": "P05（°C）", "value": round(_quantile(temperatures, 5), 2), "detail": f"最低 {temperatures[0]:g} °C"},
            {"label": "P50（°C）", "value": round(_quantile(temperatures, 50), 2), "detail": "交接点温中位数"},
            {"label": "P95（°C）", "value": round(_quantile(temperatures, 95), 2), "detail": f"最高 {temperatures[-1]:g} °C"},
        ],
        "tables": tables,
        "charts": [_histogram(temperatures, options["bin_width"])],
        "sections": [{"title": "重跑与现场复测", "text": rerun}],
    }
