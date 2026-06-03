"""配置模块：读取环境变量。

读取:
- OPENAI_API_KEY
- OPENAI_BASE_URL
- MODEL_NAME
- MOCK_MODE

不要把 API Key 写死在代码里，全部从环境变量 / .env 读取。
"""

import os

from dotenv import load_dotenv

# 自动加载项目根目录下的 .env 文件（如果存在）
load_dotenv()


def _str_to_bool(value: str) -> bool:
    """把字符串转换为布尔值。"""
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


class Config:
    """全局配置对象。"""

    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()

    # 如果显式开启 MOCK_MODE，或没有 API Key，都使用 mock 模式
    _MOCK_ENV: bool = _str_to_bool(os.getenv("MOCK_MODE", "true"))

    @classmethod
    def is_mock_mode(cls) -> bool:
        """是否使用 mock 模式。

        规则：显式开启 MOCK_MODE 或没有配置 API Key 时，强制使用 mock。
        """
        if cls._MOCK_ENV:
            return True
        if not cls.OPENAI_API_KEY:
            return True
        return False

    @classmethod
    def summary(cls) -> dict:
        """返回当前配置摘要（用于界面展示，不暴露 Key 内容）。"""
        return {
            "模型名称": cls.MODEL_NAME,
            "接口地址": cls.OPENAI_BASE_URL,
            "是否配置 API Key": "是" if cls.OPENAI_API_KEY else "否",
            "运行模式": "Mock 模式" if cls.is_mock_mode() else "真实 LLM 模式",
        }


# 全局唯一配置实例
config = Config()
