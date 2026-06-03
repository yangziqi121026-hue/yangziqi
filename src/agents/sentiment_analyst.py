"""情绪分析师。"""

from typing import Dict

from .base_agent import BaseAgent


class SentimentAnalyst(BaseAgent):
    name = "Sentiment Analyst"
    role = "情绪分析师"
    mock_role = "sentiment"
    system_prompt = (
        "你是 Sentiment Analyst 情绪分析师。"
        "你只负责判断市场情绪，包括价格变化、成交量、市场关注度、投资者偏好。"
        "判断情绪偏多、偏空或中性。"
        "不要给出最终交易建议，只输出情绪判断。"
        "输出使用简洁的中文 Markdown。"
    )

    def build_user_prompt(self, context: Dict) -> str:
        ind = context.get("indicators", {})
        return (
            f"请基于以下量价信息进行市场情绪分析：\n\n"
            f"{self.format_stock_info(context)}\n\n"
            f"近20日涨跌幅：{ind.get('change_20d_pct')}%\n"
            f"成交量变化：{ind.get('volume_change_pct')}%\n"
            f"当前趋势：{ind.get('trend')}\n"
            f"RSI14：{ind.get('RSI14')}\n\n"
            f"请输出：市场情绪、投资者偏好、量价情绪、情绪风险、情绪面结论"
            f"（判断偏多/偏空/中性）。"
        )
