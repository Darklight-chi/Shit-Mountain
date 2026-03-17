"""Business policies for different scenarios."""

REFUND_POLICY = {
    "zh": {
        "within_7_days": "收货7天内可申请无理由退货，请提供订单号。",
        "after_7_days": "已超过7天退货期限，建议联系人工客服确认是否符合特殊退货条件。",
        "damaged": "商品破损可申请退货退款，请拍照提供凭证。",
        "wrong_item": "发错商品可免费换货或退款，请提供订单号和照片。",
        "missing_item": "少件问题请提供订单号，我们核实后会尽快补发。",
    },
    "en": {
        "within_7_days": "You can request a return within 7 days of receipt. Please provide your order number.",
        "after_7_days": "The 7-day return window has passed. Please contact our support team for special cases.",
        "damaged": "For damaged items, please provide photos and your order number for a return/refund.",
        "wrong_item": "Wrong item received — we'll arrange a free exchange or refund. Please share your order number and photos.",
        "missing_item": "For missing items, please provide your order number. We'll verify and reship promptly.",
    },
}

ADDRESS_CHANGE_POLICY = {
    "zh": {
        "before_ship": "订单未发货前可以修改地址，请提供新地址和订单号。",
        "after_ship": "订单已发货，暂时无法修改地址，建议联系人工客服处理。",
    },
    "en": {
        "before_ship": "Address can be changed before shipping. Please provide your new address and order number.",
        "after_ship": "Order has shipped — address changes require human assistance.",
    },
}

CANCELLATION_POLICY = {
    "zh": {
        "before_ship": "订单未发货可以取消，请提供订单号。",
        "after_ship": "订单已发货，无法直接取消。您可以收到后申请退货。",
    },
    "en": {
        "before_ship": "Order can be cancelled before shipping. Please provide your order number.",
        "after_ship": "Order has shipped and cannot be cancelled. You may request a return after receiving it.",
    },
}

ESCALATION_TRIGGERS = [
    "投诉", "举报", "骗", "差评", "赔偿", "平台介入", "法律",
    "海关", "扣关", "dispute", "refund now", "chargeback",
    "scam", "report", "lawsuit", "fraud", "骗子", "举报你",
]
