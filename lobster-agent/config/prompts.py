"""Prompt templates for different locales and scenarios."""

SYSTEM_PROMPTS = {
    "zh": (
        "你是一位专业的电商客服数字员工，名叫小龙虾。"
        "你需要礼貌、高效地回答客户问题。"
        "如果遇到无法处理的问题，请建议转人工客服。"
        "回复要简洁、友好、专业，不超过3句话。"
        "不要自行承诺赔偿或做出超出权限的承诺。"
    ),
    "en": (
        "You are a professional e-commerce customer service agent named Lobster. "
        "Answer customer questions politely and efficiently. "
        "If you cannot handle a question, suggest transferring to a human agent. "
        "Keep replies concise, friendly, and professional — no more than 3 sentences. "
        "Never promise compensation or make commitments beyond your authority."
    ),
}

INTENT_CLASSIFICATION_PROMPT = """Classify the user message into one of these intents:
- general_greeting: greetings like hi, hello, 在吗
- presale_product: questions about product details, stock, size, usage
- shipping_time: questions about shipping/delivery time
- order_status: checking order status
- tracking_status: asking about logistics/tracking
- return_refund: return or refund requests
- address_change: wants to change delivery address
- cancellation: wants to cancel order
- complaint: complaints, threats of bad review, fraud accusations
- damaged_or_wrong_item: received wrong/damaged/missing items
- customs_tax: customs, tax, duty questions
- fallback: cannot classify

User message: {message}

Respond with ONLY the intent name, nothing else."""

RISK_DETECTION_PROMPT = """Assess the risk level of this customer message.

Risk levels:
- low: normal inquiry, safe to auto-reply
- medium: after-sales issue, needs careful response, may need human
- high: complaint, compensation demand, abuse, threat, dispute — must escalate

High-risk keywords include: 投诉, 举报, 骗, 差评, 赔偿, 平台介入, 法律, 海关, 扣关, dispute, refund now, chargeback, scam, report, lawsuit

User message: {message}

Respond with ONLY: low, medium, or high"""

RESPONSE_GENERATION_PROMPT = """Based on the following context, generate a customer service reply.

Locale: {locale}
Intent: {intent}
Risk level: {risk_level}
Tool results: {tool_results}
Conversation history: {history}
User message: {message}

Generate a helpful, professional reply in {language}.
Keep it under 3 sentences. Be specific and actionable."""

ESCALATION_SUMMARY_PROMPT = """Generate a brief ticket summary for human handoff.

User message: {message}
Detected intent: {intent}
Risk level: {risk_level}
Conversation history: {history}

Output a JSON with: reason, summary, priority (low/medium/high/urgent)"""
