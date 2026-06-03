"""新闻分析师。"""

from typing import Dict

from .base_agent import BaseAgent


class NewsAnalyst(BaseAgent):
    name = "News Analyst"
    role = "新闻分析师"
    mock_role = "news"
    system_prompt = (
        "你是 News Analyst 新闻分析师。"
        "你只负责分析近期新闻、行业事件、政策和宏观信息对股票的影响。"
        "不要给出最终交易建议，只输出新闻面的利好和利空。"
        "如果新闻数据为 mock，必须明确提示。"
        "输出使用简洁的中文 Markdown。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        news = context.get("news", {})
        is_mock = news.get("is_mock", True)
        details = news.get("details", [])
        items = news.get("items", [])

        # 优先使用含正文摘要的真实新闻明细，让分析更有依据
        if details:
            news_text = "\n".join(d.get("text", "") for d in details)
        else:
            news_text = "\n".join(f"- {x}" for x in items) or "（无新闻条目）"

        mock_hint = (
            "注意：以下新闻为模拟/占位数据，请在结论中明确提示"
            "“新闻数据为模拟/占位，需接入真实新闻源后提高可信度”。"
            if is_mock
            else "以下为来自东方财富的真实个股新闻（含发布时间、来源与正文摘要），"
                 "请基于真实内容分析，不要编造未出现的信息。"
        )

        return (
            f"请基于以下新闻信息进行新闻面分析：\n\n"
            f"{self.format_stock_info(context)}\n\n"
            f"{mock_hint}\n"
            f"新闻明细：\n{news_text}\n\n"
            f"请输出：近期重要新闻（点名具体标题）、行业/政策影响、潜在利好、"
            f"潜在利空、新闻面结论。"
        )

    def run(self, context: Dict) -> str:
        """覆盖默认行为：当 LLM 处于 mock 模式但已抓到真实新闻时，
        直接基于真实新闻条目生成确定性的新闻面摘要，避免占位文案
        错误地宣称“新闻为模拟数据”。
        真实 LLM 模式下仍走父类逻辑，由模型阅读新闻明细做分析。
        """
        news = context.get("news", {})
        has_real_news = (not news.get("is_mock", True)) and news.get("details")
        if getattr(self.llm, "mock_mode", False) and has_real_news:
            return self._summarize_real_news(news)
        return super().run(context)

    @staticmethod
    def _summarize_real_news(news: Dict) -> str:
        """无真实 LLM 时，基于真实抓取的新闻生成确定性摘要。"""
        details = news.get("details", [])
        lines = ["**新闻面分析（基于东方财富真实新闻）**", ""]
        lines.append("**近期重要新闻：**")
        for d in details[:8]:
            title = d.get("title", "")
            meta = " ｜ ".join(x for x in (d.get("source", ""), d.get("time", "")) if x)
            lines.append(f"- {title}" + (f"（{meta}）" if meta else ""))
        lines.append("")
        lines.append(
            "**新闻面结论：** 以上为真实抓取的个股相关新闻，已构成新闻面的真实依据；"
            "如需更深入的利好/利空研判与措辞，请配置真实 LLM（在 .env 填入 "
            "`OPENAI_API_KEY` 并将 `MOCK_MODE` 设为 false）。"
        )
        lines.append("")
        lines.append("> 说明：本段新闻**数据为真实抓取**（来源：东方财富 stock_news_em）；"
                     "当前分析措辞为占位（未接入真实 LLM）。")
        return "\n".join(lines)
