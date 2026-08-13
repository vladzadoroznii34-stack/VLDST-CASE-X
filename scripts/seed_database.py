import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[1]))
from sqlalchemy import select
from backend.app.db import Base,engine,SessionLocal
from backend.app.models import *
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from scripts.validate_cases import CASES
RARITIES=['COMMON','COMMON','UNCOMMON','UNCOMMON','RARE','RARE','EPIC','LEGENDARY','MYTHIC']
SELL={'COMMON':100,'UNCOMMON':250,'RARE':750,'EPIC':2000,'LEGENDARY':7500,'MYTHIC':25000}
def main():
 Base.metadata.create_all(bind=engine);db=SessionLocal()
 try:
  for code,name,price,theme,unlock,names in CASES:
   if not db.scalar(select(Case).where(Case.case_code==code)):db.add(Case(case_code=code,name=name,price=price,theme=theme,unlock_level=unlock))
   for i,(n,r) in enumerate(zip(names,RARITIES),1):
    ic=f'{code}-{i:03d}'
    if not db.scalar(select(Item).where(Item.item_code==ic)):
     total={'COMMON':40,'UNCOMMON':30,'RARE':16,'EPIC':5,'LEGENDARY':2.5,'MYTHIC':1.5}[r];chance=total/(2 if r in ('COMMON','UNCOMMON','RARE') else 1)
     db.add(Item(item_code=ic,case_code=code,name=n,rarity=r,chance=Decimal(str(chance)),sell_price=SELL[r],visual_theme=theme,visual_seed=f'{theme[:2].upper()}-{i:03d}'))
  ach=[('FIRST_CASE','FIRST CASE','Open first case',1,500,100),('COLLECTOR','Collector','Own 10 unique items',10,2000,250),('MYTHIC_HUNTER','Mythic Hunter','Obtain a Mythic item',1,10000,500),('MASTER','VLDST MASTER','Complete 90 items',90,100000,5000),('STREAK_7','7 DAY STREAK','Reach 7 day streak',7,5000,500),('LEVEL_10','Level 10','Reach level 10',10,10000,1000)]
  for a in ach:
   if not db.scalar(select(Achievement).where(Achievement.code==a[0])):db.add(Achievement(code=a[0],name=a[1],description=a[2],target=a[3],reward_coins=a[4],reward_xp=a[5]))
  products=[('PREMIUM_30','Premium 30 days','Cosmetic frame, expanded stats and enhanced daily rewards','Premium',100),('XP_BOOST_7','XP Boost 7 days','Gameplay XP convenience boost','Boosts',75),('SEASON_PASS','Season Pass','Unlock premium Season reward line','Season Pass',250),('PROFILE_FRAME','Legendary Frame','Exclusive cosmetic frame','Special',50)]
  for p in products:
   if not db.scalar(select(ShopProduct).where(ShopProduct.code==p[0])):db.add(ShopProduct(code=p[0],title=p[1],description=p[2],category=p[3],stars_price=p[4]))
  if not db.scalar(select(Season).where(Season.code=='S1')):
   s=datetime.now(timezone.utc);db.add(Season(code='S1',name='VLDST SEASON 1',active=True,starts_at=s,ends_at=s+timedelta(days=60)))
  db.commit();print('Seed complete')
 finally:db.close()
if __name__=='__main__':main()
