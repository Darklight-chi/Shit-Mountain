# Lobster Agent - AI 客服数字员工

> 以 LangGraph 为核心决策引擎、以 Playwright 为闲鱼接入层、以知识库 + mock 业务工具为客服能力基础，天然可迁移到海外电商平台的 AI 客服数字员工内核。

## 项目地址

```
C:\Users\More\Desktop\lobster-agent\
```

## 架构概览

```
渠道接入层 (adapters/)     ← 闲鱼 / Shopify / Chatwoot / WhatsApp
    ↓
会话处理层 (conversation/) ← 路由 / 去重 / 会话管理 / 转人工
    ↓
Agent 决策层 (agent/)      ← 意图分类(12类) / 风险检测(3级) / LLM 回复
    ↓
业务工具层 (tools/)        ← FAQ / 知识库 / 订单 / 物流 / 退款 / 翻译
    ↓
存储配置层 (database/)     ← SQLite / 中英知识库 / Prompt 国际化
```

## 核心能力

| 能力 | 状态 | 说明 |
|------|------|------|
| 12 类意图识别 | ✅ | 售前/售中/售后/投诉/海关等 |
| 3 级风险检测 | ✅ | low/medium/high，高风险自动转人工 |
| 订单查询 (mock) | ✅ | 支持订单号查询 + 用户最近订单 |
| 物流查询 (mock) | ✅ | 顺丰/圆通/UPS 示例数据 |
| 退款退货政策 | ✅ | 7天无理由 / 破损 / 发错 / 少件 |
| 地址修改/取消订单 | ✅ | 按发货状态判断 |
| 高风险转人工 | ✅ | 创建工单 + 输出标准话术 |
| 中英双语 | ✅ | 自动语言检测，自动切换回复 |
| 会话持久化 | ✅ | SQLite 存消息/会话/工单/订单 |
| 渠道可迁移 | ✅ | adapter 模式，闲鱼只是其中一个 |

## 快速启动

### 1. 安装依赖

```bash
pip install sqlalchemy loguru python-dotenv openai pydantic
pip install playwright  # 闲鱼模式需要
playwright install chromium
```

### 2. 配置 .env

```bash
# 复制示例配置
cp .env.example .env

# 修改 LLM 后端（Ollama / OpenClaw / OpenAI）
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=llama3
```

### 3. 运行

```bash
# CLI 交互测试（不需要 LLM，关键词匹配即可工作）
run.bat cli

# 闲鱼实时监听（需要 Playwright + 首次扫码登录）
run.bat xianyu
```

## 目录结构

```
lobster-agent/
├── app/                    # 入口
│   ├── main.py            # 主程序
│   └── runner.py          # 运行器 (CLI / Xianyu)
├── adapters/              # 渠道接入层
│   ├── base.py            # 统一接口 (BaseChannelAdapter)
│   ├── xianyu_adapter.py  # 闲鱼 Playwright 实现
│   ├── shopify_adapter.py # Shopify 占位
│   └── chatwoot_adapter.py# Chatwoot 占位
├── conversation/          # 会话处理层
│   ├── message_router.py  # 消息路由
│   ├── session_manager.py # 会话管理
│   ├── deduplicator.py    # 消息去重
│   └── escalation.py      # 转人工逻辑
├── agent/                 # Agent 决策层
│   ├── graph.py           # 核心处理流水线
│   ├── state.py           # 状态定义
│   ├── intent_classifier.py # 意图分类 (12类)
│   ├── risk_detector.py   # 风险检测 (3级)
│   └── response_generator.py # LLM 回复生成
├── tools/                 # 业务工具层
│   ├── faq_tool.py        # FAQ 固定问答
│   ├── kb_tool.py         # 知识库检索
│   ├── order_tool.py      # 订单查询
│   ├── tracking_tool.py   # 物流查询
│   ├── refund_tool.py     # 退款/退货/地址/取消
│   ├── escalation_tool.py # 转人工工单
│   └── translation_tool.py# 语言检测
├── knowledge/             # 知识库 (按语言)
│   ├── zh/                # 中文
│   └── en/                # 英文
├── integrations/          # 外部服务 (mock)
│   ├── mock_order_service.py
│   └── mock_tracking_service.py
├── database/              # 数据层
│   ├── db.py              # 初始化 + seed
│   ├── models.py          # SQLAlchemy 模型
│   └── repository.py      # 数据访问层
├── config/                # 配置
│   ├── settings.py        # 环境变量
│   ├── prompts.py         # Prompt 模板 (中英)
│   └── policies.py        # 业务策略
├── tests/                 # 测试 (20个全通过)
├── storage/               # SQLite 数据库
├── .env                   # 环境配置
├── requirements.txt       # Python 依赖
└── run.bat                # 启动脚本
```

## 意图分类 (12 类)

| Intent | 示例 |
|--------|------|
| general_greeting | 在吗 / hello |
| presale_product | 有货吗 / 尺寸 |
| shipping_time | 多久发货 |
| order_status | 查订单 A10239 |
| tracking_status | 物流到哪了 |
| return_refund | 可以退吗 |
| address_change | 改地址 |
| cancellation | 取消订单 |
| complaint | 投诉 / 骗人 |
| damaged_or_wrong_item | 发错 / 坏了 |
| customs_tax | 海关扣了 |
| fallback | 无法识别 |

## 海外迁移

只需实现新的 adapter：

```python
from adapters.base import BaseChannelAdapter

class WhatsAppAdapter(BaseChannelAdapter):
    channel_name = "whatsapp"

    async def fetch_new_messages(self): ...
    async def send_reply(self, session_id, text): ...
    async def get_session_context(self, session_id): ...
```

Agent 内核 + 知识库 + 工具层完全复用。

## 技术栈

- Python 3.11
- SQLAlchemy (ORM)
- Playwright (闲鱼接入)
- OpenAI API 兼容接口 (Ollama / OpenClaw / OpenAI)
- Loguru (日志)
- Pydantic (数据校验)
