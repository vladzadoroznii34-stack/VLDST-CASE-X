from datetime import datetime,timezone,timedelta
import secrets
from fastapi import APIRouter,Depends,Header,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import *
from .schemas import *
from .security import validate_telegram_init_data
from .game import *
from .config import settings
router=APIRouter(prefix='/api')
def current_user(db=Depends(get_db),x_telegram_init_data=Header(...,alias='X-Telegram-Init-Data')):
    tg=validate_telegram_init_data(x_telegram_init_data)['user']; u=db.scalar(select(User).where(User.telegram_id==int(tg['id'])))
    if not u:u=User(telegram_id=int(tg['id']),username=tg.get('username'),first_name=tg.get('first_name'));db.add(u);db.flush()
    else:u.username=tg.get('username',u.username);u.first_name=tg.get('first_name',u.first_name)
    return u
def out(u):return {'telegram_id':u.telegram_id,'username':u.username,'first_name':u.first_name,'coins':u.coins,'gems':u.gems,'tickets':u.tickets,'xp':u.xp,'level':u.level,'daily_streak':u.daily_streak,'premium':u.premium,'notifications_enabled':u.notifications_enabled,'performance_mode':u.performance_mode,'sound_enabled':u.sound_enabled}
def tx(db,u,amount,kind,ref=None):u.coins+=amount;db.add(EconomyTransaction(user_id=u.id,amount=amount,balance_after=u.coins,kind=kind,reference_id=ref))
@router.get('/meta')
def meta(db:Session=Depends(get_db)):
 return {'channel_url':settings.telegram_channel_url,'cases':[{'case_code':c.case_code,'name':c.name,'price':c.price,'theme':c.theme,'unlock_level':c.unlock_level} for c in db.scalars(select(Case).where(Case.active==True).order_by(Case.id))]}
@router.post('/auth')
def auth(req:AuthRequest,db:Session=Depends(get_db)):
 tg=validate_telegram_init_data(req.init_data)['user'];u=db.scalar(select(User).where(User.telegram_id==int(tg['id'])))
 created=False
 if not u:u=User(telegram_id=int(tg['id']),username=tg.get('username'),first_name=tg.get('first_name'));db.add(u);db.flush();created=True
 if created and req.referral_code:
  try:
   rid=int(req.referral_code.replace('ref_',''));r=db.scalar(select(User).where(User.telegram_id==rid))
   if r and r.id!=u.id:db.add(Referral(referrer_id=r.id,referred_id=u.id))
  except:pass
 db.commit();return out(u)
@router.get('/profile')
def profile(u=Depends(current_user)):return out(u)
@router.get('/cases')
def cases(db:Session=Depends(get_db),u=Depends(current_user)):
 return [{'case_code':c.case_code,'name':c.name,'price':c.price,'theme':c.theme,'unlock_level':c.unlock_level,'unlocked':u.level>=c.unlock_level} for c in db.scalars(select(Case).where(Case.active==True).order_by(Case.id))]
@router.post('/cases/open')
def open_case(req:OpenRequest,db:Session=Depends(get_db),u=Depends(current_user)):
 ex=db.scalar(select(CaseOpening).where(CaseOpening.user_id==u.id,CaseOpening.request_id==req.request_id))
 if ex:
  it=db.scalar(select(Item).where(Item.item_code==ex.item_code));return {'request_id':req.request_id,'duplicate':True,'item':{'item_code':it.item_code,'name':it.name,'rarity':it.rarity,'visual_theme':it.visual_theme,'visual_seed':it.visual_seed},'coins':u.coins,'xp':u.xp,'level':u.level}
 u=db.scalar(select(User).where(User.id==u.id).with_for_update());c=db.scalar(select(Case).where(Case.case_code==req.case_code,Case.active==True))
 if not c:raise HTTPException(404,'Case not found')
 if u.level<c.unlock_level:raise HTTPException(403,'Case locked')
 if u.coins<c.price:raise HTTPException(400,'INSUFFICIENT_COINS')
 try:
  tx(db,u,-c.price,'CASE_OPEN',req.request_id);r=secure_rarity();items=list(db.scalars(select(Item).where(Item.case_code==c.case_code,Item.rarity==r)));it=items[secrets.randbelow(len(items))]
  inv=db.scalar(select(Inventory).where(Inventory.user_id==u.id,Inventory.item_code==it.item_code).with_for_update())
  if inv:inv.quantity+=1
  else:db.add(Inventory(user_id=u.id,item_code=it.item_code))
  add_xp(u,25+(50 if not inv else 0));db.add(CaseOpening(user_id=u.id,case_code=c.case_code,item_code=it.item_code,rarity=it.rarity,request_id=req.request_id));db.commit()
 except Exception:db.rollback();raise
 return {'request_id':req.request_id,'item':{'item_code':it.item_code,'name':it.name,'rarity':it.rarity,'visual_theme':it.visual_theme,'visual_seed':it.visual_seed},'coins':u.coins,'xp':u.xp,'level':u.level}
