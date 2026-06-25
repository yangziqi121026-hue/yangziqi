"""⑤ 行业价格监控（P5）· 混合方案。

数据可得性（已实测）：
- 【自动·Sina期货/上金所】铜铝锌铅镍/黄金白银/原油/碳酸锂/尿素 → 日线现价+周期判断
- 【联网检索】DRAM/NAND/DDR5/HBM、稀土/钨钼锗镓锑、制冷剂、电子特气、高纯四氯化硅、
  氟化液、磷钾肥 → 无期货，返回检索标记+建议query（assistant 跑 WebSearch 后填 PRICE_OVERRIDE）
- 【映射】品种→A股受益公司（curated，可维护）

industry_score(code): 反查个股关联品种→是否上涨周期→行业景气分（供 fundamental_score）。
无关联品种的纯技术股返回 None（行业景气维不适用，诚实留空）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

# —— 自动 feed：品种 → Sina 期货主连 symbol ——
FUTURES = {
    "铜": "CU0", "铝": "AL0", "锌": "ZN0", "铅": "PB0", "镍": "NI0",
    "黄金": "AU0", "白银": "AG0", "原油": "SC0", "碳酸锂": "LC0", "尿素": "UR0",
}

# —— 联网检索品种（无期货）：建议检索 query ——
WEB_ITEMS = {
    "DRAM": "DRAM 现货价格 最新 集邦 TrendForce 涨跌",
    "NAND": "NAND Flash 现货价格 最新 趋势",
    "DDR5": "DDR5 内存 现货价格 最新 涨价",
    "HBM": "HBM 高带宽内存 供需 价格 最新",
    "稀土": "稀土 氧化镨钕 价格 最新 上涨",
    "钨": "钨 APT 钨精矿 价格 最新", "钼": "钼 钼精矿 价格 最新",
    "锗": "锗 价格 最新 管制", "镓": "镓 价格 最新 管制", "锑": "锑 价格 最新",
    "高纯四氯化硅": "高纯四氯化硅 价格 最新 光纤",
    "氟化液": "氟化液 浸没式液冷 价格 供需 最新",
    "制冷剂": "制冷剂 R32 R134a 价格 最新 配额 涨价",
    "电子特气": "电子特气 价格 最新 国产替代",
    "磷肥": "磷酸一铵 磷肥 价格 最新", "钾肥": "氯化钾 钾肥 价格 最新",
}

# —— 品种 → A股受益公司（curated，可维护扩充）——
BENEFIT_MAP: Dict[str, List[str]] = {
    "铜": ["江西铜业", "铜陵有色", "云南铜业", "紫金矿业"],
    "铝": ["云铝股份", "神火股份", "中国铝业", "天山铝业"],
    "锌": ["驰宏锌锗", "中金岭南"], "铅": ["驰宏锌锗", "中金岭南"],
    "镍": ["华友钴业", "格林美"],
    "黄金": ["山东黄金", "中金黄金", "赤峰黄金", "山金国际"],
    "白银": ["盛达资源", "兴业银锡"],
    "原油": ["中国石油", "中国海油", "中国石化"],
    "碳酸锂": ["天齐锂业", "赣锋锂业", "盐湖股份"],
    "尿素": ["华鲁恒升", "鲁西化工"],
    "DRAM": ["香农芯创", "德明利", "佰维存储", "兆易创新"],
    "NAND": ["佰维存储", "江波龙", "德明利"],
    "HBM": ["香农芯创", "雅克科技", "深科技", "太极实业"],
    "稀土": ["北方稀土", "盛和资源", "中国稀土", "广晟有色"],
    "钨": ["厦门钨业", "章源钨业", "中钨高新"],
    "锗": ["驰宏锌锗", "云南锗业"], "镓": ["云南锗业", "中金岭南"],
    "锑": ["湖南黄金", "华钰矿业"],
    "高纯四氯化硅": ["三孚股份", "新安股份"],
    "氟化液": ["巨化股份", "新宙邦"],
    "制冷剂": ["巨化股份", "三美股份", "昊华科技", "东岳集团"],
    "电子特气": ["华特气体", "金宏气体", "南大光电", "凯美特气"],
    "磷肥": ["云天化", "新洋丰"], "钾肥": ["盐湖股份", "亚钾国际"],
}

# 联网检索后由 assistant 写入：{品种: {"price":.., "trend":"上涨/下行/震荡", "note":.., "src":..}}
PRICE_OVERRIDE: Dict[str, Dict] = {}


def _stock_to_items() -> Dict[str, List[str]]:
    rev: Dict[str, List[str]] = {}
    for item, stocks in BENEFIT_MAP.items():
        for s in stocks:
            rev.setdefault(s, []).append(item)
    return rev


def cycle_status(closes: List[float]) -> str:
    """日线收盘序列 → 上涨/筑底/下行/震荡。"""
    if not closes or len(closes) < 60:
        return "数据不足"
    c = closes[-1]
    ma20 = sum(closes[-20:]) / 20
    ma60 = sum(closes[-60:]) / 60
    chg20 = (c / closes[-20] - 1) * 100
    chg60 = (c / closes[-60] - 1) * 100
    if c > ma20 > ma60 and chg20 > 3:
        return f"上涨周期(20日{chg20:+.0f}%/60日{chg60:+.0f}%)"
    if c < ma20 < ma60 and chg20 < -3:
        return f"下行周期(20日{chg20:+.0f}%/60日{chg60:+.0f}%)"
    if chg60 < -8 and chg20 > 0:
        return f"筑底反弹(60日{chg60:+.0f}%/20日{chg20:+.0f}%)"
    return f"震荡(20日{chg20:+.0f}%/60日{chg60:+.0f}%)"


def fetch_auto(item: str) -> Optional[Dict]:
    """自动品种现价 + 周期。失败/非自动品种返回 None。"""
    sym = FUTURES.get(item)
    if not sym:
        return None
    try:
        import pandas as pd
        pd.set_option("future.infer_string", False)
        import akshare as ak
        d = ak.futures_main_sina(symbol=sym)
        closes = [float(x) for x in d["收盘价"].tolist()]
        return {"品种": item, "现价": round(closes[-1], 2),
                "周期": cycle_status(closes), "源": "Sina期货", "可自动": True}
    except Exception:  # noqa: BLE001
        return None


def get_price(item: str) -> Dict:
    """统一取价：自动→override→需检索。"""
    a = fetch_auto(item)
    if a:
        return a
    if item in PRICE_OVERRIDE:
        o = PRICE_OVERRIDE[item]
        return {"品种": item, "现价": o.get("price"), "周期": o.get("trend", "—"),
                "源": o.get("src", "联网检索"), "可自动": False, "note": o.get("note")}
    q = WEB_ITEMS.get(item)
    return {"品种": item, "现价": None, "周期": "需联网检索", "可自动": False,
            "检索query": q or f"{item} 价格 最新"}


def map_to_stocks(item: str) -> List[str]:
    return BENEFIT_MAP.get(item, [])


def industry_score(code: str, name: str = "", full: float = 10) -> Optional[Dict]:
    """个股行业景气分：反查关联品种→上涨周期得高分。无关联品种返回 None（不适用）。"""
    rev = _stock_to_items()
    items = rev.get(name, [])
    if not items:
        return None
    statuses = []
    score_sum, n = 0.0, 0
    for it in items:
        p = get_price(it)
        cyc = p.get("周期", "")
        statuses.append(f"{it}:{cyc}")
        if "上涨周期" in cyc:
            score_sum += 1.0; n += 1
        elif "筑底反弹" in cyc:
            score_sum += 0.65; n += 1
        elif "震荡" in cyc:
            score_sum += 0.5; n += 1
        elif "下行周期" in cyc:
            score_sum += 0.2; n += 1
        # 需检索 不计入 n
    if n == 0:
        return {"score": None, "full": full, "note": f"关联{items}，但价格需联网检索"}
    return {"score": round(score_sum / n * full, 1), "full": full,
            "note": "；".join(statuses)}


def report_md(items: Optional[List[str]] = None) -> str:
    items = items or list(FUTURES.keys())
    lines = ["### 🛢️ 行业价格周期监控", "| 品种 | 现价 | 周期 | 源 | 主要受益股 |", "|---|---|---|---|---|"]
    for it in items:
        p = get_price(it)
        stk = "、".join(map_to_stocks(it)[:3])
        lines.append(f"| {it} | {p.get('现价') or '—'} | {p.get('周期')} | {p.get('源','-')} | {stk} |")
    web = [k for k in WEB_ITEMS if k not in PRICE_OVERRIDE]
    if web:
        lines.append(f"\n> 需联网检索品种（无期货）：{('、'.join(web))}——跑WebSearch后写入 PRICE_OVERRIDE 即纳入。")
    return "\n".join(lines)
