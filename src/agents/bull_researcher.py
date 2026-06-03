"""看涨研究员。"""

from typing import Dict

from .base_agent import BaseAgent


class BullResearcher(BaseAgent):
    name = "Bull Researcher"
    role = "看涨研究员"
    mock_role = "bull"
    system_prompt = (
        "你是 Bull Researcher 看涨研究员。"
        "你必须站在看涨立场，从已有分析中提炼上涨逻辑。"
        "只输出看涨理由，不要平衡观点。输出 3-5 条看涨理由。"
        "输出使用简洁的中文 Markdown，使用有序列表。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        return (
            f"请基于以下已有分析，站在看涨立场提炼 3-5 条上涨理由：\n\n"
            f"{self.format_stock_info(context)}\n\n"
            f"{self.format_upstream(context)}\n\n"
            f"只输出看涨理由，不要给出风险或平衡观点。"
        )