@router.post('/cases/open-multi')
def multi(count:int,case_code:str,db:Session=Depends(get_db),u=Depends(current_user)):
 if count not in (1,3,5,10):raise HTTPException(400,'count must be 1,3,5,10')
 u=db.scalar(select(User).where(User.id==u.id).with_for_update());c=db.scalar(select(Case).where(Case.case_code==case_code,Case.active==True))
 if not c:raise HTTPException(404,'Case not found')
 if u.level<c.unlock_level:raise HTTPException(403,'Case locked')
 total=c.price*count
 if u.coins<total:raise HTTPException(400,'INSUFFICIENT_COINS')
 tx(db,u,-total,'MULTI_CASE_OPEN',case_code);res=[]
 for _ in range(count):
  r=secure_rarity();items=list(db.scalars(select(Item).where(Item.case_code==case_code,Item.rarity==r)));it=items[secrets.randbelow(len(items))];inv=db.scalar(select(Inventory).where(Inventory.user_id==u.id,Inventory.item_code==it.item_code).with_for_update())
  if inv:inv.quantity+=1
  else:db.add(Inventory(user_id=u.id,item_code=it.item_code))
  add_xp(u,25+(50 if not inv else 0));db.add(CaseOpening(user_id=u.id,case_code=case_code,item_code=it.item_code,rarity=it.rarity,request_id=secrets.token_hex(16)));res.append({'item_code':it.item_code,'name':it.name,'rarity':it.rarity,'visual_theme':it.visual_theme,'visual_seed':it.visual_seed})
 db.commit();return {'results':res,'coins':u.coins,'xp':u.xp,'level':u.level}
@router.get('/inventory')
def inventory(db:Session=Depends(get_db),u=Depends(current_user)):
 rows=db.execute(select(Inventory,Item).join(Item,Inventory.item_code==Item.item_code).where(Inventory.user_id==u.id)).all();return [{'item_code':i.item_code,'name':it.name,'rarity':it.rarity,'quantity':i.quantity,'pinned':i.pinned,'sell_price':it.sell_price,'visual_theme':it.visual_theme,'visual_seed':it.visual_seed} for i,it in rows]
@router.post('/inventory/sell')
def sell(req:SellRequest,db:Session=Depends(get_db),u=Depends(current_user)):
 u=db.scalar(select(User).where(User.id==u.id).with_for_update());inv=db.scalar(select(Inventory).where(Inventory.user_id==u.id,Inventory.item_code==req.item_code).with_for_update());it=db.scalar(select(Item).where(Item.item_code==req.item_code))
 if not inv or not it or inv.quantity<req.quantity:raise HTTPException(400,'Not enough items')
 if inv.pinned:raise HTTPException(400,'Unpin item before selling')
 inv.quantity-=req.quantity
 if inv.quantity==0:db.delete(inv)
 tx(db,u,it.sell_price*req.quantity,'ITEM_SELL',it.item_code);db.commit();return {'coins':u.coins}
@router.post('/inventory/pin')
def pin(req:PinRequest,db:Session=Depends(get_db),u=Depends(current_user)):
 i=db.scalar(select(Inventory).where(Inventory.user_id==u.id,Inventory.item_code==req.item_code))
 if not i:raise HTTPException(404,'Item not found')
 i.pinned=req.pinned;db.commit();return {'ok':True}
@router.get('/collection')
def collection(db:Session=Depends(get_db),u=Depends(current_user)):
 own={i.item_code:i.quantity for i in db.scalars(select(Inventory).where(Inventory.user_id==u.id))};return [{'item_code':it.item_code,'name':it.name,'rarity':it.rarity,'owned':it.item_code in own,'quantity':own.get(it.item_code,0),'case_code':it.case_code,'visual_theme':it.visual_theme,'visual_seed':it.visual_seed} for it in db.scalars(select(Item).order_by(Item.case_code,Item.id))]
@router.get('/daily')
def daily(u=Depends(current_user)):
 now=datetime.now(timezone.utc);available=not u.last_daily or now.date()>u.last_daily.date();day=u.daily_streak%7+1;rw={1:(500,0),2:(750,0),3:(1000,0),4:(1500,0),5:(2000,0),6:(3000,0),7:(5000,1)}[day];return {'available':available,'streak':u.daily_streak,'day':day,'reward_coins':rw[0],'reward_tickets':rw[1]}
