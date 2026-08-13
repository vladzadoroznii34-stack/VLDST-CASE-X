import asyncio
from aiogram import Bot,Dispatcher,F
from aiogram.filters import CommandStart,Command
from aiogram.types import Message,PreCheckoutQuery,InlineKeyboardMarkup,InlineKeyboardButton
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.models import Payment,User
from sqlalchemy import select
from datetime import datetime,timezone

dp=Dispatcher()
@dp.message(CommandStart())
async def start(m:Message):
 await m.answer('🎁 <b>Добро пожаловать в VLDST CASE X</b>\n\nОткрывай кейсы, собирай коллекцию, выполняй Daily и Missions.',parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🚀 ИГРАТЬ',web_app={'url':settings.web_app_url})]]))
@dp.message(Command('paysupport'))
async def paysupport(m:Message):await m.answer('По вопросам оплаты укажите Telegram ID и детали покупки.')
@dp.pre_checkout_query()
async def pre(q:PreCheckoutQuery):
 db=SessionLocal()
 try:
  p=db.scalar(select(Payment).where(Payment.payload==q.invoice_payload,Payment.status=='created'))
  await q.answer(ok=bool(p),error_message=None if p else 'Заказ не найден или уже обработан.')
 finally:db.close()
@dp.message(F.successful_payment)
async def paid(m:Message):
 sp=m.successful_payment;db=SessionLocal()
 try:
  p=db.scalar(select(Payment).where(Payment.payload==sp.invoice_payload).with_for_update())
  if not p or p.status=='paid':return
  if sp.currency!='XTR' or sp.total_amount!=p.amount:return
  p.status='paid';p.telegram_payment_charge_id=sp.telegram_payment_charge_id;p.paid_at=datetime.now(timezone.utc)
  u=db.get(User,p.user_id)
  if p.product_code=='PREMIUM_30':u.premium=True
  db.commit();await m.answer('✅ Покупка активирована.')
 finally:db.close()
async def main():await dp.start_polling(Bot(settings.bot_token))
if __name__=='__main__':asyncio.run(main())
