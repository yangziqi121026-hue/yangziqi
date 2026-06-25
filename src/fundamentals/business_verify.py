"""⑥ 业务验证 / 证据强弱分级（P4）。

把"某公司受益某题材/有某订单/有某产能"的说法，用多源证据交叉裁定：
  - 主营构成收入占比（硬证据，来自 ②）
  - 个股新闻/公告（中证据，stock_news_em）
  - 互动易/调研/联网检索（弱证据，需 extra_evidence 传入）
→ 输出 level：强(实锤) / 中 / 弱 / 未实锤

设计原则：**落到收入占比的才算强证据**；只有互动易/新闻嘴上说=弱；什么都没有=未实锤。
避免被"蹭概念"忽悠。
"""
from __future__ import annotations

from typing import Dict, List, Optional

from . import annual_report_parser as arp


def _stock_news_hits(code: str, kws: List[str], limit: int = 8) -> List[str]:
    try:
        from .. import stock_deepdive as sd
        news = sd._stock_news(code, limit=limit)
        return [n for n in news if any(k in n for k in kws)]
    except Exception:  # noqa: BLE001
        return []


def verify(code: str, claim: str, name: str = "",
           extra_evidence: Optional[List[str]] = None) -> Dict:
    """裁定 claim 的证据强弱。

    claim: 待验证说法，如 "HBM" / "六氟化钨" / "特斯拉订单" / "液冷"
    extra_evidence: 联网检索/互动易抓到的关键句（弱证据）
    返回 {level, anchor, evidence:[{src,level,text}], note}
    """
    kws = arp.expand_keywords(claim)
    evidence: List[Dict] = []

    # 1) 主营构成（硬证据）
    tb = arp.verify_theme_benefit(code, claim, extra_evidence=None)
    anchor_ratio = sum(h["收入占比%"] for h in tb["hit_items"]) if tb["hit_items"] else 0
    if tb["hit_items"]:
        evidence.append({"src": "主营构成", "level": "强",
                         "text": f"{tb['note']}（毛利率见业务结构）"})

    # 2) 新闻/公告（中证据）
    news_hits = _stock_news_hits(code, kws)
    for n in news_hits[:4]:
        evidence.append({"src": "新闻/公告", "level": "中", "text": n})

    # 3) 联网检索/互动易（弱证据）
    for e in (extra_evidence or []):
        evidence.append({"src": "检索/互动易", "level": "弱", "text": e})

    # —— 裁定 ——
    if anchor_ratio >= 30:
        level, note = "强(实锤)", f"主营收入占比{anchor_ratio:.0f}%，已落到报表"
    elif anchor_ratio >= 10:
        level, note = "中", f"主营占比{anchor_ratio:.0f}%，有贡献但非主力"
    elif anchor_ratio > 0:
        level, note = "弱", f"主营占比仅{anchor_ratio:.0f}%，蹭边"
    elif news_hits and (extra_evidence):
        level, note = "弱", "有新闻+检索表述，但未落到收入，谨防蹭概念"
    elif news_hits or extra_evidence:
        level, note = "弱", "仅个别消息提及，未实锤"
    else:
        level, note = "未实锤", "无收入、无新闻、无检索证据"

    return {"claim": claim, "code": code, "name": name,
            "level": level, "anchor_占比%": round(anchor_ratio, 1),
            "evidence": evidence, "note": note}


def report_md(code: str, claim: str, name: str = "",
              extra_evidence: Optional[List[str]] = None) -> str:
    v = verify(code, claim, name, extra_evidence)
    icon = {"强(实锤)": "✅", "中": "🟡", "弱": "⚠️", "未实锤": "❌"}.get(v["level"], "")
    lines = [f"### 🔍 {name} {code} 业务验证「{claim}」：{icon} **{v['level']}**",
             f"_{v['note']}_", ""]
    if v["evidence"]:
        lines.append("| 证据源 | 强度 | 内容 |")
        lines.append("|---|---|---|")
        for e in v["evidence"]:
            lines.append(f"| {e['src']} | {e['level']} | {e['text']} |")
    else:
        lines.append("> 无任何证据")
    lines.append("\n> 裁定原则：落到主营收入占比才算强证据；仅新闻/互动易表述=弱，防蹭概念。")
    return "\n".join(lines)
