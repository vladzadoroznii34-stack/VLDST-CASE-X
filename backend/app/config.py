from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    bot_token: str=""
    admin_key: str=""
    admin_telegram_ids: str=""
    web_app_url: str="https://vldst-case-x-1.onrender.com"
    database_url: str=""
    telegram_channel_url: str="https://t.me/vldst_news"
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")
settings=Settings()
