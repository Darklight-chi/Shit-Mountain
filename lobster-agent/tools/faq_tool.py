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
    "浠锋牸浣庝竴鐐?": "亲，这个价已经尽量压低了，利润真的不多啦，喜欢的话我给您尽快发~",
    "浣庝竴鐐?": "亲，这边已经是比较实在的价格了，真心想要的话可以直接拍，我这边尽快给您安排~",
    "渚垮疁鐐?": "亲，这个价格已经放得比较低啦，基本没什么空间了~",
    "杩樿兘灏?": "亲，这边已经是实在价了哈，您喜欢的话可以直接拍~",
    "鑳戒究瀹滅偣": "亲，这个价格已经尽量给到位了，真心要的话我这边优先给您发~",
    "鏈€浣?": "亲，这边基本就是到手实价了，已经没法再往下压太多啦~",
    "灏戜竴鐐?": "亲，这个价已经比较实在了，小本生意还请理解呀~",
    "鎶归浂": "亲，价格已经尽量压低啦，基本就是实在价了~",
    "鍒€": "亲，这边已经是实在价了哈，空间不大哦~",
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
