# VLDST CASE X — FINAL RELEASE

Premium Telegram Mini App for VLDST CASE X.

## Final build

- Bright VLDST visual system: Orange + Purple + Neon Blue.
- Mobile-first gaming interface with glass/metal cards, glow, gradients and responsive layouts.
- VLDST-branded case and item artwork wired through API `image_url`.
- Case opening, inventory, collection and selling/pinning.
- Daily rewards, missions, achievements and season progression.
- Telegram Stars shop/invoices.
- Mini-games, advertising tasks, referrals and leaderboard.
- History and promo codes.
- Owner-only administration: users, balances, inventory grants, ads, Stars/payments, promos, audit and catalog.
- Telegram WebApp authentication.
- PostgreSQL schema/bootstrap and Render deployment configuration.
- Telegram bot polling is started by the backend when `BOT_TOKEN` is configured.

## Runtime

Backend: FastAPI + SQLAlchemy/psycopg  
Frontend: vanilla HTML/CSS/JS  
Bot: aiogram  
Database: PostgreSQL  
Hosting: Render / Docker

## Required Render environment variables

- `BOT_TOKEN`
- `DATABASE_URL`
- `ADMIN_KEY`
- `ADMIN_TELEGRAM_IDS`

Optional:
- `WEB_APP_URL`
- `TELEGRAM_CHANNEL_URL`

## Local checks

```bash
python -m py_compile backend/app/main.py bot/main.py
python -m pytest -q
node --check frontend/public/app.js
```

## Production

Push the repository to GitHub and deploy the `main` branch through Render. Open the Mini App from the Telegram bot after the deploy is live.

Important: only one running instance may use Telegram long polling for the same bot token. Stop any old V8/local bot before starting the final production bot.
