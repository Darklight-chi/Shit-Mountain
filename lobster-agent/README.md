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

# Ozon 实时监听（需要配置 Ozon API 凭证）
run.bat ozon
```

## 当前运行 / 运营流程（当前重点：闲鱼 + Ozon）

当前代码里的主流程如下：

1. **启动入口**
   - `app/main.py` 负责初始化日志、初始化数据库、选择运行模式。
   - 当前实际重点渠道是 `xianyu` 和 `ozon`，都走统一的 live loop。

2. **渠道拉消息**
   - `adapters/xianyu_adapter.py` 负责从闲鱼 IM 页面抓取未读消息、发送回复、提取当前会话里的商品卡片 / 订单卡片信息。
   - `adapters/ozon_adapter.py` 负责从 Ozon Seller API 拉取未读会话、读取聊天历史、发送回复。

3. **统一消息处理**
   - 所有渠道消息进入 `app/runner.py` 的统一处理链路：
     - 去重
     - 建立 / 读取会话
     - 保存用户消息
     - 拉取会话上下文
     - 运行 Agent
     - 发送回复
     - 回写会话状态

4. **会话层**
   - `conversation/message_router.py` 负责把原始消息包装成 Agent 可消费的上下文。
   - `conversation/deduplicator.py` 负责短时间内同会话重复消息去重，避免重复回复。
   - `conversation/session_manager.py` 负责会话持久化、历史消息读取、状态更新。

5. **Agent 决策层**
   - `agent/graph.py` 是主决策流程：
     - 语言识别
     - 意图识别
     - 风险识别
     - 运营规则判断
     - 工具调用
     - 最终回复生成

6. **运营规则（已加到主流程）**
   - 仅对 `xianyu` / `ozon` 生效。
   - **催单续接**：如果用户只发“在吗 / 还在吗 / any update”这类消息，会优先继承上一轮订单、物流、退款、改址、取消等意图，而不是重新当成普通招呼。
   - **重复无法识别升级**：如果连续多轮都是 `fallback`，说明自动化没解决问题，会自动转人工。
   - **售后重复追问升级**：退款 / 错发 / 海关类问题在多轮反复追问时，会升级处理。
   - **已发货后改址 / 取消自动转人工**：这类问题已经不适合继续模板自动回复，会直接建工单。
   - **已转人工会话保持人工状态**：已经标记 `needs_handoff=True` 的会话，后续再来消息不会重复创建新流程，而是继续返回人工接管话术。

7. **业务工具层**
   - `tools/order_tool.py`：优先提取订单号；如果用户没提供订单号，则回退到该用户最近一笔订单。
   - `tools/tracking_tool.py`：先解析订单，再根据运单号查询物流，不再把“查物流”错误回成“订单状态”。
   - `tools/refund_tool.py`：处理退款、改地址、取消订单的规则回复。
   - `tools/faq_tool.py` / `tools/kb_tool.py`：处理售前 FAQ 和知识库检索。
   - `tools/escalation_tool.py`：创建人工工单并返回转人工话术。

8. **回复策略**
   - 普通招呼直接返回固定话术。
   - 低风险且工具结果足够明确时，直接返回工具结果，减少无意义 LLM 调用。
   - 复杂问题才交给 `agent/response_generator.py` 调用 LLM 做润色回复。

9. **数据落库**
   - `database/db.py` 初始化 SQLite，并 seed mock 订单数据。
   - `database/repository.py` 持久化：
     - 消息
     - 会话
     - 工单
     - 订单查询结果
   - 当前会话里会额外记录：
     - `last_intent`
     - `last_risk_level`
     - `needs_handoff`
     - `summary`

10. **实际运营含义**
   - 这套系统现在不是单纯“自动聊天”。
   - 它已经具备一个基础客服运营内核：
     - 自动接待
     - 订单 / 物流查询
     - 售后分流
     - 高风险识别
     - 人工升级
     - 会话追踪
     - 问题摘要沉淀

如果后续继续只做闲鱼和 Ozon，下一步建议优先补：

- 更细的工单摘要（自动带订单号、物流号、最近 3 轮对话）
- Ozon / 闲鱼渠道差异化话术
- 售后 SLA 超时提醒
- 人工接管后的状态回写

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
