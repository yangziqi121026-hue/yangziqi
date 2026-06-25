"""④ 股东 / 筹码面变化追踪（P2）。

数据源：东财 F10 datacenter（已实测可连）
- 股东户数 RPT_F10_EH_HOLDERNUM        → 户数环比(集中/分散)
- 十大流通股东 RPT_F10_EH_FREEHOLDERS   → 新进/增/减 + 基金家数
- 北向持股 RPT_MUTUAL_HOLD_DET          → 持股变化
- 高管增减持 RPT_EXECUTIVE_HOLD_DETAILS → 近期增减持
- 解禁 RPT_LIFT_STAGE                   → 未来解禁
- 融资余额：端点待补（margin() 暂返回 None，不阻塞）

summarize() 输出筹码面评分 0-100 + 流入/流出结论，供 fundamental_score 用。
"""
from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from .. import em_f10


def _f(v) -> Optional[float]:
    try:
        return None if v in (None, "", "-") else float(v)
    except (ValueError, TypeError):
        return None


def holder_num(code: str) -> Dict:
    """股东户数最新 + 环比变化。户数降=筹码集中(利多)，升=分散(利空)。"""
    rows = em_f10.report("RPT_F10_EH_HOLDERNUM", code, page_size=2, sort_col="END_DATE")
    if not rows:
        return {}
    r = rows[0]
    chg = _f(r.get("TOTAL_NUM_RATIO"))  # 户数环比% (+增/-减)
    return {
        "日期": str(r.get("END_DATE"))[:10],
        "户数": int(_f(r.get("HOLDER_TOTAL_NUM")) or 0),
        "户数环比%": chg,
        "户均持股市值": _f(r.get("AVG_HOLD_AMT")),
        "集中度": r.get("HOLD_FOCUS"),
        "判断": ("筹码集中(利多)" if chg is not None and chg < -2
                else "筹码分散(利空)" if chg is not None and chg > 5
                else "基本平稳"),
    }


def free_holders(code: str) -> Dict:
    """十大流通股东变化统计：新进/增持/减持家数 + 机构(基金)家数。"""
    rows = em_f10.report("RPT_F10_EH_FREEHOLDERS", code, page_size=10, sort_col="END_DATE")
    if not rows:
        return {}
    date = str(rows[0].get("END_DATE"))[:10]
    cur = [r for r in rows if str(r.get("END_DATE"))[:10] == date]
    新进 = sum(1 for r in cur if r.get("HOLDNUM_CHANGE_NAME") == "新进")
    增 = sum(1 for r in cur if r.get("HOLDNUM_CHANGE_NAME") == "增加")
    减 = sum(1 for r in cur if r.get("HOLDNUM_CHANGE_NAME") == "减少")
    基金 = sum(1 for r in cur if "基金" in str(r.get("HOLDER_TYPE", "")) or "投资基金" in str(r.get("HOLDER_NEWTYPE", "")))
    净增 = (新进 + 增) - 减
    return {
        "日期": date, "新进": 新进, "增持": 增, "减持": 减, "基金家数": 基金,
        "净增家数": 净增,
        "判断": ("机构增仓(利多)" if 净增 >= 2 else "机构减仓(利空)" if 净增 <= -2 else "变化不大"),
    }


def north_hold(code: str) -> Dict:
    """北向持股最新 + 变化（非北向标的返回空）。"""
    rows = em_f10.report("RPT_MUTUAL_HOLD_DET", code, page_size=2, sort_col="HOLD_DATE",
                         extra_filter="", )
    # 该表用 SECURITY_CODE 过滤
    if not rows:
        rows = em_f10.report("RPT_MUTUAL_HOLD_DET", code, page_size=2, sort_col="HOLD_DATE")
    if not rows:
        return {}
    r = rows[0]
    # 防御性取数：不同版本字段名可能不同
    shares = _f(r.get("HOLD_SHARES")) or _f(r.get("SHARESHOLD")) or _f(r.get("HOLD_NUM"))
    ratio = _f(r.get("TOTAL_SHARES_RATIO")) or _f(r.get("FREESHARES_RATIO")) or _f(r.get("HOLD_RATIO"))
    chg = _f(r.get("HOLD_SHARES_CHANGE")) or _f(r.get("ADD_SHARES_REPADAY"))
    return {"日期": str(r.get("HOLD_DATE"))[:10], "持股(股)": shares,
            "占流通%": ratio, "持股变化": chg,
            "判断": ("北向增持" if chg and chg > 0 else "北向减持" if chg and chg < 0 else "持平/—")}


