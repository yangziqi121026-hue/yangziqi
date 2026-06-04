"""全球新闻 → A股事件雷达。

数据：东财全球财经快讯 ak.stock_info_global_em（实时 7x24，标题/摘要/时间/链接）。
研判：DeepSeek 对每条快讯输出 影响A股/动向/触发因素/传导逻辑/受益板块/利空板块/置信度。
映射：把"受益板块"映射到项目板块池(sector_screener.POOLS)的真实标的代码，避免凭空点票。

不构成投资建议；标的映射仅为研究候选，需核验。
"""

import time
from typing import Dict, List, Optional

import pandas as pd

from .llm_client import llm_client
from .sector_screener import POOLS

try:
    pd.set_option("future.infer_string", False)
except Exception:  # noqa: BLE001
    pass

# 板块关键词 -> 项目板块池名（用于把 DeepSeek/新闻文本映射到真实标的）
SECTOR_KEYWORDS = {
    "半导体": ["芯片", "半导体", "晶圆", "光刻", "制程", "存储", "EDA", "出口管制", "先进封装"],
    "AI算力/服务器": ["算力", "AI", "人工智能", "大模型", "英伟达", "GPU", "数据中心", "服务器", "推理"],
    "光模块/CPO": ["光模块", "CPO", "光通信", "800G", "1.6T", "光芯片"],
    "机器人": ["机器人", "人形", "擎天柱", "减速器", "灵巧手", "特斯拉"],
    "电力": ["电力", "用电", "电价", "核电", "风电", "水电", "电网", "特高压", "电荒"],
    "新能源/锂电": ["锂", "电池", "光伏", "储能", "新能源车", "碳酸锂", "钠电"],
}

SYSTEM_PROMPT = (
    "你是A股产业链事件分析员。给定一条全球/国内财经快讯，冷静判断它对A股的影响，"
    "只做产业链传导分析，不给买卖指令。不确定的信息写“需核验”，绝不编造具体数字或标的。"
)


def fetch_global_news(limit: int = 50) -> pd.DataFrame:
    """拉取东财全球财经快讯，失败重试，返回标准列 DataFrame。"""
    last = None
    for _ in range(3):
        try:
            import akshare as ak

            df = ak.stock_info_global_em()
            if df is not None and not df.empty:
                cols = {c: c for c in df.columns}
                df = df.rename(columns={"标题": "title", "摘要": "summary",
                                        "发布时间": "time", "链接": "url"})
                keep = [c for c in ["title", "summary", "time", "url"] if c in df.columns]
                return df[keep].head(limit).reset_index(drop=True)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5)
    print(f"[news_radar] 全球快讯获取失败: {last}")
    return pd.DataFrame(columns=["title", "summary", "time", "url"])


def match_pool_targets(text: str, per_sector: int = 3) -> Dict[str, List[str]]:
    """根据文本命中的板块关键词，映射到板块池真实标的（代码+名称）。"""
    out: Dict[str, List[str]] = {}
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(k in text for k in kws) and sector in POOLS:
            picks = list(POOLS[sector].items())[:per_sector]
            out[sector] = [f"{n}({c})" for c, n in picks]
    return out


def _build_prompt(item: dict) -> str:
    return (
        f"快讯标题：{item.get('title')}\n"
        f"快讯摘要：{item.get('summary')}\n"
        f"发布时间：{item.get('time')}\n\n"
        f"请按以下固定结构输出（每条一行，简洁）：\n"
        f"1) 影响A股：高/中/低/无（一句话定性）\n"
        f"2) 事件动向：\n"
        f"3) 触发因素：\n"
        f"4) 传导逻辑（事件→宏观/产业→A股）：\n"
        f"5) 受益板块（尽量用规范词，如 半导体/AI算力/光模块/机器人/电力/新能源/军工/黄金/券商 等）：\n"
        f"6) 利空板块：\n"
        f"7) 关注方向（板块/细分，不必点具体代码）：\n"
        f"8) 置信度：高/中/低\n"
        f"不构成投资建议；不确定写“需核验”。"
    )


def analyze_event(item: dict) -> str:
    """对单条快讯做 DeepSeek 事件研判，返回 Markdown 文本。"""
    return llm_client.chat(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_build_prompt(item),
        temperature=0.3,
        max_tokens=500,
        mock_role="news_event",
    )


def scan(limit: int = 50, analyze_top: int = 6,
         keyword: Optional[str] = None) -> Dict:
    """拉快讯 + 对前 analyze_top 条做事件研判 + 映射板块池标的。

    返回 {news: DataFrame, events: [ {item, analysis, targets} ], meta }
    """
    df = fetch_global_news(limit)
    if keyword:
        mask = df["title"].astype(str).str.contains(keyword, na=False) | \
               df["summary"].astype(str).str.contains(keyword, na=False)
        df = df[mask].reset_index(drop=True)

    events = []
    for i in range(min(analyze_top, len(df))):
        item = df.iloc[i].to_dict()
        analysis = analyze_event(item)
        targets = match_pool_targets(f"{item.get('title','')}{item.get('summary','')}{analysis}")
        events.append({"item": item, "analysis": analysis, "targets": targets})

    return {"news": df, "events": events,
            "meta": {"count": len(df), "analyzed": len(events),
                     "real_llm": not getattr(llm_client, "mock_mode", True)}}
