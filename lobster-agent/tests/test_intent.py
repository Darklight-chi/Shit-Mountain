"""Test intent classification."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.intent_classifier import classify_intent


def test_greeting():
    assert classify_intent("在吗") == "general_greeting"
    assert classify_intent("hello") == "general_greeting"
    assert classify_intent("hi") == "general_greeting"

def test_presale():
    assert classify_intent("有货吗") == "presale_product"
    assert classify_intent("尺寸是多少") == "presale_product"
    assert classify_intent("Is this in stock?") == "presale_product"

def test_shipping():
    assert classify_intent("多久发货") == "shipping_time"
    assert classify_intent("什么时候发") == "shipping_time"

def test_order():
    assert classify_intent("帮我查一下订单") == "order_status"
    assert classify_intent("my order status") == "order_status"

def test_tracking():
    assert classify_intent("物流到哪了") == "tracking_status"
    assert classify_intent("where is my shipment") == "tracking_status"

def test_refund():
    assert classify_intent("可以退吗") == "return_refund"
    assert classify_intent("I want a refund") == "return_refund"

def test_complaint():
    assert classify_intent("我要投诉") == "complaint"
    assert classify_intent("你们骗人") == "complaint"
    assert classify_intent("This is a scam") == "complaint"

def test_damaged():
    assert classify_intent("发错货了") == "damaged_or_wrong_item"
    assert classify_intent("坏了") == "damaged_or_wrong_item"

def test_customs():
    assert classify_intent("海关扣了怎么办") == "customs_tax"

def test_fallback():
    assert classify_intent("今天天气真好") == "fallback"


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} — {e}")
    print("Done.")
