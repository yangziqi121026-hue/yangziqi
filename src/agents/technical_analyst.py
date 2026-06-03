"""技术分析师。"""

from typing import Dict

from .base_agent import BaseAgent


class TechnicalAnalyst(BaseAgent):
    name = "Technical Analyst"
    role = "技术分析师"
    mock_role = "technical"
    system_prompt = (
        "你是 Technical Analyst 技术分析师。"
        "你只负责分析技术指标，包括均线、RSI、MACD、趋势、支撑位、压力位。"
        "不要给出最终交易建议，只输出技术面结论。"
        "输出使用简洁的中文 Markdown。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        return (
            f"请基于以下技术指标进行技术面分析：\n\n"
            f"{self.format_stock_info(context)}\n\n"
            f"{self.format_indicators(context)}\n\n"
            f"请输出：趋势分析、均线分析、RSI 分析、MACD 分析、"
            f"支撑位与压力位分析、技术面结论。"
        )
