"""统一研判入口：输入代码 → 自动判定体系 → 路由到对应系统出报告。

判定逻辑（两套体系隔离的自动分流）：
- 【妖股打板】今日在涨停池(连板≥1) 或 近10日涨停≥2次 或 近5日涨停且近20日涨幅>50%
  → 走 dragon_board（情绪周期+连板+封板强度+严格-5%止损），绝不用均线趋势
- 【趋势主线】其余 → 走 pro_report 专业版10行表（技术硬门槛+基本面定仓位）

用法：
    from src import analyze
    print(analyze.analyze("002674", date="20260625"))     # 自动判定
    print(analyze.analyze("600362", "江西铜业", theme="铜"))
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from . import stock_deepdive as sd
from . import pro_report
from . import dragon_board as db


def _limit_pct(code: str) -> float:
    """涨停阈值(%)：创业板/科创20、北交所30、其余10。"""
    c = str(code)
    if c[:1] in ("3",) and c[:3] in ("300", "301") or c[:3] in ("688", "689"):
        return 19.5
    if c[:1] in ("8", "4") or c[:2] in ("43", "83", "87", "92"):
        return 29.5
    return 9.7


def _recent_limit_ups(d, code: str, lookback: int = 10) -> int:
    """近 lookback 交易日涨停次数。"""
    if d is None or len(d) < lookback + 1:
        lookback = max(1, len(d) - 1)
    thr = _limit_pct(code)
    cnt = 0
    closes = d["close"].tolist()
    for i in range(len(d) - lookback, len(d)):
        if i <= 0:
            continue
        chg = (float(closes[i]) / float(closes[i - 1]) - 1) * 100
        if chg >= thr:
            cnt += 1
    return cnt


def classify(code: str, name: str = "", date: Optional[str] = None) -> Dict:
    """判定体系。返回 {体系, 理由, 在涨停池, 连板}。"""
    date = date or datetime.now().strftime("%Y%m%d")
    # 1) 今日涨停池
    try:
        senti = db.market_sentiment(date)
        p = db.find_in_pool(code, senti)
    except Exception:  # noqa: BLE001
        senti, p = None, None
    if p:
        lbc = p.get("lbc") or 0
        cap_yi = (p.get("ltsz") or 0) / 1e8
        # 连板≥2=真妖股；单日涨停的大盘股(>300亿)按趋势看，不算打板标的
        if lbc >= 2 or cap_yi < 300:
            return {"体系": "妖股打板", "理由": f"今日涨停(连板{lbc}，流通{cap_yi:.0f}亿)",
                    "在涨停池": True, "连板": lbc, "_senti": senti}
        return {"体系": "趋势主线", "理由": f"今日涨停但大盘股(流通{cap_yi:.0f}亿)，按趋势看",
                "在涨停池": False, "连板": lbc, "_senti": senti}
    # 2) 近期涨停频率（K线）+ 流通市值闸门（妖股多为中小盘）
    d = sd._fetch(code)
    if d is not None:
        lu10 = _recent_limit_ups(d, code, 10)
        lu5 = _recent_limit_ups(d, code, 5)
        closes = d["close"].tolist()
        chg20 = (float(closes[-1]) / float(closes[-21]) - 1) * 100 if len(closes) > 21 else 0
        cap_yi = None
        if "outstanding_share" in d.columns:
            osh = float(d.iloc[-1]["outstanding_share"])
            if osh == osh:  # 非NaN
                cap_yi = osh * float(closes[-1]) / 1e8
        small = (cap_yi is None) or (cap_yi < 300)  # 市值未知时不放行大盘豁免
        if lu10 >= 2 and small:
            return {"体系": "妖股打板", "理由": f"近10日涨停{lu10}次(中小盘题材连板特征)",
                    "在涨停池": False, "连板": 0, "_senti": senti}
        if lu5 >= 1 and chg20 > 50 and small:
            return {"体系": "妖股打板", "理由": f"近5日涨停+近20日涨{chg20:.0f}%(题材脉冲)",
                    "在涨停池": False, "连板": 0, "_senti": senti}
    return {"体系": "趋势主线", "理由": "无连板/涨停特征，按趋势+基本面研判",
            "在涨停池": False, "连板": 0, "_senti": senti}


def analyze(code: str, name: str = "", date: Optional[str] = None,
            theme: Optional[str] = None) -> str:
    """统一入口：自动判定体系并出对应报告。"""
    date = date or datetime.now().strftime("%Y%m%d")
    if not name:
        name = sd._name(code)
    cls = classify(code, name, date)
    sys_name = cls["体系"]
    banner = (f"# 🧭 {name} {code} 统一研判\n"
              f"> **自动判定体系：【{sys_name}】** — {cls['理由']}\n"
              f"> （两套体系隔离：妖股走打板/趋势走专业版，绝不混用）\n")

    if sys_name == "妖股打板":
        if cls["在涨停池"]:
            body = db.report_md(code, name, date)
        else:
            # 妖股属性但今日未涨停：给情绪周期 + 等再次涨停启动 + 基本面排雷视角
            senti = cls.get("_senti") or db.market_sentiment(date)
            body = (f"## 🐲 {name} {code} 打板研判（{date}）\n"
                    f"> **市场温度：{senti['温度']}**｜涨停{senti['涨停数']}/最高{senti['最高板']}板/"
                    f"炸板率{senti['炸板率%']}%　→ {senti['建议']}\n\n"
                    f"> ⚠️ 该股近期有连板/涨停特征但**今日未涨停**：打板需等**再次放量涨停启动**才介入；"
                    f"回调期不抄底、不用趋势回踩低吸去接。\n\n"
                    + db.playbook(code, name))
        return banner + "\n" + body

    # 趋势主线 → 专业版10行表
    return banner + "\n" + pro_report.pro_card(code, name, theme=theme)
