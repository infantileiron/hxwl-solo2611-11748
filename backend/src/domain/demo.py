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
