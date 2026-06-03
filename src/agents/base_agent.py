"""智能体基础类。

每个智能体都有：
- name：名称
- role：角色定位
- system_prompt：角色专属系统提示词
- mock_role：mock 模式下使用的占位模板键
- run(context)：执行分析并返回 Markdown 文本

智能体不直接获取数据，只消费 workflow 传进来的 context（market_data + 上游结论）。
"""

from typing import Dict

from ..llm_client import llm_client


class BaseAgent:
    """所有智能体的基类。"""

    name: str = "BaseAgent"
    role: str = "基础智能体"
    system_prompt: str = "你是一个金融分析智能体。"
    mock_role: str = "default"

    def __init__(self) -> None:
        self.llm = llm_client

    def build_user_prompt(self, context: Dict) -> str:
        """子类实现：根据 context 构造发给 LLM 的用户提示。"""
        raise NotImplementedError

    def run(self, context: Dict) -> str:
        """执行分析，返回 Markdown 文本。出错也不抛异常中断流程。"""
        try:
            user_prompt = self.build_user_prompt(context)
            return self.llm.chat(
                system_prompt=self.system_prompt,
                user_prompt=user_prompt,
                mock_role=self.mock_role,
            )
        except Exception as exc:  # noqa: BLE001
            return f"> ⚠️ {self.name} 执行出错：{exc}\n\n（已跳过该环节，不影响整体流程。）"

    # 一些通用的上下文格式化工具，供子类复用 -------------------------------

    @staticmethod
    def format_stock_info(context: Dict) -> str:
        info = context.get("stock_info", {})
        return (
            f"市场：{info.get('market')}\n"
            f"股票代码：{info.get('symbol')}\n"
            f"股票名称：{info.get('name')}\n"
            f"当前价格：{info.get('current_price')}\n"
            f"交易货币：{info.get('currency')}"
        )

    @staticmethod
    def format_indicators(context: Dict) -> str:
        ind = context.get("indicators", {})
        return (
            f"MA5={ind.get('MA5')} MA10={ind.get('MA10')} "
            f"MA20={ind.get('MA20')} MA60={ind.get('MA60')}\n"
            f"RSI14={ind.get('RSI14')} MACD={ind.get('MACD')} "
            f"Signal={ind.get('MACD_Signal')} Hist={ind.get('MACD_Hist')}\n"
            f"趋势={ind.get('trend')} 近20日涨跌幅={ind.get('change_20d_pct')}%\n"
            f"52周高={ind.get('high_52w')} 52周低={ind.get('low_52w')}\n"
            f"成交量变化={ind.get('volume_change_pct')}% "
            f"支撑位={ind.get('support')} 压力位={ind.get('resistance')}"
        )

    @staticmethod
    def format_upstream(context: Dict) -> str:
        """汇总上游已有的各分析师/研究员结论。"""
        agents = context.get("agents", {})
        parts = []
        labels = {
            "fundamental": "基本面分析",
            "news": "新闻面分析",
            "sentiment": "情绪面分析",
            "technical": "技术面分析",
            "bull": "看涨观点",
            "bear": "看跌观点",
            "research_manager": "研究经理总结",
            "trader": "交易员建议",
        }
        for key, label in labels.items():
            if key in agents and agents[key]:
                parts.append(f"【{label}】\n{agents[key]}")
        return "\n\n".join(parts) if parts else "（暂无上游分析）"
