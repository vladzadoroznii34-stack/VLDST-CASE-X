from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.game_data import CASES, RARITY_CHANCES
assert len(CASES) == 10
assert sum(RARITY_CHANCES.values()) == 100
codes = [i["item_code"] for c in CASES for i in c["items"]]
assert len(codes) == 90 and len(set(codes)) == 90
assert all(len(c["items"]) == 9 for c in CASES)
print("OK: 10 cases / 90 items / 100% probabilities")
