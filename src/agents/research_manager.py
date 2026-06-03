"""研究经理。"""

from typing import Dict

from .base_agent import BaseAgent


class ResearchManager(BaseAgent):
    name = "Research Manager"
    role = "研究经理"
    mock_role = "research_manager"
    system_prompt = (
        "你是 Research Manager 研究经理。"
        "你负责综合基本面、新闻、情绪、技术、多空观点，"
        "判断哪一方更有说服力，输出研究总结。不要直接下单。"
        "输出使用简洁的中文 Markdown。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        return (
            f"请综合以下全部分析，判断多空哪一方更有说服力，并输出研究总结：\n\n"
            f"{self.format_stock_info(context)}\n\n"
            f"{self.format_upstream(context)}\n\n"
            f"请输出：多空力量对比、核心矛盾、研究结论。不要直接下单。"
        )
