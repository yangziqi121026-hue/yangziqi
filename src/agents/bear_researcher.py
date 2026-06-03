"""看跌研究员。"""

from typing import Dict

from .base_agent import BaseAgent


class BearResearcher(BaseAgent):
    name = "Bear Researcher"
    role = "看跌研究员"
    mock_role = "bear"
    system_prompt = (
        "你是 Bear Researcher 看跌研究员。"
        "你必须站在看跌立场，从已有分析中提炼下跌风险。"
        "只输出看跌理由，不要平衡观点。输出 3-5 条看跌理由。"
        "输出使用简洁的中文 Markdown，使用有序列表。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        return (
            f"请基于以下已有分析，站在看跌立场提炼 3-5 条下跌风险：\n\n"
            f"{self.format_stock_info(context)}\n\n"
            f"{self.format_upstream(context)}\n\n"
            f"只输出看跌理由，不要给出利好或平衡观点。"
        )
