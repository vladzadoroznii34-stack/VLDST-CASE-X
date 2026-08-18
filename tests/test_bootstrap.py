from pathlib import Path

from backend.app.game_data import CASES


def test_seed_contains_full_catalog():
    root = Path(__file__).resolve().parents[1]
    seed = (root / "database" / "seed.sql").read_text(encoding="utf-8")
    expected_codes = [item["item_code"] for case in CASES for item in case["items"]]
    missing = [code for code in expected_codes if code not in seed]
    assert not missing, f"Missing seed items: {missing[:5]}"
