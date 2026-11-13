from pydantic_settings import BaseSettings, SettingsConfigDict
class Settings(BaseSettings):
    secret_key: str
    access_token_expire_minutes: int = 720
    database_url: str
    admin_username: str = "admin"
    admin_password: str
    admin_full_name: str = "مدیر کل"
    cors_origins: str = "http://localhost:5500"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    @property
    def allowed_origins(self):
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
settings = Settings()
