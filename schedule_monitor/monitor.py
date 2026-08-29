from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from common.database import models
from common.schedule_sync import (
    diff_lessons,
    display_group_name,
    dump_payload,
    format_lesson,
    load_db_schedule,
    normalize_group_name,
    parse_source_schedule,
)
from .config import MonitorConfig


logger = logging.getLogger(__name__)
SCAN_ADVISORY_LOCK_ID = 2_026_082_900


@dataclass(frozen=True)
class SourceGroup:
    uuid: str
    group_name: str
    display_name: str


@dataclass
class GroupChange:
    source: SourceGroup
    payload: dict
    added: list
    removed: list
    is_new_group: bool


@dataclass
class ScanResult:
    scanned_groups: int
    changes: list[GroupChange]
    warnings: list[str]
    missing_from_site: list[str]


def walk_nodes(value) -> Iterable[dict]:
    if isinstance(value, dict):
        yield value
        for child in value.get("children") or []:
            yield from walk_nodes(child)
    elif isinstance(value, list):
        for item in value:
            yield from walk_nodes(item)


def discover_groups(structure_payload: dict, config: MonitorConfig) -> list[SourceGroup]:
    roots = list(walk_nodes(structure_payload.get("data")))
    faculties = [node for node in roots if node.get("uuid") in config.faculty_uuids]
    found: dict[str, SourceGroup] = {}

    for faculty in faculties:
        for node in walk_nodes(faculty):
            if node.get("nodeType") != "group":
                continue
            display_name = (node.get("abbr") or node.get("name") or "").strip()
            group_name = normalize_group_name(display_name)
            if not group_name.startswith(("uik", "mk")):
                continue
            if not config.include_postgraduates and group_name.endswith("a"):
                continue
            uuid = (node.get("uuid") or "").strip()
            if uuid:
                found[group_name] = SourceGroup(uuid, group_name, display_group_name(group_name))

    return sorted(found.values(), key=lambda group: group.group_name)


def describe_exception(exc: BaseException | None) -> str:
    """Возвращает полезную цепочку ошибок, не включая URL запроса."""
    parts: list[str] = []
    current = exc
    while current is not None and len(parts) < 5:
        detail = str(current).strip()
        label = type(current).__name__
        part = f"{label}: {detail}" if detail else label
        if part not in parts:
            parts.append(part)
        current = current.__cause__ or current.__context__
    return " -> ".join(parts) or "неизвестная ошибка"


