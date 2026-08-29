from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import or_
from sqlalchemy.orm import Session

from common.database import models
from common.schedule_sync import (
    load_payload,
    parse_admin_group_selection,
    replace_group_schedule,
)
from config import config
from app.admin_auth import is_admin_authenticated
from app import keyboards as kb


router = Router()


async def _require_admin_session(event, state: FSMContext) -> bool:
    if event.from_user.id != config.admin_id:
        if isinstance(event, CallbackQuery):
            await event.answer("У вас нет прав администратора.", show_alert=True)
        else:
            await event.answer("У вас нет прав для выполнения этой команды.")
        return False
    if not await is_admin_authenticated(state, event.from_user.id, config.admin_id):
        text = "Сначала выполните /admin и введите пароль."
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
        return False
    return True


def _queue_schedule_check(db: Session, requested_by: int) -> str:
    active = (
        db.query(models.ScheduleMonitorRun)
        .filter(models.ScheduleMonitorRun.status.in_(("queued", "running")))
        .order_by(models.ScheduleMonitorRun.id.desc())
        .first()
    )
    if active is not None:
        state = "уже выполняется" if active.status == "running" else "уже стоит в очереди"
        return f"Проверка №{active.id} {state}. Дождитесь отчёта."

    run = models.ScheduleMonitorRun(
        requested_by=requested_by,
        status="queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return (
        f"🔎 Проверка расписаний №{run.id} поставлена в очередь. "
        "Результат, файл и инструкция по подтверждению придут отдельными сообщениями."
    )


@router.message(Command("check_schedule", "schedule_check"))
async def request_schedule_check(message: Message, state: FSMContext, db: Session):
    """Ставит ручную проверку в очередь отдельного schedule-monitor."""
    if not await _require_admin_session(message, state):
        return

    await message.answer(_queue_schedule_check(db, message.from_user.id))


@router.callback_query(F.data == "admin_check_schedule")
async def admin_schedule_check(callback: CallbackQuery, state: FSMContext, db: Session):
    if not await _require_admin_session(callback, state):
        return
    await callback.answer()
    await callback.message.edit_text(
        _queue_schedule_check(db, callback.from_user.id),
        reply_markup=kb.admin_menu_keyboard(),
    )


def _find_review(db: Session, telegram_message_id: int):
    return (
        db.query(models.ScheduleReview)
        .filter(
            models.ScheduleReview.status.in_(("pending", "partially_applied")),
            or_(
                models.ScheduleReview.telegram_summary_message_id == telegram_message_id,
                models.ScheduleReview.telegram_document_message_id == telegram_message_id,
            ),
        )
        .order_by(models.ScheduleReview.id.desc())
        .first()
    )


@router.message(
    F.from_user.id == config.admin_id,
    F.reply_to_message,
    F.text,
    ~F.text.startswith("/"),
)
async def approve_schedule_update(message: Message, state: FSMContext, db: Session):
    """Применяет только группы из ответа администратора на сообщение мониторинга."""
    review = _find_review(db, message.reply_to_message.message_id)
    if review is None:
        return
    if not await _require_admin_session(message, state):
        return

    action, requested = parse_admin_group_selection(message.text)
    pending_rows = [group for group in review.groups if group.status == "pending"]
    pending_by_name = {group.group_name: group for group in pending_rows}

    if action == "cancel":
        for group in pending_rows:
            group.status = "cancelled"
        review.status = "cancelled"
        db.commit()
        await message.answer(
            f"Заявка №{review.id} отменена. Расписание в БД не изменено."
        )
        return

    if not pending_rows:
        await message.answer("В этой заявке больше нет неприменённых групп.")
        return

    selected_names = sorted(pending_by_name) if action == "all" else requested
    if not selected_names:
        await message.answer(
            "Не удалось распознать группы. Напишите, например: "
            "mk2-72b, uik3-52b — либо «все» или «отмена»."
        )
        return

    unknown = sorted(set(selected_names) - set(pending_by_name))
    if unknown:
        await message.answer(
            "Этих групп нет среди неприменённых изменений заявки №"
            f"{review.id}: {', '.join(unknown)}. Ничего не изменено."
        )
        return

    results = []
    try:
        # Одна транзакция на весь выбранный список: частичного обновления не будет.
        for group_name in selected_names:
            row = pending_by_name[group_name]
            old_count, new_count, created_group = replace_group_schedule(
                db,
                group_name,
                load_payload(row.source_payload),
            )
            row.status = "applied"
            row.applied_at = datetime.now(timezone.utc)
            row.error = None
            results.append((group_name, old_count, new_count, created_group))

        remaining = any(
            group.status == "pending" and group.group_name not in selected_names
            for group in review.groups
        )
        review.status = "partially_applied" if remaining else "applied"
        db.commit()
    except Exception as exc:
        db.rollback()
        await message.answer(
            "❌ Обновление отменено целиком из-за ошибки. Старое расписание сохранено.\n"
            f"Причина: {exc}"
        )
        return

    details = "\n".join(
        f"• {name}: было {old_count}, стало {new_count}"
        + ("; группа создана" if created_group else "")
        for name, old_count, new_count, created_group in results
    )
    await message.answer(
        f"✅ Заявка №{review.id}: изменения применены атомарно.\n{details}\n"
        "ID существующих групп и связи с пользователями сохранены."
    )
