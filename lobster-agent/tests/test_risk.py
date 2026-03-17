"""Test risk detection."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.risk_detector import detect_risk


def test_low_risk():
    assert detect_risk("在吗") == "low"
    assert detect_risk("多久发货") == "low"

def test_medium_risk():
    assert detect_risk("我想退货") == "medium"
    assert detect_risk("发错了") == "medium"
    assert detect_risk("damaged item", "damaged_or_wrong_item") == "medium"

def test_high_risk():
    assert detect_risk("我要投诉") == "high"
    assert detect_risk("骗子") == "high"
    assert detect_risk("我要赔偿") == "high"
    assert detect_risk("I want a chargeback") == "high"
    assert detect_risk("随便说点什么", "complaint") == "high"


if __name__ == "__main__":
    for name, func in list(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  PASS: {name}")
            except AssertionError as e:
                print(f"  FAIL: {name} — {e}")
    print("Done.")
