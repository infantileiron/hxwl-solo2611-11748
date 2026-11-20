"""麦屿烘焙三天的虚拟交接单。"""


_ROUTES = (
    ("E", "东线", ("东桥店", "白榆店"), "TP-17"),
    ("S", "南线", ("丰谷店", "江湾店"), "TP-23"),
    ("N", "北线", ("长松店", "望塔店"), "TP-31"),
)
_SHIFTS = (("A", "早班"), ("P", "午班"))
_TEMPERATURES = {
    ("E", "A"): (3.2, 3.8, 4.1, 3.7, 4.2, 4.6, 4.1, 3.9, 4.4),
    ("E", "P"): (5.1, 5.4, 5.8, 5.4, 5.8, 6.0, 5.3, 6.5, 5.9),
    ("S", "A"): (2.8, 3.3, 3.6, 3.1, 3.5, 4.2, 3.2, 3.4, 3.7),
    ("S", "P"): (5.3, 6.4, 7.3, 5.8, 6.0, 7.8, 5.5, 6.7, 8.1),
    ("N", "A"): (1.3, 2.0, 2.6, 1.8, 2.3, 2.9, 2.2, 2.7, 3.1),
    ("N", "P"): (3.8, 4.3, 4.7, 4.1, 4.3, 4.9, 4.1, 4.6, 5.1),
}


def demo_rows() -> list[dict]:
    rows = []
    for day_index, day in enumerate((14, 15, 16)):
        for route_code, route, stores, probe in _ROUTES:
            for shift_code, shift in _SHIFTS:
                for stop in range(3):
                    rows.append({
                        "handoff_id": f"MY-202611{day}-{route_code}-{shift_code}-{stop + 1:02d}",
                        "handoff_date": f"2026-11-{day}",
                        "route": route,
                        "shift": shift,
                        "store": stores[(day_index + stop) % len(stores)],
                        "batch": f"FL-111{day % 10}-{shift_code}{stop % 2 + 1}",
                        "probe": probe,
                        "temperature": _TEMPERATURES[route_code, shift_code][day_index * 3 + stop],
                    })
    return rows


# 演示校准单：南线探针在 11 月 16 日补到修订 2 的校准单；东线探针 11 月 14 日的校准单还没补到，
# 用于演示缺校准读数单列。南线校正后高尾仍在，北线早班的两条低温记录保持不变。
def demo_calibration_rows() -> list[dict]:
    rows = []
    for day in (14, 15, 16):
        for _route_code, _route, _stores, probe in _ROUTES:
            # 东线探针 11 月 14 日的校准单缺失，对应当天两条班次共 6 条读数。
            if probe == "TP-17" and day == 14:
                continue
            offset = {"TP-23": -0.3, "TP-31": 0.1}.get(probe, 0.2)
            rows.append({
                "probe": probe,
                "handoff_date": f"2026-11-{day}",
                "revision": 1,
                "offset": offset,
                "calibration_id": f"CAL-2611-{probe[-2:]}-R1",
            })
    # 修订 2 的校准单晚到，只覆盖南线 11 月 16 日；同日修订 1 仍保留在历史里。
    rows.append({
        "probe": "TP-23",
        "handoff_date": "2026-11-16",
        "revision": 2,
        "offset": -0.6,
        "calibration_id": "CAL-2611-23-R2",
    })
    return rows
