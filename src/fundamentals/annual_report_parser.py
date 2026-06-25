"""② 年报/业务结构解析（P4）。

Tier A（东财 F10 自动）：
- main_composition(code): 主营构成（产品/收入占比/毛利率）RPT_F10_FN_MAINOP

Tier B/C（需年报PDF or 联网检索，半自动）：
- top_customers_suppliers / capex_rd_risk: 东财API无，返回占位+提示用WebSearch/PDF补
- verify_theme_benefit(code, theme): 用主营构成做"是否真受益题材"的客观判断（收入占比硬证据）
  + 可选 extra_evidence（联网检索/公告）增强
"""
from __future__ import annotations

from typing import Dict, List, Optional

from .. import em_f10

_MAINOP = "RPT_F10_FN_MAINOP"


def _f(v):
    try:
        return None if v in (None, "", "-") else float(v)
    except (ValueError, TypeError):
        return None


def main_composition(code: str) -> List[Dict]:
    """最新报告期主营构成（取条目最细的一种分类），按收入占比降序。"""
    rows = em_f10.report(_MAINOP, code, page_size=60, sort_col="REPORT_DATE")
    if not rows:
        return []
    latest = str(rows[0].get("REPORT_DATE"))[:10]
    cur = [r for r in rows if str(r.get("REPORT_DATE"))[:10] == latest]
    # 按 MAINOP_TYPE 分组。优先 产品(2)/行业(1)，避开地区(3)——地区分类对题材验证无意义
    by_type: Dict = {}
    for r in cur:
        by_type.setdefault(str(r.get("MAINOP_TYPE")), []).append(r)
    if not by_type:
        return []

    def _pref(t):
        return {"2": 0, "1": 1, "3": 3}.get(t, 2)  # 产品最优→行业→其他→地区最次

    best = sorted(by_type.items(), key=lambda kv: (_pref(kv[0]), -len(kv[1])))[0][1]
    out = []
    for r in best:
        out.append({
            "项目": r.get("ITEM_NAME"),
            "收入(亿)": round((_f(r.get("MAIN_BUSINESS_INCOME")) or 0) / 1e8, 2),
            "收入占比%": round((_f(r.get("MBI_RATIO")) or 0) * 100, 1),
            "毛利率%": round((_f(r.get("GROSS_RPOFIT_RATIO")) or 0) * 100, 1),
            "报告期": r.get("REPORT_NAME"),
        })
    out.sort(key=lambda x: x["收入占比%"], reverse=True)
    return out


def top_customers_suppliers(code: str) -> Dict:
    """前五大客户/供应商：东财F10无结构化API，需年报PDF或联网检索。"""
    return {"客户": None, "供应商": None,
            "提示": "东财F10无此结构化数据；用 WebSearch（年报/巨潮）或PDF解析补充"}


def capex_rd_risk(code: str) -> Dict:
    """在建工程/产能/研发方向/风险提示：需年报PDF文本，联网检索兜底。"""
    return {"在建工程": None, "产能": None, "研发方向": None, "风险提示": None,
            "提示": "需年报PDF（巨潮cninfo）或 WebSearch 提取后填充"}


def verify_theme_benefit(code: str, theme: str,
                         extra_evidence: Optional[List[str]] = None) -> Dict:
    """用主营构成客观判断'是否真受益某题材'。收入占比=硬证据。

    extra_evidence: 可传入联网检索/公告的关键句，增强判断。
    返回 {benefit:真/部分/伪/未实锤, hit_items:[...], confidence:强/中/弱, evidence:[...]}。
    """
    comp = main_composition(code)
    kws = [k for k in theme.replace("/", " ").replace("、", " ").split() if k]
    hits = []
    for item in comp:
        nm = str(item["项目"])
        if any(k in nm for k in kws):
            hits.append(item)
    ev = extra_evidence or []

    if hits:
        ratio = sum(h["收入占比%"] for h in hits)
        if ratio >= 30:
            benefit, conf = "真受益", "强"
        elif ratio >= 10:
            benefit, conf = "部分受益", "中"
        else:
            benefit, conf = "沾边受益", "弱"
        note = f"主营含[{','.join(h['项目'] for h in hits)}]，合计收入占比{ratio:.0f}%"
    elif ev:
        benefit, conf = "存疑(仅消息面)", "弱"
        note = "主营构成无对应产品，仅靠消息/互动易表述，未落到收入"
    else:
        benefit, conf = "未实锤", "弱"
        note = "主营构成无对应产品，且无其他证据"

    return {"theme": theme, "benefit": benefit, "confidence": conf,
            "hit_items": hits, "note": note, "extra_evidence": ev}


def report_md(code: str, name: str = "", theme: str = "") -> str:
    comp = main_composition(code)
    lines = [f"### 🏭 {name} {code} 业务结构"]
    if comp:
        lines.append(f"**主营构成（{comp[0]['报告期']}）：**")
        lines.append("| 项目 | 收入(亿) | 占比 | 毛利率 |")
        lines.append("|---|---|---|---|")
        for it in comp[:8]:
            lines.append(f"| {it['项目']} | {it['收入(亿)']} | {it['收入占比%']}% | {it['毛利率%']}% |")
    else:
        lines.append("> 无主营构成数据")
    if theme:
        v = verify_theme_benefit(code, theme)
        lines.append(f"\n**题材验证「{theme}」：{v['benefit']}（置信{v['confidence']}）** — {v['note']}")
    lines.append("\n> 客户/供应商/在建工程/研发：东财F10无结构化数据，需年报PDF或WebSearch补充。")
    return "\n".join(lines)
