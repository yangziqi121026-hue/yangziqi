"""⑧ 题材预警回测（P3）。

记录每次题材/盘中预警，回算收益与胜率，统计哪些题材有效、哪些容易骗炮。
留痕：reports/题材预警日志.jsonl（gitignored，与 review_log 同规范）。

- log_alert(theme, strength, code, name, price): 记录一次预警
- evaluate(): 给每条补 当日/次日/3日收益 + 区间最大回撤（基于日线）
- theme_scorecard(): 按题材聚合 胜率/平均收益/骗炮率 → 哪些题材最有效

注：1小时级收益需分钟数据，当前用日线做 当日/次日/3日；1h 字段预留(None)，后续接分钟K线再补。
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Dict, List, Optional

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LOG = os.path.join(_BASE, "reports", "题材预警日志.jsonl")


def _ensure():
    os.makedirs(os.path.dirname(_LOG), exist_ok=True)


def log_alert(theme: str, strength, code: str, name: str = "",
              price: Optional[float] = None, ts: Optional[str] = None,
              note: str = "") -> Dict:
    """记录一次题材/盘中预警。strength 可为 强/中/弱 或数值。"""
    _ensure()
    rec = {"ts": ts or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "date": (ts or datetime.now().strftime("%Y-%m-%d"))[:10],
           "theme": theme, "strength": strength, "code": str(code),
           "name": name, "price": price, "note": note}
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def _load() -> List[Dict]:
    if not os.path.exists(_LOG):
        return []
    out = []
    with open(_LOG, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def _returns(code: str, alert_date: str, alert_price: Optional[float]) -> Dict:
    """基于日线算 当日/次日/3日收益 + 3日内最大回撤。"""
    try:
        from . import em_fetch
        import pandas as pd
        pd.set_option("future.infer_string", False)
        d = em_fetch.daily(code)
        if d is None or d.empty:
            return {}
        d = d.reset_index(drop=True)
        dates = [str(x)[:10] for x in d["date"].tolist()]
        # 找预警日（或之后第一个交易日）
        idx = next((i for i, dd in enumerate(dates) if dd >= alert_date), None)
        if idx is None:
            return {}
        base = alert_price if alert_price else float(d.iloc[idx]["close"])

        def ret(j):
            if idx + j >= len(d):
                return None
            return round((float(d.iloc[idx + j]["close"]) / base - 1) * 100, 2)

        # 3日内最低 → 最大回撤
        window = d.iloc[idx:idx + 4]
        mdd = round((float(window["low"].min()) / base - 1) * 100, 2) if len(window) else None
        return {"当日%": ret(0), "次日%": ret(1), "3日%": ret(3), "最大回撤%": mdd,
                "1h%": None}  # 1h 需分钟数据，预留
    except Exception:  # noqa: BLE001
        return {}


def evaluate() -> List[Dict]:
    """给每条预警补收益。返回带收益的记录列表。"""
    rows = _load()
    for r in rows:
        r.update(_returns(r["code"], r["date"], r.get("price")))
    return rows


def theme_scorecard() -> List[Dict]:
    """按题材聚合：次数/胜率(次日为正)/平均次日%/平均3日%/骗炮率。"""
    rows = [r for r in evaluate() if r.get("次日%") is not None]
    by: Dict[str, List[Dict]] = {}
    for r in rows:
        by.setdefault(r["theme"], []).append(r)
    cards = []
    for theme, rs in by.items():
        n = len(rs)
        win = sum(1 for r in rs if (r.get("次日%") or 0) > 0)
        fake = sum(1 for r in rs if (r.get("当日%") or 0) > 2 and (r.get("次日%") or 0) < 0)
        cards.append({
            "题材": theme, "预警次数": n,
            "次日胜率%": round(win / n * 100, 1),
            "平均次日%": round(sum(r.get("次日%") or 0 for r in rs) / n, 2),
            "平均3日%": round(sum(r.get("3日%") or 0 for r in rs if r.get("3日%") is not None)
                            / max(1, sum(1 for r in rs if r.get("3日%") is not None)), 2),
            "骗炮率%": round(fake / n * 100, 1),
        })
    return sorted(cards, key=lambda x: x["平均3日%"], reverse=True)


def scorecard_md() -> str:
    cards = theme_scorecard()
    if not cards:
        return "### 🎯 题材预警成绩单\n> 暂无足够预警记录（先用 log_alert 积累）"
    lines = ["### 🎯 题材预警成绩单（按平均3日收益排序）",
             "| 题材 | 次数 | 次日胜率 | 平均次日 | 平均3日 | 骗炮率 |",
             "|---|---|---|---|---|---|"]
    for c in cards:
        lines.append(f"| {c['题材']} | {c['预警次数']} | {c['次日胜率%']}% | "
                     f"{c['平均次日%']}% | {c['平均3日%']}% | {c['骗炮率%']}% |")
    lines.append("> 骗炮率=当日冲高>2%但次日收跌的比例；高骗炮率题材=容易追高被套。")
    return "\n".join(lines)
