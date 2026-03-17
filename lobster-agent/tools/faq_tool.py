"""Fixed FAQ lookup — fast answers for common questions."""

FAQ_ZH = {
    "发货": "我们通常在付款后1-2个工作日内发货。",
    "到货": "国内快递一般3-5天送达，偏远地区可能稍长。",
    "退货": "收货7天内支持无理由退货，请保持商品完好。",
    "退款": "退款会在收到退回商品后3-5个工作日内处理。",
    "现货": "商品页面标注'现货'的当天可发，其他需1-2天备货。",
    "包邮": "大部分商品支持包邮，偏远地区可能需补运费。",
    "尺寸": "请查看商品详情页的尺寸表，如有疑问可提供身高体重帮您推荐。",
    "质量": "所有商品均经过质检，如有质量问题可申请退换。",
    "优惠": "当前暂无额外优惠，以页面标价为准。",
}

FAQ_EN = {
    "shipping": "Orders are shipped within 1-2 business days after payment.",
    "delivery": "Standard delivery takes 5-10 business days internationally.",
    "return": "Returns are accepted within 7 days of receipt. Items must be in original condition.",
    "refund": "Refunds are processed within 3-5 business days after we receive the returned item.",
    "in_stock": "Items marked 'In Stock' ship same day. Others require 1-2 days to prepare.",
    "size": "Please refer to the size chart on the product page.",
    "quality": "All items pass quality inspection. Defective items can be exchanged.",
    "discount": "No additional discounts available at this time.",
}


def faq_lookup(message: str, locale: str = "zh") -> str | None:
    """Try to match a FAQ entry. Returns answer or None."""
    faq = FAQ_ZH if locale == "zh" else FAQ_EN
    msg_lower = message.lower()
    for keyword, answer in faq.items():
        if keyword in msg_lower:
            return answer
    return None
