"""Fixed FAQ lookup — fast answers for common questions (Xianyu seller tone)."""

FAQ_ZH = {
    "发货": "亲，拍下后1-2天内发货哈~",
    "到货": "国内快递一般3-5天到，偏远地区可能慢一点~",
    "退货": "收到7天内可以退哈，商品保持完好就行。",
    "退款": "退回的东西收到后3-5个工作日退到账~",
    "现货": "标了现货的当天就发，其他的1-2天备货~",
    "包邮": "大部分都包邮的亲，偏远地区可能要补一点运费。",
    "尺寸": "详情页有尺寸表亲，不确定的话告诉我身高体重帮您推荐~",
    "质量": "都是验过货的亲，有质量问题随时找我处理。",
    "优惠": "目前就是页面这个价了亲，已经很实惠了~",
    "有货": "在的亲，这个有货的~",
    "几件": "亲您看中哪个款呢？我帮您看下库存~",
    "正品": "亲放心，都是正品，可以验货的~",
    "实拍": "图片都是实拍的亲，实物和图片一样~",
    "议价": "亲这个价格已经很实在了，小本生意利润很薄~",
    "砍价": "亲这个价格已经很实在了，小本生意利润很薄~",
    "便宜": "亲这个价格已经很实在了，小本生意利润很薄~",
}

FAQ_EN = {
    "shipping": "Ships within 1-2 business days after payment.",
    "delivery": "Standard delivery takes 5-10 business days internationally.",
    "return": "Returns accepted within 7 days of receipt. Items must be in original condition.",
    "refund": "Refunds processed within 3-5 business days after we receive the return.",
    "in_stock": "Items marked 'In Stock' ship same day. Others need 1-2 days to prepare.",
    "size": "Check the size chart on the product page, or tell me your measurements.",
    "quality": "All items are inspected. Any quality issues — just reach out.",
    "discount": "This is already the best price, sorry!",
    "authentic": "100% authentic, verification welcome.",
}


def faq_lookup(message: str, locale: str = "zh") -> str | None:
    """Try to match a FAQ entry. Returns answer or None."""
    faq = FAQ_ZH if locale == "zh" else FAQ_EN
    msg_lower = message.lower()
    for keyword, answer in faq.items():
        if keyword in msg_lower:
            return answer
    return None
