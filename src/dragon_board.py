"""第二套体系：妖股打板/追涨（与趋势主线严格隔离）。

⚠️ 体系隔离铁律：本系统只用于【题材连板/超跌反弹妖股】，绝不用均线趋势/回踩低吸那套；
趋势主线股也绝不用这套打板规则。两套打法混用是亏损根源。

核心（呼应记忆框架的8维情绪打分+三剧本+硬风控）：
A. 情绪周期(市场温度)：涨停数/连板梯队/炸板率 → 冰点/退潮分歧/修复/主升/亢奋 → 决定能不能打
B. 个股打板分(0-100)：连板梯队 + 封板强度(封流比/首封时间/炸板) + 换手 + 龙虎榜游资 + 排雷
C. 打板专用硬风控：止损-5%或破板即走、单笔≤总仓5%、高位(≥5板)+亢奋只减不加、不接最后一棒
D. 三剧本：乐观(连板)/中性(冲高回落)/悲观(炸板核按钮) + 应对

数据：东财 push2ex 涨停池/炸板池 + datacenter 龙虎榜（实测可连）；分时封单强度需实时，用
封板资金/首封时间近似（盘后口径）。
"""
from __future__ import annotations

from typing import Dict, List, Optional

import requests

_H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_UT = "7eea3edcaed734bea9cbfc24409ed989"


def _pool(date: str, kind: str = "zt") -> List[Dict]:
    """涨停池(zt)/炸板池(zb)。date=YYYYMMDD。"""
    url = ("https://push2ex.eastmoney.com/getTopicZTPool" if kind == "zt"
           else "https://push2ex.eastmoney.com/getTopicZBPool")
    dpt = "wz.ztzt" if kind == "zt" else "wz.zbzt"
    try:
        r = requests.get(url, params={"ut": _UT, "dpt": dpt, "Pageindex": "0",
                                      "pagesize": "300", "sort": "fbt:asc", "date": date},
                         headers=_H, timeout=15)
        return (r.json().get("data") or {}).get("pool") or []
    except Exception:  # noqa: BLE001
        return []


def market_sentiment(date: str) -> Dict:
    """情绪周期/市场温度。date=YYYYMMDD。"""
    zt = _pool(date, "zt")
    zb = _pool(date, "zb")
    n_zt = len(zt)
    n_zb = len(zb)
    lb_list = [p for p in zt if (p.get("lbc") or 0) >= 2]
    n_lb = len(lb_list)
    maxlb = max((p.get("lbc") or 0) for p in zt) if zt else 0
    zb_rate = round(n_zb / (n_zt + n_zb) * 100, 1) if (n_zt + n_zb) else 0.0

    if n_zt < 30:
        temp, advice = "冰点", "❄️ 情绪冰点：不打板，等放量启动信号；空仓为主"
    elif zb_rate > 45:
        temp, advice = "退潮/分歧", "⚠️ 炸板率高、分歧大：只打低位首板/确定性龙头，仓位减半，快进快出"
    elif maxlb >= 6 and n_zt > 70:
        temp, advice = "亢奋(高位)", "🔥 高位亢奋：高标只减不加、不接最后一棒；新仓只做低位补涨"
    elif n_zt >= 50:
        temp, advice = "主升", "🟢 主升期：可打强势板，跟最高板梯队，严守次日不及预期就走"
    else:
        temp, advice = "修复", "🟡 修复期：试探性打低位首板/2板，轻仓，破板即走"

    return {"日期": date, "涨停数": n_zt, "连板数": n_lb, "最高板": maxlb,
            "炸板数": n_zb, "炸板率%": zb_rate, "温度": temp, "建议": advice,
            "_zt_pool": zt}


def find_in_pool(code: str, sentiment: Dict) -> Optional[Dict]:
    for p in sentiment.get("_zt_pool", []):
        if str(p.get("c")) == str(code):
            return p
    return None


def _lhb(code: str, date: str) -> Optional[Dict]:
    """龙虎榜上榜情况（游资活跃度近似：上榜金额/占比）。"""
    try:
        from . import em_f10
        rows = em_f10.report("RPT_DAILYBILLBOARD_DETAILSNEW", code, page_size=1,
                             sort_col="TRADE_DATE")
        if not rows:
            return None
        r = rows[0]
        if str(r.get("TRADE_DATE"))[:10].replace("-", "") != date:
            return None
        return {"上榜原因": r.get("EXPLAIN"),
                "上榜成交占比%": round((r.get("DEAL_AMOUNT_RATIO") or 0), 1),
                "次日涨幅%": r.get("D1_CLOSE_ADJCHRATE")}
    except Exception:  # noqa: BLE001
        return None


def _landmine(code: str, name: str) -> List[str]:
    """打板排雷（只排雷、不做价值判断）：业绩预告负/ST/巨亏。"""
    flags = []
    try:
        from .fundamentals import event_calendar as ec
        fc = ec.forecast(code)
        if fc and str(fc.get("净利变动", "")).startswith("-"):
            flags.append(f"业绩预告负({fc['净利变动']})")
    except Exception:  # noqa: BLE001
        pass
    if "ST" in (name or "").upper():
        flags.append("ST")
    return flags


