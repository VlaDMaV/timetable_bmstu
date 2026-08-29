from aiogram.exceptions import TelegramBadRequest


TELEGRAM_MESSAGE_LIMIT = 4000


def split_message_text(text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Разбивает сообщение по строкам, не разрывая обычные HTML-теги расписания."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append(current.rstrip())
                current = ""
            while len(line) > limit:
                chunks.append(line[:limit])
                line = line[limit:]

        if len(current) + len(line) > limit:
            chunks.append(current.rstrip())
            current = line
        else:
            current += line

    if current:
        chunks.append(current.rstrip())

    return chunks


async def safe_edit_text(message, text: str, **kwargs) -> bool:
    """Игнорирует только безопасный случай повторного редактирования тем же содержимым."""
    try:
        await message.edit_text(text, **kwargs)
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise


async def safe_edit_reply_markup(message, **kwargs) -> bool:
    """Безопасно обрабатывает повторное нажатие на ту же страницу клавиатуры."""
    try:
        await message.edit_reply_markup(**kwargs)
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise


async def edit_or_send_long_message(message, text: str, **kwargs) -> None:
    """Редактирует текущее сообщение и при необходимости отправляет продолжения."""
    chunks = split_message_text(text)
    reply_markup = kwargs.pop("reply_markup", None)

    await safe_edit_text(
        message,
        chunks[0],
        reply_markup=reply_markup if len(chunks) == 1 else None,
        **kwargs,
    )

    for index, chunk in enumerate(chunks[1:], start=1):
        await message.answer(
            chunk,
            reply_markup=reply_markup if index == len(chunks) - 1 else None,
            **kwargs,
        )
