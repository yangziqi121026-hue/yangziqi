"""统一数据接口定义。

所有市场的 provider 都继承 BaseDataProvider，实现统一方法签名，
便于 workflow 在不同市场之间无缝切换。
"""

from abc import ABC, abstractmethod
from typing import Dict

import pandas as pd


class BaseDataProvider(ABC):
    """数据 provider 抽象基类。"""

    market_name: str = "未知市场"
    currency: str = "未知"

    @abstractmethod
    def validate_symbol(self, symbol: str) -> bool:
        """校验股票代码格式是否合法。"""
        raise NotImplementedError

    @abstractmethod
    def get_stock_name(self, symbol: str) -> str:
        """获取股票名称，失败时返回占位名称，不抛出异常中断流程。"""
        raise NotImplementedError

    @abstractmethod
    def get_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        period: str = "daily",
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """获取历史 K 线。

        返回标准化 DataFrame，至少包含列：
        date, open, high, low, close, volume
        失败时返回空 DataFrame（带标准列），不抛出异常中断流程。
        """
        raise NotImplementedError

    @abstractmethod
    def get_basic_info(self, symbol: str) -> Dict[str, object]:
        """获取个股基本信息。失败时返回 mock/空值结构，不中断流程。"""
        raise NotImplementedError

    @abstractmethod
    def get_financial(self, symbol: str) -> Dict[str, object]:
        """获取财务指标。失败时返回提示文本，不中断流程。"""
        raise NotImplementedError

    @abstractmethod
    def get_news(self, symbol: str, stock_name: str = "") -> Dict[str, object]:
        """获取新闻。第一版可返回 mock 新闻，并标注 is_mock=True。"""
        raise NotImplementedError

    @staticmethod
    def empty_history() -> pd.DataFrame:
        """返回带标准列的空 DataFrame。"""
        return pd.DataFrame(
            columns=["date", "open", "high", "low", "close", "volume"]
        )
