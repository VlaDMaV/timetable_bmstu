from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, ValidationError, field_validator
    

class Settings(BaseSettings):
    bot_token: SecretStr
    admin_id: int
    admin_password: SecretStr
    admin_public_url: str = ""
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    @field_validator("bot_token")
    @classmethod
    def validate_bot_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value().strip()
        if not token or ":" not in token:
            raise ValueError("BOT_TOKEN должен быть непустым токеном Telegram")
        return SecretStr(token)

    @field_validator("admin_id")
    @classmethod
    def validate_admin_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ADMIN_ID должен быть положительным числом")
        return value

    @field_validator("admin_password")
    @classmethod
    def validate_admin_password(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            raise ValueError("ADMIN_PASSWORD не должен быть пустым")
        return value

    @field_validator("admin_public_url")
    @classmethod
    def validate_admin_public_url(cls, value: str) -> str:
        value = value.strip()
        if value and not value.startswith(("http://", "https://")):
            raise ValueError("ADMIN_PUBLIC_URL должен начинаться с http:// или https://")
        return value


try:
    config = Settings()
except ValidationError as exc:
    invalid_fields = ", ".join(
        ".".join(str(part) for part in error["loc"])
        for error in exc.errors()
    )
    raise RuntimeError(
        "Ошибка конфигурации бота. Проверьте обязательные переменные: "
        f"{invalid_fields or 'BOT_TOKEN, ADMIN_ID, ADMIN_PASSWORD'}"
    ) from None