def insider(code: str, limit: int = 5) -> List[Dict]:
    """近期高管增减持。CHANGE_SHARES>0 增持 / <0 减持。"""
    rows = em_f10.report("RPT_EXECUTIVE_HOLD_DETAILS", code, page_size=limit,
                         sort_col="CHANGE_DATE")
    out = []
    for r in rows:
        sh = _f(r.get("CHANGE_SHARES"))
        out.append({"日期": str(r.get("CHANGE_DATE"))[:10], "姓名": r.get("PERSON_NAME"),
                    "变动股数": sh, "金额": _f(r.get("CHANGE_AMOUNT")),
                    "方向": "增持" if sh and sh > 0 else "减持" if sh and sh < 0 else "—"})
    return out


def unlock(code: str, limit: int = 3) -> List[Dict]:
    """未来/最近解禁批次。"""
    rows = em_f10.report("RPT_LIFT_STAGE", code, page_size=limit, sort_col="FREE_DATE")
    out = []
    for r in rows:
        out.append({"解禁日": str(r.get("FREE_DATE"))[:10],
                    "解禁股(股)": _f(r.get("CURRENT_FREE_SHARES")),
                    "解禁市值": _f(r.get("LIFT_MARKET_CAP")),
                    "类型": r.get("FREE_SHARES_TYPE")})
    return out


def margin(code: str) -> Optional[Dict]:
    """融资余额（端点待补，暂返回 None）。"""
    return None


def summarize(code: str, name: str = "") -> Dict:
    """综合筹码面评分 0-100 + 结论。"""
    hn = holder_num(code)
    fh = free_holders(code)
    nh = north_hold(code)
    ins = insider(code)
    ul = unlock(code)

    score = 50.0  # 中性基准
    notes = []
    # 户数
    chg = hn.get("户数环比%")
    if chg is not None:
        if chg < -5:
            score += 15; notes.append(f"户数{chg:.0f}%大幅集中")
        elif chg < 0:
            score += 8; notes.append(f"户数{chg:.0f}%集中")
        elif chg > 8:
            score -= 12; notes.append(f"户数+{chg:.0f}%明显分散")
        elif chg > 0:
            score -= 5; notes.append(f"户数+{chg:.0f}%略分散")
    # 十大流通
    净增 = fh.get("净增家数")
    if 净增 is not None:
        score += max(-15, min(15, 净增 * 5))
        if 净增:
            notes.append(f"机构净{'增' if 净增>0 else '减'}{abs(净增)}家")
    # 北向
    nc = nh.get("持股变化")
    if nc:
        score += 8 if nc > 0 else -8
        notes.append(nh.get("判断"))
    # 高管
    net_ins = sum((r["变动股数"] or 0) for r in ins)
    if net_ins > 0:
        score += 6; notes.append("高管净增持")
    elif net_ins < 0:
        score -= 8; notes.append("高管净减持")
    # 解禁（未来30天大额）
    for u in ul:
        try:
            dd = (datetime.strptime(u["解禁日"], "%Y-%m-%d") - datetime.now()).days
            if 0 <= dd <= 30 and (u["解禁市值"] or 0) > 1e9:
                score -= 10; notes.append(f"30天内解禁{u['解禁市值']/1e8:.0f}亿")
                break
        except (ValueError, TypeError):
            pass

    score = round(max(0, min(100, score)), 1)
    tier = ("筹码向好" if score >= 62 else "筹码恶化" if score <= 38 else "筹码中性")
    return {"score": score, "tier": tier, "notes": notes,
            "户数": hn, "十大流通": fh, "北向": nh, "高管": ins, "解禁": ul}


def report_md(code: str, name: str = "") -> str:
    s = summarize(code, name)
    lines = [f"### 👥 {name} {code} 股东/筹码面：{s['score']}/100 → **{s['tier']}**",
             f"_{('；'.join(s['notes']) or '无明显异动')}_", ""]
    hn, fh, nh = s["户数"], s["十大流通"], s["北向"]
    if hn:
        lines.append(f"- **股东户数**（{hn.get('日期')}）：{hn.get('户数'):,}户，环比{hn.get('户数环比%')}% → {hn.get('判断')}")
    if fh:
        lines.append(f"- **十大流通股东**（{fh.get('日期')}）：新进{fh.get('新进')}/增{fh.get('增持')}/减{fh.get('减持')}，基金{fh.get('基金家数')}家 → {fh.get('判断')}")
    if nh:
        lines.append(f"- **北向**（{nh.get('日期')}）：{nh.get('判断')}")
    if s["高管"]:
        for r in s["高管"][:3]:
            lines.append(f"- 高管{r['方向']}：{r['姓名']} {r['变动股数']}股（{r['日期']}）")
    if s["解禁"]:
        u = s["解禁"][0]
        lines.append(f"- 下次解禁：{u['解禁日']}，{(u['解禁市值'] or 0)/1e8:.1f}亿（{u['类型']}）")
    return "\n".join(lines)
