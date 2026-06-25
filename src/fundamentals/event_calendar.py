"""⑦ 事件日历（P3）。

个股级（Tier A 东财自动）：
- 财报预约披露日 RPT_PUBLIC_BS_APPOIN
- 业绩预告 RPT_PUBLIC_OP_NEWPREDICT
- 解禁 RPT_LIFT_STAGE
市场级（需联网检索刷新，curated 占位）：
- 产业大会 / 政策会议 / 海外龙头财报 / 商品数据公布

upcoming(code, days): 汇总未来 N 天该股 + 市场重要事件。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .. import em_f10


def _date(s) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.strptime(str(s)[:10], "%Y-%m-%d")
    except ValueError:
        return None


def _f(v):
    try:
        return None if v in (None, "", "-") else float(v)
    except (ValueError, TypeError):
        return None


def earnings_date(code: str) -> Optional[Dict]:
    """下一次财报披露（预约/实际）。"""
    rows = em_f10.report("RPT_PUBLIC_BS_APPOIN", code, page_size=4,
                         sort_col="FIRST_APPOINT_DATE")
    now = datetime.now()
    upcoming = []
    for r in rows:
        appoint = _date(r.get("FIRST_APPOINT_DATE"))
        actual = _date(r.get("ACTUAL_PUBLISH_DATE"))
        if actual is None and appoint and appoint >= now - timedelta(days=1):
            upcoming.append((appoint, r))
    if not upcoming:
        return None
    appoint, r = min(upcoming, key=lambda x: x[0])
    return {"日期": appoint.strftime("%Y-%m-%d"), "类型": r.get("REPORT_TYPE"),
            "年度": r.get("REPORT_YEAR"), "事件": f"{r.get('REPORT_YEAR')}{r.get('REPORT_TYPE')}披露"}


def forecast(code: str) -> Optional[Dict]:
    """最新业绩预告。"""
    rows = em_f10.report("RPT_PUBLIC_OP_NEWPREDICT", code, page_size=1, sort_col="NOTICE_DATE")
    if not rows:
        return None
    r = rows[0]
    lo, hi = _f(r.get("ADD_AMP_LOWER")), _f(r.get("ADD_AMP_UPPER"))
    amp = (f"{lo:.0f}%~{hi:.0f}%" if lo is not None and hi is not None
           else (f"{lo:.0f}%" if lo is not None else "—"))
    return {"公告日": str(r.get("NOTICE_DATE"))[:10], "报告期": str(r.get("REPORT_DATE"))[:10],
            "类型": r.get("PREDICT_FINANCE"), "净利变动": amp}


def unlocks(code: str, days: int = 90) -> List[Dict]:
    """未来 days 天内解禁。"""
    rows = em_f10.report("RPT_LIFT_STAGE", code, page_size=5, sort_col="FREE_DATE", desc=False)
    now = datetime.now()
    out = []
    for r in rows:
        d = _date(r.get("FREE_DATE"))
        if d and now <= d <= now + timedelta(days=days):
            out.append({"日期": d.strftime("%Y-%m-%d"),
                        "解禁市值(亿)": round((_f(r.get("LIFT_MARKET_CAP")) or 0) / 1e8, 2),
                        "事件": f"解禁{round((_f(r.get('LIFT_MARKET_CAP')) or 0)/1e8,1)}亿（{r.get('FREE_SHARES_TYPE')}）"})
    return out


# 市场级事件（curated；建议每周用 WebSearch 刷新一次）
MARKET_EVENTS: List[Dict] = [
    # 示例结构：{"日期":"2026-07-15","类别":"商品数据","事件":"6月DRAM现货均价(集邦)"}
    # 海外龙头财报、政策会议、产业大会、商品数据公布 → 联网检索后填充
]


def market_events(days: int = 7) -> List[Dict]:
    """未来 days 天市场级事件（curated；空则提示用 WebSearch 刷新）。"""
    now = datetime.now()
    out = []
    for e in MARKET_EVENTS:
        d = _date(e.get("日期"))
        if d and now <= d <= now + timedelta(days=days):
            out.append(e)
    return out


def upcoming(code: str, name: str = "", days: int = 7) -> Dict:
    """未来 days 天该股 + 市场事件汇总。"""
    now = datetime.now()
    items: List[Dict] = []
    ed = earnings_date(code)
    if ed:
        d = _date(ed["日期"])
        if d and d <= now + timedelta(days=days):
            items.append({"日期": ed["日期"], "类别": "财报", "事件": ed["事件"]})
    for u in unlocks(code, days=days):
        items.append({"日期": u["日期"], "类别": "解禁", "事件": u["事件"]})
    items += [{"日期": e["日期"], "类别": e.get("类别", "市场"), "事件": e["事件"]}
              for e in market_events(days)]
    items.sort(key=lambda x: x["日期"])
    return {"未来事件": items, "业绩预告": forecast(code),
            "下次财报": ed, "近端解禁": unlocks(code, days=90)}


def report_md(code: str, name: str = "", days: int = 7) -> str:
    u = upcoming(code, name, days)
    lines = [f"### 📅 {name} {code} 事件日历（未来{days}天）"]
    fc = u["业绩预告"]
    if fc:
        lines.append(f"- **业绩预告**（{fc['公告日']}）：{fc['类型']}，净利变动 {fc['净利变动']}")
    if u["下次财报"]:
        lines.append(f"- **下次财报**：{u['下次财报']['日期']} {u['下次财报']['事件']}")
    if u["未来事件"]:
        for e in u["未来事件"]:
            lines.append(f"- ⚠️ {e['日期']}｜{e['类别']}｜{e['事件']}")
    else:
        lines.append(f"- 未来{days}天无重大个股事件")
    nxt = u["近端解禁"]
    if nxt:
        lines.append(f"- 近端解禁：{nxt[0]['日期']}，{nxt[0]['解禁市值(亿)']}亿")
    if not MARKET_EVENTS:
        lines.append("- _市场级事件(政策/产业大会/海外财报/商品数据)：需联网检索刷新 MARKET_EVENTS_")
    return "\n".join(lines)
