import hmac


ADMIN_AUTH_DATA_KEY = "admin_authenticated"


def password_matches(provided: str, expected: str) -> bool:
    """Сравнивает пароль без утечек через обычное незащищённое сравнение."""
    return bool(expected) and hmac.compare_digest(provided or "", expected)


async def is_admin_authenticated(state, user_id: int, admin_id: int) -> bool:
    if user_id != admin_id:
        return False
    data = await state.get_data()
    return bool(data.get(ADMIN_AUTH_DATA_KEY))


async def mark_admin_authenticated(state) -> None:
    await state.update_data(**{ADMIN_AUTH_DATA_KEY: True})