async def fetch_json(
    client: httpx.AsyncClient,
    url: str,
    attempts: int = 5,
    timeout: float = 20.0,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("API вернул не JSON-объект")
            return payload
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt < attempts:
                await asyncio.sleep(min(10, 2 ** (attempt - 1)))
    raise RuntimeError(
        f"Не удалось получить {url} после {attempts} попыток: "
        f"{describe_exception(last_error)}"
    )


async def fetch_schedules(
    client: httpx.AsyncClient,
    groups: list[SourceGroup],
    config: MonitorConfig,
) -> tuple[dict[str, dict], list[str]]:
    semaphore = asyncio.Semaphore(config.concurrency)
    payloads: dict[str, dict] = {}
    warnings: list[str] = []

    async def fetch_one(group: SourceGroup):
        async with semaphore:
            try:
                payloads[group.group_name] = await fetch_json(
                    client,
                    config.schedule_url_template.format(uuid=group.uuid),
                    attempts=config.request_attempts,
                    timeout=config.request_timeout,
                )
            except Exception as exc:
                warnings.append(f"{group.display_name}: не удалось получить расписание: {exc}")

    await asyncio.gather(*(fetch_one(group) for group in groups))
    if len(payloads) != len(groups):
        failed_count = len(groups) - len(payloads)
        raise RuntimeError(
            f"Проверка неполная: не удалось скачать {failed_count} из {len(groups)} групп. "
            "Заявка на обновление не создана."
        )
    return payloads, warnings


async def scan_schedules(
    config: MonitorConfig,
    session_factory: sessionmaker,
) -> ScanResult:
    async with httpx.AsyncClient(
        timeout=config.request_timeout,
        follow_redirects=True,
        headers={"User-Agent": "timetable-bmstu-schedule-monitor/1.0"},
    ) as client:
        structure = await fetch_json(
            client,
            config.structure_url,
            attempts=config.request_attempts,
            timeout=config.request_timeout,
        )
        source_groups = discover_groups(structure, config)
        payloads, warnings = await fetch_schedules(client, source_groups, config)

    if not source_groups:
        raise RuntimeError("В структуре BMSTU не найдены группы ИУК/МК КФ МГТУ")

    return compare_schedules(
        config,
        session_factory,
        source_groups,
        payloads,
        warnings,
    )


def compare_schedules(
    config: MonitorConfig,
    session_factory: sessionmaker,
    source_groups: list[SourceGroup],
    payloads: dict[str, dict],
    warnings: list[str] | None = None,
) -> ScanResult:
    warnings = list(warnings or [])

    changes: list[GroupChange] = []
    source_names = {group.group_name for group in source_groups}

    with session_factory() as db:
        db_groups = {
            normalize_group_name(group.name): group
            for group in db.query(models.Group).all()
            if normalize_group_name(group.name).startswith(("uik", "mk"))
            and (config.include_postgraduates or not normalize_group_name(group.name).endswith("a"))
        }

        for source in source_groups:
            payload = payloads.get(source.group_name)
            if payload is None:
                continue

            payload_group = normalize_group_name((payload.get("data") or {}).get("title", ""))
            if payload_group != source.group_name:
                warnings.append(
                    f"{source.display_name}: название ответа BMSTU не совпало "
                    f"({payload_group or 'пусто'})"
                )
                continue

            proposed, parse_errors = parse_source_schedule(payload)
            if parse_errors:
                warnings.append(
                    f"{source.display_name}: расписание не прошло проверку: "
                    + "; ".join(parse_errors[:5])
                )
                continue

            current_group = db_groups.get(source.group_name)
            current = load_db_schedule(db, current_group)

            if not proposed:
                status = "в БД тоже пусто" if not current else f"в БД {len(current)} занятий"
                warnings.append(
                    f"{source.display_name}: BMSTU вернул пустое расписание ({status}); "
                    "очистка не предлагается"
                )
                continue

            added, removed = diff_lessons(current, proposed)
            if added or removed:
                changes.append(
                    GroupChange(
                        source=source,
                        payload=payload,
                        added=added,
                        removed=removed,
                        is_new_group=current_group is None,
                    )
                )

        missing_from_site = sorted(set(db_groups) - source_names)

    return ScanResult(
        scanned_groups=len(source_groups),
        changes=sorted(changes, key=lambda change: change.source.group_name),
        warnings=sorted(warnings),
        missing_from_site=missing_from_site,
    )


def build_report(result: ScanResult, created_at: datetime, timezone_name: str) -> str:
    from zoneinfo import ZoneInfo

    lines = [
        "Проверка расписаний КФ МГТУ: ИУК и МК",
        f"Дата проверки: {created_at.astimezone(ZoneInfo(timezone_name)).strftime('%d.%m.%Y %H:%M:%S %Z')}",
        f"Проверено групп на сайте: {result.scanned_groups}",
        f"Групп с изменениями: {len(result.changes)}",
        "Аспирантура (группы на a): исключена",
        "",
    ]

    if result.changes:
        lines.append("ИЗМЕНЕНИЯ")
        lines.append("=" * 80)
        for change in result.changes:
            new_label = " [НОВАЯ ГРУППА]" if change.is_new_group else ""
            lines.extend(
                [
                    "",
                    f"{change.source.display_name} ({change.source.group_name}){new_label}",
                    f"Добавлено: {len(change.added)}; удалено: {len(change.removed)}",
                ]
            )
            for lesson in change.added:
                lines.append("+ " + format_lesson(lesson))
            for lesson in change.removed:
                lines.append("- " + format_lesson(lesson))
    else:
        lines.append("Изменений расписания не найдено.")

    if result.warnings:
        lines.extend(["", "ПРЕДУПРЕЖДЕНИЯ", "=" * 80])
        lines.extend(f"! {warning}" for warning in result.warnings)

    if result.missing_from_site:
        lines.extend(
            [
                "",
                "ГРУППЫ ИЗ БД, КОТОРЫХ НЕТ В ТЕКУЩЕЙ СТРУКТУРЕ BMSTU",
                "=" * 80,
                "Они только указаны в отчёте и автоматически не удаляются.",
            ]
        )
        lines.extend(f"! {name}" for name in result.missing_from_site)

    return "\n".join(lines).rstrip() + "\n"


def create_review(
    db: Session,
    result: ScanResult,
    report_filename: str,
) -> models.ScheduleReview:
    supersede_pending_reviews(db)

    review = models.ScheduleReview(status="pending", report_filename=report_filename)
    db.add(review)
    db.flush()

    for change in result.changes:
        db.add(
            models.ScheduleReviewGroup(
                review_id=review.id,
                group_name=change.source.group_name,
                display_name=change.source.display_name,
                source_uuid=change.source.uuid,
                source_payload=dump_payload(change.payload),
                added_count=len(change.added),
                removed_count=len(change.removed),
                is_new_group=int(change.is_new_group),
                status="pending",
            )
        )
    db.commit()
    db.refresh(review)
    return review


def supersede_pending_reviews(db: Session) -> None:
    previous = (
        db.query(models.ScheduleReview)
        .filter(models.ScheduleReview.status.in_(("pending", "partially_applied")))
        .all()
    )
    for review in previous:
        review.status = "superseded"
        for group in review.groups:
            if group.status == "pending":
                group.status = "superseded"


async def telegram_request(
    config: MonitorConfig,
    method: str,
    *,
    data: dict,
    files: dict | None = None,
) -> dict:
    url = f"https://api.telegram.org/bot{config.bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=data, files=files)
            response.raise_for_status()
            payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # Не включаем URL запроса в ошибку: в нём находится токен бота.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        suffix = f", HTTP {status}" if status else ""
        raise RuntimeError(
            f"Telegram API {method} недоступен ({type(exc).__name__}{suffix})"
        ) from None
    if not payload.get("ok"):
        raise RuntimeError(f"Telegram API {method}: {payload}")
    return payload["result"]


async def notify_admin(
    config: MonitorConfig,
    result: ScanResult,
    report: str,
    review: models.ScheduleReview | None,
) -> tuple[int, int | None]:
    if result.changes:
        group_items = [
            f"• {change.source.group_name}: +{len(change.added)} / -{len(change.removed)}"
            for change in result.changes
        ]
        visible_items: list[str] = []
        visible_length = 0
        for item in group_items:
            if visible_length + len(item) + 1 > 2800:
                break
            visible_items.append(item)
            visible_length += len(item) + 1
        hidden_count = len(group_items) - len(visible_items)
        if hidden_count:
            visible_items.append(f"…ещё {hidden_count} групп — полный список в файле")
        group_lines = "\n".join(visible_items)
        summary = (
            f"🔎 Еженедельная проверка расписаний завершена.\n"
            f"Найдены изменения в {len(result.changes)} группах:\n{group_lines}\n\n"
            "Ответьте на это сообщение списком групп, которые нужно применить. "
            "Можно написать группы через пробел, запятую или с новой строки.\n"
            "Также доступны ответы: «все» или «отмена»."
        )
    else:
        summary = (
            "✅ Еженедельная проверка расписаний ИУК/МК завершена. "
            f"Проверено групп: {result.scanned_groups}. Изменений не найдено."
        )

    sent_summary = await telegram_request(
        config,
        "sendMessage",
        data={"chat_id": str(config.admin_id), "text": summary},
    )
    summary_id = int(sent_summary["message_id"])

    document_id = None
    if result.changes or result.warnings or result.missing_from_site:
        filename = review.report_filename if review else "schedule_check.txt"
        sent_document = await telegram_request(
            config,
            "sendDocument",
            data={
                "chat_id": str(config.admin_id),
                "caption": "Подробный отчёт по изменениям расписаний",
                "reply_parameters": json.dumps({"message_id": summary_id}),
            },
            files={
                "document": (filename, report.encode("utf-8"), "text/plain; charset=utf-8")
            },
        )
        document_id = int(sent_document["message_id"])
    return summary_id, document_id


async def run_once(
    config: MonitorConfig,
    session_factory: sessionmaker,
    *,
    dry_run: bool = False,
) -> ScanResult:
    lock_db = session_factory()
    lock_acquired = False
    try:
        if lock_db.get_bind().dialect.name == "postgresql":
            lock_acquired = bool(
                lock_db.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"),
                    {"lock_id": SCAN_ADVISORY_LOCK_ID},
                ).scalar()
            )
            if not lock_acquired:
                raise RuntimeError("Другая проверка расписаний уже выполняется")

        started = datetime.now(timezone.utc)
        result = await scan_schedules(config, session_factory)
        filename = f"schedule_changes_{started.strftime('%Y%m%d_%H%M%S')}.txt"
        report = build_report(result, started, config.timezone)

        if dry_run:
            print(report, end="")
            return result

        review = None
        if result.changes:
            with session_factory() as db:
                review = create_review(db, result, filename)
        else:
            # Успешная новая проверка делает старые неподтверждённые снимки устаревшими.
            with session_factory() as db:
                supersede_pending_reviews(db)
                db.commit()

        try:
            summary_id, document_id = await notify_admin(config, result, report, review)
        except Exception as exc:
            if review is not None:
                with session_factory() as db:
                    stored = db.get(models.ScheduleReview, review.id)
                    if stored:
                        stored.status = "notification_failed"
                        stored.error = str(exc)
                        db.commit()
            raise

        if review is not None:
            with session_factory() as db:
                stored = db.get(models.ScheduleReview, review.id)
                stored.telegram_summary_message_id = summary_id
                stored.telegram_document_message_id = document_id
                db.commit()

        logger.info(
            "Проверено %s групп, изменения в %s, предупреждений %s",
            result.scanned_groups,
            len(result.changes),
            len(result.warnings),
        )
        return result
    finally:
        if lock_acquired:
            lock_db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": SCAN_ADVISORY_LOCK_ID},
            )
        lock_db.close()
