from backend.app.game_data import CASES,RARITY_CHANCES
def test_catalog():
 assert len(CASES)==10
 assert sum(RARITY_CHANCES.values())==100
 assert sum(len(c['items']) for c in CASES)==90
