"""配置模块：读取环境变量。

读取:
- OPENAI_API_KEY / OPENAI_BASE_URL / MODEL_NAME
- DEEPSEEK_API_KEY（便捷支持：填了它就自动用 DeepSeek，无需改 BASE_URL/MODEL）
- MOCK_MODE

不要把 API Key 写死在代码里，全部从环境变量 / .env 读取。

DeepSeek 接入说明：
- DeepSeek 提供 OpenAI 兼容接口，因此沿用同一套 OpenAI 客户端即可。
- 小白零代码版：在 .env 里只填 DEEPSEEK_API_KEY 和 MOCK_MODE=false 即可，
  系统会自动把 BASE_URL 指向 https://api.deepseek.com、模型用 deepseek-chat。
- 也可显式用 OPENAI_API_KEY + OPENAI_BASE_URL 指向任意兼容服务。
"""

import os

from dotenv import load_dotenv

# 自动加载项目根目录下的 .env 文件（如果存在）
load_dotenv()

# DeepSeek 默认参数
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_DEFAULT_MODEL = "deepseek-chat"   # 也可用 deepseek-reasoner（更强推理，更慢更贵）


def _str_to_bool(value: str) -> bool:
    """把字符串转换为布尔值。"""
    if value is None:
        return False
    return str(value).strip().lower() in ("1", "true", "yes", "on", "y")


def _resolve_llm_settings():
    """解析最终使用的 (provider, api_key, base_url, model)。

    优先级：
    1. 显式 OPENAI_API_KEY -> 用 OPENAI_BASE_URL / MODEL_NAME（默认 OpenAI）
    2. 否则若有 DEEPSEEK_API_KEY -> 自动用 DeepSeek 默认 BASE_URL/模型
       （仍可被显式 OPENAI_BASE_URL / MODEL_NAME 覆盖）
    3. 都没有 -> 空 Key（将走 Mock）
    """
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    if openai_key:
        provider = "OpenAI 兼容"
        api_key = openai_key
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()
    elif deepseek_key:
        provider = "DeepSeek"
        api_key = deepseek_key
        base_url = os.getenv("OPENAI_BASE_URL", DEEPSEEK_BASE_URL).strip()
        model = os.getenv("MODEL_NAME", DEEPSEEK_DEFAULT_MODEL).strip()
    else:
        provider = "未配置"
        api_key = ""
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
        model = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()

    return provider, api_key, base_url, model


class Config:
    """全局配置对象。"""

    PROVIDER, OPENAI_API_KEY, OPENAI_BASE_URL, MODEL_NAME = _resolve_llm_settings()

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
            "服务商": cls.PROVIDER,
            "模型名称": cls.MODEL_NAME,
            "接口地址": cls.OPENAI_BASE_URL,
            "是否配置 API Key": "是" if cls.OPENAI_API_KEY else "否",
            "运行模式": "Mock 模式" if cls.is_mock_mode() else "真实 LLM 模式",
        }


# 全局唯一配置实例
config = Config()
