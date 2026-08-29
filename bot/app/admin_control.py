import asyncio
import json
import os
import time
from pathlib import Path
from uuid import uuid4


CONTROL_DIR = Path(os.getenv("ADMIN_CONTROL_DIR", "/var/run/timetable-admin-control"))


class AdminControlError(RuntimeError):
    pass


def _write_request(request_id: str, action: str) -> Path:
    requests_dir = CONTROL_DIR / "requests"
    requests_dir.mkdir(parents=True, exist_ok=True)
    request_path = requests_dir / f"{request_id}.json"
    temporary_path = requests_dir / f"{request_id}.tmp"
    temporary_path.write_text(
        json.dumps({"action": action}, ensure_ascii=False),
        encoding="utf-8",
    )
    temporary_path.replace(request_path)
    return request_path


async def set_admin_container_enabled(enabled: bool, timeout: float = 20.0) -> dict:
    request_id = uuid4().hex
    action = "start" if enabled else "stop"
    request_path = await asyncio.to_thread(_write_request, request_id, action)
    response_path = CONTROL_DIR / "responses" / f"{request_id}.json"
    deadline = time.monotonic() + timeout

    try:
        while time.monotonic() < deadline:
            if response_path.exists():
                payload = json.loads(response_path.read_text(encoding="utf-8"))
                response_path.unlink(missing_ok=True)
                if not payload.get("ok"):
                    raise AdminControlError(payload.get("error") or "Неизвестная ошибка Docker")
                return payload
            await asyncio.sleep(0.2)
    finally:
        request_path.unlink(missing_ok=True)

    raise AdminControlError("Контроллер админки не ответил за 20 секунд")
