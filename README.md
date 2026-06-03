# TradingAgents 多市场智能体金融分析系统

> A股优先 ｜ 预留美股与港股扩展 ｜ 多智能体（Multi-Agent）LLM 金融分析框架

## 一、项目介绍

TradingAgents 是一个基于「多智能体协作」的金融分析框架。系统模拟一家投研机构的工作流：
由 **基本面 / 新闻 / 情绪 / 技术** 四位分析师并行给出专业判断，再由 **看涨 / 看跌研究员** 展开多空辩论，
经 **研究经理** 汇总、**交易员** 形成交易计划，最后由 **风控员** 审核把关，输出一份格式固定的研究报告。

第一版以 **A 股** 为主，数据源使用 [AKShare](https://akshare.akshare.xyz/)；美股、港股已预留接口，后续版本接入。

## 二、功能说明

- 多市场架构：A股（已实现）、美股 / 港股（接口预留）。
- 9 个智能体角色协作：基本面 / 新闻 / 情绪 / 技术分析师 + 看涨 / 看跌研究员 + 研究经理 + 交易员 + 风控员。
- 完整技术指标：MA5/10/20/60、RSI14、MACD（含 Signal/Hist）、52 周高低点、近 20 日涨跌幅、成交量变化、支撑位 / 压力位。
- 固定格式研究报告，可一键导出 Markdown。
- SQLite 历史记录，随时回看导出。
- Streamlit 可视化界面：最终报告 / 智能体过程 / 技术图表 / 历史记录 四个标签页。
- **Mock 模式**：没有 LLM API Key 或没有稳定新闻源时，系统仍可跑通完整流程（占位输出，并明确标注）。

## 三、第一版支持范围

| 能力 | 状态 |
| --- | --- |
| A 股行情 / 指标 / 报告 | ✅ 已实现（AKShare） |
| A 股财务 / 新闻 | ⚠️ 尽力获取，失败自动降级占位 |
| 美股 | 🔜 接口预留，返回「暂未接入」提示 |
| 港股 | 🔜 接口预留，返回「暂未接入」提示 |
| LLM 分析 | ✅ OpenAI 兼容接口 / Mock 模式 |

## 四、多市场扩展设计说明

所有数据源都继承统一抽象基类 `src/data_providers/base_provider.py:BaseDataProvider`，
实现相同的方法签名（`get_history` / `get_basic_info` / `get_financial` / `get_news` 等）。
`workflow.py` 通过 `get_provider(market)` 选择对应 provider，智能体只消费 `workflow` 注入的
`context`，**不直接取数**。因此新增市场只需新增一个 provider 文件并实现接口即可，无需改动智能体与报告逻辑。

## 五、安装步骤

```bash
pip install -r requirements.txt
```

## 六、环境变量配置

复制 `.env.example` 为 `.env` 并按需填写：

```env
OPENAI_API_KEY=          # 你的 Key；留空则自动使用 Mock 模式
OPENAI_BASE_URL=https://api.openai.com/v1   # 可指向任意 OpenAI 兼容服务
MODEL_NAME=gpt-4o-mini
MOCK_MODE=true           # true=强制占位输出；改为 false 且填了 Key 才会调用真实模型
```

> API Key 全部从环境变量读取，不会写死在代码中。

## 七、启动命令

```bash
streamlit run app.py
```

启动后浏览器打开提示的本地地址（默认 http://localhost:8501）。

## 八、使用方法

1. 左侧选择 **市场**（默认 A股）。
2. 输入 **股票代码**（A 股为 6 位数字，如 `600519`）。
3. 选择 **分析深度 / 复权方式 / 数据周期 / 开始与结束日期**。
4. 点击 **🚀 开始分析**。
5. 在右侧标签页查看：
   - **最终报告**：固定格式研究报告，可导出 Markdown。
   - **智能体过程**：每个智能体的实时输出。
   - **技术图表**：收盘价与 MA5/MA10/MA20/MA60。
   - **历史记录**：查看 / 导出过往分析。

## 九、项目结构

```
tradingagents_multi_market_clone/
├── app.py                      # Streamlit 主页面（仅界面交互）
├── requirements.txt
├── .env.example
├── README.md
├── data/
│   └── tradingagents.db        # 运行后自动生成
├── reports/                    # 导出的 Markdown 报告
└── src/
    ├── __init__.py
    ├── config.py               # 读取环境变量
    ├── database.py             # SQLite 历史记录
    ├── indicators.py           # 技术指标计算
    ├── llm_client.py           # LLM 封装 + Mock
    ├── data_providers/
    │   ├── __init__.py
    │   ├── base_provider.py     # 统一数据接口
    │   ├── a_share_provider.py  # A 股（AKShare）
    │   ├── us_stock_provider.py # 美股（预留）
    │   └── hk_stock_provider.py # 港股（预留）
    ├── agents/
    │   ├── __init__.py
    │   ├── base_agent.py
    │   ├── fundamental_analyst.py
    │   ├── news_analyst.py
    │   ├── sentiment_analyst.py
    │   ├── technical_analyst.py
    │   ├── bull_researcher.py
    │   ├── bear_researcher.py
    │   ├── research_manager.py
    │   ├── trader.py
    │   └── risk_manager.py
    ├── workflow.py             # 流程编排
    └── report_generator.py     # 固定格式报告
```

## 十、AKShare 数据源说明

- 历史行情：`ak.stock_zh_a_hist(symbol, period, start_date, end_date, adjust)`
- 实时行情 / 名称：`ak.stock_zh_a_spot_em()`
- 个股基本信息：`ak.stock_individual_info_em(symbol)`（失败返回占位结构）
- 财务指标：`ak.stock_financial_abstract_ths` / `ak.stock_financial_analysis_indicator`（失败返回「暂未获取到完整财务数据」）
- 新闻：`ak.stock_news_em(symbol)`（失败或为空时退回 mock，并明确标注）

> AKShare 接口依赖第三方公开数据，偶发失败属正常现象。系统对所有数据接口都做了**异常兜底**，
> 任何单点失败都不会中断整体分析流程。

## 十一、后期如何接入美股

编辑 `src/data_providers/us_stock_provider.py`，在各方法中接入真实数据源（如 yfinance / AKShare 美股接口等），
返回与 A 股一致的标准化结构（`get_history` 返回含 `date/open/high/low/close/volume` 的 DataFrame）即可，
无需改动智能体与报告模块。

## 十二、后期如何接入港股

编辑 `src/data_providers/hk_stock_provider.py`，方式同美股。实现统一接口后，前端市场选择「港股」即可直接生效。

## 十三、风险声明

本项目由 AI 多智能体系统生成，仅用于研究和学习，**不构成任何投资建议**。
系统不包含、也不会接入任何真实下单 / 券商 / 交易所（Binance、OKX、Alpaca 等）接口。
据此操作，风险自负。
```
