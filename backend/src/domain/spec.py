"""冷链交接温度复核的共享页面配置。"""


SPEC = {
    "title": "烘焙门店冷链交接温度复核",
    "short_name": "bakery-cold-chain",
    "subtitle": "核对到店点温，追查偏热与偏冷的交接批次。",
    "organization": "麦屿烘焙配送组，服务六家门店，三条配送路线分早班与午班送达冷藏馅料。",
    "workflow": (
        "门店收货员用随车探针记录冷藏馅料的到店点温，配送组每天把交接单合并成 CSV。"
        "值班员过去在表格中按班次筛选，再在群里逐个追问越界批次。现在由温控复核汇总分布，"
        "将异常读数连同交接单号、门店、批次和探针交给店长与配送巡检员，供复测与巡检排期。"
    ),
    "pains": [
        "平均温度容易掩盖少量偏热交接，也看不出同一天有没有过冷记录。",
        "路线与班次分开筛选时，难以确认高尾集中在哪一个组合。",
        "群内转发读数经常漏掉批次或探针编号，现场要重复查找交接单。",
    ],
    "steps": [
        "11 月 16 日 14:10，将 11 月 14–16 日的门店到货记录整理为「麦屿冷藏馅料交接_20261114-16.csv」。",
        "在「交接明细」导入 CSV，确认三条路线、两个班次共 54 条记录，检查交接单号与探针编号。",
        "在「温控复核」设置 2–6 °C 工作区间、1 °C 分箱和 6 条尾部分位样本下限，运行整批读数。",
        "在「温度分布与巡检」核对直方图是否合计 54 条，查看 P05、P50、P95 和各路线的越界计数。",
        "按路线与班次确认南线午班 9 条中有 5 条高于 6 °C，并查看北线早班的两条低温记录。",
        "将筛选改为南线、午班，沿用同一温区重跑，核对 11 月 16 日南线交接 MY-20261116-S-P-03 的 8.1 °C 读数。",
        "按巡检表安排南线卸货口复测和北线冷风口检查，提交复核处置并注明要回填的交接单号。",
    ],
    "methodology": [
        "每条交接单以一次到店点温计数。先校验整份明细的交接单号、日期、班次和读数，再按路线与班次取交集。",
        "分位用线性插值。读数升序后令 h=(n−1)p，取相邻两项 x[i]、x[i+1]，计算 x[i]+(h−i)(x[i+1]−x[i])，其中 i=⌊h⌋。单条记录的分位等于原读数。",
        "标准差按总体口径计算，即 √(Σ(x−均值)²/n)。直方图从 0 °C 对齐分箱，区间左闭右开，保留观测范围内的空箱。",
        "可接受温区含上下限。偏冷率、偏热率与越界率均以对应分组的全部有效交接为分母。路线、班次及交叉组按越界率、最远越界幅度和样本数降序排列。",
        "分组少于设定样本下限仍展示实测越界与巡检线索，分组分位标记为样本不足。同一 CSV 与参数可得到相同结果，点温用于排查交接，无法还原运输全程温度。",
    ],
    "sample_name": "麦屿冷藏馅料交接_20261114-16.csv",
    "default_dataset": "麦屿烘焙 11 月 14–16 日馅料交接单",
    "entity": "交接读数",
    "run": "温控复核",
    "decision": "复核处置",
    "action": "提交巡检决定",
    "modes": ["安排巡检", "复测待回填", "常规归档"],
    "pages": ["值班总览", "交接明细", "温控复核", "温度分布与巡检"],
    "fields": [
        {"key": "handoff_id", "label": "交接单号", "type": "string", "required": True},
        {"key": "handoff_date", "label": "交接日期", "type": "date", "required": True},
        {"key": "route", "label": "配送路线", "type": "string", "required": True},
        {"key": "shift", "label": "配送班次", "type": "select", "required": True, "options": ["早班", "午班"]},
        {"key": "store", "label": "收货门店", "type": "string", "required": True},
        {"key": "batch", "label": "馅料批次", "type": "string", "required": True},
        {"key": "probe", "label": "探针编号", "type": "string", "required": True},
        {"key": "temperature", "label": "到店点温（°C）", "type": "number", "required": True, "min": -40, "max": 60},
    ],
    "params": [
        {"key": "lower_limit", "label": "温区下限（°C）", "type": "number", "required": True, "min": -40, "max": 60, "default": 2, "help": "低于下限的读数进入偏冷巡检。"},
        {"key": "upper_limit", "label": "温区上限（°C）", "type": "number", "required": True, "min": -40, "max": 60, "default": 6, "help": "高于上限的读数进入偏热巡检。"},
        {"key": "bin_width", "label": "直方图箱宽（°C）", "type": "number", "required": True, "min": 0.5, "max": 10, "default": 1, "help": "箱沿从 0 °C 对齐。归入下界等于该读数的箱。"},
        {"key": "min_group_size", "label": "分位展示样本下限", "type": "int", "required": True, "min": 1, "max": 10000, "default": 6, "help": "小组样本分位暂不展示，越界记录仍进入巡检。"},
        {"key": "route_scope", "label": "指定路线", "type": "string", "required": False, "default": "", "help": "留空复核全部路线，或填写交接明细中的路线名称，如南线。"},
        {"key": "shift_scope", "label": "指定班次", "type": "select", "required": True, "options": ["全部班次", "早班", "午班"], "default": "全部班次"},
    ],
    "fixture": {"route_scope": "南线", "shift_scope": "午班", "upper_limit": 7},
    "axes": "温度直方图横轴为左闭右开的温区（°C），纵轴为交接读数条数。",
}
