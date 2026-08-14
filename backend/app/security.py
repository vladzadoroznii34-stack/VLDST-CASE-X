import hashlib,hmac,time,json
from urllib.parse import parse_qsl
from .config import settings
def validate_telegram_init_data(raw):
    d=dict(parse_qsl(raw or "",keep_blank_values=True)); received=d.pop("hash",None)
    if not received: raise ValueError("Missing Telegram initData hash")
    if not settings.bot_token: raise ValueError("BOT_TOKEN is not configured")
    if "auth_date" not in d or time.time()-int(d["auth_date"])>86400: raise ValueError("Expired initData")
    secret=hmac.new(b"WebAppData",settings.bot_token.encode(),hashlib.sha256).digest()
    check=hmac.new(secret,"\n".join(f"{k}={v}" for k,v in sorted(d.items())).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(check,received): raise ValueError("Invalid Telegram initData")
    return d
