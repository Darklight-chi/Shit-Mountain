"""Test business tools."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.db import init_db
from tools.faq_tool import faq_lookup
from tools.order_tool import extract_order_id, query_order, resolve_order
from tools.refund_tool import check_address_change, check_cancellation, check_refund
from tools.tracking_tool import query_tracking_for_order
from tools.translation_tool import detect_language


def test_faq():
    result = faq_lookup("多久发货", "zh")
    assert result is not None and "发货" in result
    assert faq_lookup("shipping", "en") is not None
    assert faq_lookup("随便说点什么", "zh") is None


def test_order_id_extract():
    assert extract_order_id("帮我查订单A10239") == "A10239"
    assert extract_order_id("order B20001 please") == "B20001"
    assert extract_order_id("没有订单号") is None


def test_order_query():
    init_db()
    result = query_order("查一下A10239", "demo_user", "zh")
    assert "A10239" in result
    assert "已发货" in result


def test_resolve_order_uses_latest_order_when_missing_id():
    init_db()
    result = resolve_order("帮我看看订单进度", "demo_user")
    assert result is not None
    assert result["order_id"] == "A10239"


def test_tracking_query_for_order():
    init_db()
    result = query_tracking_for_order("物流到哪了 A10239", "demo_user", "zh")
    assert "SF1234567890" in result or "顺丰" in result


def test_refund():
    r = check_refund("return_refund", "zh")
    assert "7天" in r


def test_address():
    r = check_address_change("paid", "zh")
    assert "修改" in r
    r2 = check_address_change("shipped", "zh")
    assert "人工" in r2


def test_cancellation():
    r = check_cancellation("paid", "zh")
    assert "取消" in r


def test_language_detect():
    assert detect_language("你好") == "zh"
    assert detect_language("Hello there") == "en"
    assert detect_language("Where is my order A10239?") == "en"


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} -- {e}")
    print("Done.")
