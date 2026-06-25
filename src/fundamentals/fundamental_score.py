"""⑨ 六维综合基本面评分 → 四档结论（P1 骨架）。

六维：财报分(①) + 估值分(③) + 行业景气分(⑤) + 股东变化分(④) + 订单产能分(②⑥) + 现金流分(①)

P1 阶段：财报分 + 现金流分已接入（来自 financial_quarter_tracker）；
其余四维为占位（返回 None），随 P2-P5 逐步接入后自动纳入加权。
权重会按"已就绪维度"自动归一，避免未接入维度拉低总分。
"""
from __future__ import annotations

from typing import Dict, Optional

from . import financial_quarter_tracker as fqt
from . import holder_change_tracker as hct
from . import peer_compare as pc

# 各维度满分（设计权重，未就绪的维度暂不计入归一）
_WEIGHTS = {
    "财报": 35,
    "现金流": 15,
    "估值": 15,    # P2 peer_compare 接入
    "股东变化": 15,  # P2 holder_change_tracker 接入
    "行业景气": 10,  # P5 industry_price_monitor 接入
    "订单产能": 10,  # P4 business_verify/annual_report_parser 接入
}


def _valuation_dim(v: Dict, full: float):
    """绝对估值打分：PE_TTM(0.6) + PEG(0.4)。负PE/无盈利给低分。"""
    if not v or v.get("PE_TTM") is None:
        return None
    pe, peg = v.get("PE_TTM"), v.get("PEG")
    if pe < 0:
        pe_s, tag = 0.2, f"PE_TTM{pe:.0f}(无盈利)"
    elif pe < 20:
        pe_s, tag = 1.0, f"PE{pe:.0f}低估"
    elif pe < 40:
        pe_s, tag = 0.7, f"PE{pe:.0f}合理"
    elif pe < 80:
        pe_s, tag = 0.4, f"PE{pe:.0f}偏高"
    else:
        pe_s, tag = 0.2, f"PE{pe:.0f}高估"
    if peg is not None and 0 < peg <= 1:
        peg_s = 1.0
    elif peg is not None and 1 < peg <= 2:
        peg_s = 0.6
    elif peg is not None and peg > 2:
        peg_s = 0.3
    else:
        peg_s = 0.5
    return round((pe_s * 0.6 + peg_s * 0.4) * full, 1), full, f"{tag}·PEG{peg if peg is None else round(peg,1)}"


def _tier(score100: float) -> str:
    if score100 >= 75:
        return "强基本面"
    if score100 >= 55:
        return "改善中"
    if score100 >= 35:
        return "题材驱动(基本面平庸)"
    return "风险较大"


def total_score(code: str, name: str = "", theme: Optional[str] = None) -> Dict:
    """综合评分。P1：仅财报+现金流就绪，其余维度 None。

    返回 {'score':0-100(已就绪维度归一), 'tier', 'dims':{维度:(得分,满分,note)}, 'ready':[...]}。
    """
    dims: Dict[str, tuple] = {}

    # —— 财报维度（含现金流子项，来自 ①）——
    df = fqt.fetch_quarters(code, n=8)
    if df.empty:
        dims["财报"] = (None, _WEIGHTS["财报"], "无财务数据")
        dims["现金流"] = (None, _WEIGHTS["现金流"], "无财务数据")
    else:
        sc = fqt.score(df)
        bd = sc["breakdown"]
        # 财报分(剔除现金流子项) 折算到 35
        cf_pts, cf_mx = bd["现金流改善"][0], bd["现金流改善"][2]
        fin_raw = sc["score"] - cf_pts  # 85分制(100-15现金流)
        fin_pts = round(fin_raw / 85 * _WEIGHTS["财报"], 1)
        dims["财报"] = (fin_pts, _WEIGHTS["财报"],
                       f"财报评分{sc['score']}/100·{sc['period']}·"
                       f"营收加速{sc['accel']['营收加速']}/净利加速{sc['accel']['净利加速']}")
        dims["现金流"] = (round(cf_pts / cf_mx * _WEIGHTS["现金流"], 1),
                        _WEIGHTS["现金流"], bd["现金流改善"][1])

    # —— 估值维度（③ peer_compare.valuation 绝对估值打分）——
    v = pc.valuation(code)
    vp = _valuation_dim(v, _WEIGHTS["估值"])
    dims["估值"] = vp if vp else (None, _WEIGHTS["估值"], "无估值数据")

    # —— 股东变化维度（④ holder_change_tracker.summarize）——
    try:
        hd = hct.summarize(code, name)
        dims["股东变化"] = (round(hd["score"] / 100 * _WEIGHTS["股东变化"], 1),
                          _WEIGHTS["股东变化"],
                          f"{hd['tier']}·{('；'.join(hd['notes']) or '无异动')}")
    except Exception:  # noqa: BLE001
        dims["股东变化"] = (None, _WEIGHTS["股东变化"], "取数失败")

    # —— 未就绪维度（P4-P5 接入）——
    for k in ("行业景气", "订单产能"):
        dims[k] = (None, _WEIGHTS[k], "待接入")

    ready = {k: v for k, v in dims.items() if v[0] is not None}
    if not ready:
        return {"score": None, "tier": "数据缺失", "dims": dims, "ready": []}
    got = sum(v[0] for v in ready.values())
    cap = sum(v[1] for v in ready.values())
    score100 = round(got / cap * 100, 1)
    return {"score": score100, "tier": _tier(score100), "dims": dims,
            "ready": list(ready.keys()), "note": f"基于已就绪维度{list(ready.keys())}归一"}


def report_md(code: str, name: str = "", theme: Optional[str] = None) -> str:
    r = total_score(code, name, theme)
    if r["score"] is None:
        return f"### 🧮 {name} {code} 综合基本面\n> {r['tier']}"
    lines = [f"### 🧮 {name} {code} 综合基本面评分：{r['score']}/100 → **{r['tier']}**",
             f"_（{r['note']}；其余维度随P2-P5接入）_", "",
             "| 维度 | 得分 | 说明 |", "|---|---|---|"]
    for k, (pts, mx, note) in r["dims"].items():
        pts_s = "—(待接入)" if pts is None else f"{pts}/{mx}"
        lines.append(f"| {k} | {pts_s} | {note} |")
    return "\n".join(lines)