def board_score(code: str, name: str, date: str, sentiment: Optional[Dict] = None) -> Dict:
    """个股打板分 0-100 + 决策。未涨停则不适用本系统。"""
    s = sentiment or market_sentiment(date)
    p = find_in_pool(code, s)
    if not p:
        return {"适用": False, "note": f"{name} {date}未涨停，不属打板标的（若做趋势用 pro_report）"}

    lbc = p.get("lbc") or 0
    zbc = p.get("zbc") or 0
    hs = (p.get("hs") or 0)
    hs = hs * 100 if hs < 1 else hs   # 换手归一到 %
    fund = p.get("fund") or 0
    ltsz = p.get("ltsz") or 0
    fbt = str(p.get("fbt") or "")        # 首封时间 HHMMSS
    if fbt.isdigit():
        fbt = fbt.zfill(6)               # 9点会丢前导零(92500→092500)
    seal_ratio = round(fund / ltsz * 100, 1) if ltsz else 0  # 封流比%

    score, notes = 50.0, []
    # 连板梯队（低位首/2板容错高；中位3-4板顺势；高位≥5板风险）
    if lbc <= 1:
        score += 10; notes.append("首板(低位,容错高)")
    elif lbc <= 3:
        score += 15; notes.append(f"{lbc}板(中位顺势,梯队较安全)")
    elif lbc == 4:
        score += 5; notes.append("4板(偏高,注意分歧)")
    else:
        score -= 10; notes.append(f"{lbc}板(高位,接最后一棒风险大)")
    # 炸板
    if zbc == 0:
        score += 10; notes.append("零炸板(封板稳)")
    else:
        score -= zbc * 6; notes.append(f"炸板{zbc}次(分歧)")
    # 封流比（封单强度）
    if seal_ratio >= 5:
        score += 12; notes.append(f"封流比{seal_ratio}%(封单强)")
    elif seal_ratio >= 2:
        score += 6; notes.append(f"封流比{seal_ratio}%")
    else:
        score -= 4; notes.append(f"封流比{seal_ratio}%(封单弱)")
    # 首封时间（越早越强；上午10点前=强）
    if fbt and fbt.isdigit() and int(fbt) <= 100000:
        score += 8; notes.append(f"首封{fbt[:2]}:{fbt[2:4]}(早盘秒板)")
    elif fbt and fbt.isdigit() and int(fbt) >= 140000:
        score -= 4; notes.append(f"首封{fbt[:2]}:{fbt[2:4]}(尾盘偷袭,弱)")
    # 换手（5-15%健康；>25%过度分歧）
    if hs > 25:
        score -= 6; notes.append(f"换手{hs:.0f}%(过度分歧)")
    elif 5 <= hs <= 15:
        score += 4; notes.append(f"换手{hs:.0f}%(健康)")
    # 龙虎榜
    lhb = _lhb(code, date)
    if lhb:
        score += 6; notes.append(f"龙虎榜上榜({lhb['上榜原因']})")
    # 排雷
    mines = _landmine(code, name)
    if mines:
        score -= 20; notes.append("⚠️排雷:" + "/".join(mines))

    score = round(max(0, min(100, score)), 1)
    # 决策（叠加情绪周期）
    temp = s["温度"]
    if mines:
        decision = "🚫 排雷否决：有暴雷项，不打"
    elif temp == "冰点":
        decision = "❄️ 情绪冰点，不打板（等启动）"
    elif lbc >= 5 and "亢奋" in temp:
        decision = "🔴 高位高标+情绪亢奋：不接最后一棒，只减不加"
    elif score >= 65:
        decision = "🟢 可打(轻仓≤5%)：" + s["建议"]
    elif score >= 50:
        decision = "🟡 谨慎试(极轻仓):分歧偏大,严守破板即走"
    else:
        decision = "⚠️ 不打:打板分偏低/封板弱"

    return {"适用": True, "code": code, "name": name, "连板": lbc,
            "几天几板": p.get("zttj", {}).get("days") and f"{p['zttj'].get('days')}天{p['zttj'].get('ct')}板",
            "封流比%": seal_ratio, "炸板": zbc, "换手%": round(hs, 1),
            "首封": fbt, "板块": p.get("hybk"), "龙虎榜": lhb,
            "score": score, "notes": notes, "decision": decision, "_pool": p}


def playbook(code: str, name: str) -> str:
    """三剧本应对（打板专用硬风控）。"""
    return (f"**三剧本应对（{name}，打板专用风控）：**\n"
            f"- 🟢乐观(连续涨停)：持有，封单减弱/炸板预警挂出即减半；\n"
            f"- 🟡中性(冲高回落)：冲高乏力/跌破分时均线→**当日走**，不留隔夜；\n"
            f"- 🔴悲观(炸板/核按钮)：破板/低开破昨低→**无条件清，止损-5%封顶**；\n"
            f"- 仓位：单笔≤总仓**5%**（妖股比趋势仓更小）；不接≥5板最后一棒。")


def report_md(code: str, name: str, date: str) -> str:
    s = market_sentiment(date)
    head = (f"## 🐲 {name} {code} 打板/追涨研判（第二套体系·{date}）\n"
            f"> **市场温度：{s['温度']}**｜涨停{s['涨停数']}/连板{s['连板数']}/最高{s['最高板']}板/"
            f"炸板率{s['炸板率%']}%　→ {s['建议']}\n")
    r = board_score(code, name, date, s)
    if not r["适用"]:
        return head + f"\n> {r['note']}"
    lines = [head, "", "| 维度 | 值 |", "|---|---|",
             f"| 连板 | {r['连板']}板 |",
             f"| 封流比 | {r['封流比%']}%（封单强度） |",
             f"| 炸板 | {r['炸板']}次 |",
             f"| 换手 | {r['换手%']}% |",
             f"| 板块 | {r['板块']} |",
             f"| 龙虎榜 | {r['龙虎榜'] or '未上榜'} |",
             f"| **打板分** | **{r['score']}/100** |",
             f"| 明细 | {'；'.join(r['notes'])} |",
             f"| **决策** | **{r['decision']}** |",
             "", playbook(code, name),
             "\n> 第二套体系：只用情绪周期+连板+封板强度+游资，**绝不用均线趋势**；止损-5%铁律。仅研究，不构成投资建议。"]
    return "\n".join(lines)
