from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    bot_token:str=''; admin_key:str=''; database_url:str='postgresql+psycopg://localhost/vldst'
    web_app_url:str='http://localhost:8000'; telegram_channel_url:str='https://t.me/vldst_news'
    log_level:str='INFO'; rate_limit_per_minute:int=60; init_data_max_age_seconds:int=86400
    model_config=SettingsConfigDict(env_file='.env',extra='ignore')
settings=Settings()
