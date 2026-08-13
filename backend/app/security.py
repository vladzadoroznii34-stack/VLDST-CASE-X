import hashlib,hmac,time,json
from urllib.parse import parse_qsl
from fastapi import HTTPException
from .config import settings
def validate_telegram_init_data(init_data:str):
    try:
        p=dict(parse_qsl(init_data,keep_blank_values=True)); received=p.pop('hash',None)
        if not received: raise ValueError('missing hash')
        if time.time()-int(p.get('auth_date','0'))>settings.init_data_max_age_seconds: raise ValueError('expired')
        check='\n'.join(f'{k}={v}' for k,v in sorted(p.items()))
        secret=hmac.new(b'WebAppData',settings.bot_token.encode(),hashlib.sha256).digest()
        expected=hmac.new(secret,check.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,received): raise ValueError('bad hash')
        return {'user':json.loads(p['user'])}
    except Exception as e: raise HTTPException(401,f'Invalid Telegram initData: {e}')