@router.post('/daily/claim')
def daily_claim(db:Session=Depends(get_db),u=Depends(current_user)):
 now=datetime.now(timezone.utc)
 if u.last_daily and now.date()<=u.last_daily.date():raise HTTPException(400,'Daily already claimed')
 u.daily_streak=u.daily_streak+1 if u.last_daily and now.date()-u.last_daily.date()==timedelta(days=1) else 1;day=(u.daily_streak-1)%7+1;coins,tickets={1:(500,0),2:(750,0),3:(1000,0),4:(1500,0),5:(2000,0),6:(3000,0),7:(5000,1)}[day];tx(db,u,coins,'DAILY');u.tickets+=tickets;add_xp(u,100);u.last_daily=now;db.commit();return out(u)
@router.get('/missions')
def missions():return {'daily':[{'code':'OPEN_1','title':'Открыть 1 кейс','target':1},{'code':'OPEN_3','title':'Открыть 3 кейса','target':3},{'code':'SELL_1','title':'Продать предмет','target':1},{'code':'NEW_1','title':'Получить новый предмет','target':1},{'code':'EARN_5000','title':'Заработать 5000 Coins','target':5000}],'weekly':[{'code':'OPEN_20','title':'Открыть 20 кейсов','target':20},{'code':'NEW_10','title':'Получить 10 новых предметов','target':10},{'code':'DAILY_15','title':'Выполнить 15 Daily Missions','target':15}]}
@router.get('/achievements')
def achievements(db:Session=Depends(get_db),u=Depends(current_user)):
 return [{'code':a.code,'name':a.name,'description':a.description,'target':a.target} for a in db.scalars(select(Achievement).order_by(Achievement.id))]
@router.get('/season')
def season(db:Session=Depends(get_db),u=Depends(current_user)):
 s=db.scalar(select(Season).where(Season.active==True).order_by(Season.id.desc()));return {'active':bool(s),'code':s.code if s else None,'name':s.name if s else None,'levels':50}
@router.get('/referrals')
def referrals(db:Session=Depends(get_db),u=Depends(current_user)):
 rows=db.scalars(select(Referral).where(Referral.referrer_id==u.id)).all();return {'link':f'https://t.me/VLDST_CaseXBot?start=ref_{u.telegram_id}','invited':len(rows),'active':sum(r.active for r in rows),'earned':0}
@router.get('/leaderboard')
def leaderboard(db:Session=Depends(get_db)):return [{'rank':i+1,'username':u.username or u.first_name or str(u.telegram_id),'level':u.level,'xp':u.xp} for i,u in enumerate(db.scalars(select(User).order_by(User.xp.desc()).limit(100)))]
@router.get('/shop')
def shop(db:Session=Depends(get_db)):return [{'code':p.code,'title':p.title,'description':p.description,'category':p.category,'stars_price':p.stars_price} for p in db.scalars(select(ShopProduct).where(ShopProduct.active==True).order_by(ShopProduct.id))]
@router.post('/shop/invoice')
async def invoice(req:PaymentRequest,db:Session=Depends(get_db),u=Depends(current_user)):
 from aiogram import Bot
 p=db.scalar(select(ShopProduct).where(ShopProduct.code==req.product_code,ShopProduct.active==True))
 if not p:raise HTTPException(404,'Product not found')
 payload=f'vldst:{u.telegram_id}:{p.code}:{secrets.token_hex(12)}';db.add(Payment(user_id=u.id,product_code=p.code,payload=payload,currency='XTR',amount=p.stars_price));db.commit();bot=Bot(settings.bot_token)
 try: link=await bot.create_invoice_link(title=p.title,description=p.description,payload=payload,currency='XTR',prices=[{'label':p.title,'amount':p.stars_price}])
 finally:await bot.session.close()
 return {'invoice_url':link,'payload':payload}
@router.get('/history')
def history(db:Session=Depends(get_db),u=Depends(current_user)):return [{'case_code':x.case_code,'item_code':x.item_code,'rarity':x.rarity,'time':x.created_at.isoformat()} for x in db.scalars(select(CaseOpening).where(CaseOpening.user_id==u.id).order_by(CaseOpening.created_at.desc()).limit(50))]
@router.post('/settings')
def settings_update(payload:dict,db:Session=Depends(get_db),u=Depends(current_user)):
 for k in ('notifications_enabled','performance_mode','sound_enabled'):
  if k in payload:setattr(u,k,bool(payload[k]))
 db.commit();return out(u)
