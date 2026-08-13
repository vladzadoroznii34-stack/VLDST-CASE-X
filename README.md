# VLDST CASE X

Final from-scratch Telegram Case Bot + Telegram Mini App package.

Bot: @VLDST_CaseXBot  |  Channel: https://t.me/vldst_news  |  Render: vldst-case-xx

## Included
- 10 cases / 90 unique items
- 6 rarities with 40/30/16/5/2.5/1.5% server-side RNG
- PostgreSQL economy and inventory
- idempotent case openings with PostgreSQL transactions and row locking
- inventory selling and pinning
- collection / XP / levels / case unlocks
- Daily / Missions / Achievements / Season / Referrals / Leaderboard
- Telegram Stars shop and official XTR invoice flow
- Telegram Mini App initData validation
- Bot commands /start and /paysupport
- Render configuration and environment-variable-only secrets
- validation scripts and backend tests

## Deploy
Create PostgreSQL `vldst-db`, deploy the Render web service, set BOT_TOKEN, ADMIN_KEY, DATABASE_URL, WEB_APP_URL and TELEGRAM_CHANNEL_URL, then run `python scripts/seed_database.py`. Configure the bot's Main Mini App in BotFather to WEB_APP_URL.

Digital goods inside Telegram use Telegram Stars (`XTR`). The payment flow is invoice → pre-checkout → successful_payment, and the charge ID is stored for deduplication/refunds. Stars never affect case RNG.

Official docs: https://core.telegram.org/bots/payments-stars and https://core.telegram.org/bots/webapps

## Probability note
The supplied rarity figures (40, 30, 16, 5, 2.5, 1.5) add up to 95%, not 100%. The final implementation preserves those ratios and normalizes them server-side to a 100% distribution so there is no undefined 5% outcome.
