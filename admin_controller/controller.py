import http.client
import json
import logging
import os
import socket
import time
from pathlib import Path
from urllib.parse import urlencode


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONTROL_DIR = Path(os.getenv("ADMIN_CONTROL_DIR", "/control"))
DOCKER_SOCKET = os.getenv("DOCKER_SOCKET", "/var/run/docker.sock")
TARGET_PROJECT = os.getenv("TARGET_COMPOSE_PROJECT", "timetable_bmstu")
TARGET_SERVICE = "admin"


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: int = 20):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def _docker_request(method: str, path: str) -> tuple[int, bytes]:
    connection = UnixHTTPConnection(DOCKER_SOCKET)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def _find_admin_container() -> dict:
    filters = {
        "label": [
            f"com.docker.compose.project={TARGET_PROJECT}",
            f"com.docker.compose.service={TARGET_SERVICE}",
            "com.docker.compose.oneoff=False",
        ]
    }
    query = urlencode({"all": "1", "filters": json.dumps(filters)})
    status, body = _docker_request("GET", f"/containers/json?{query}")
    if status != 200:
        raise RuntimeError(f"Docker returned HTTP {status} while locating admin")

    containers = json.loads(body.decode("utf-8"))
    if len(containers) != 1:
        raise RuntimeError(
            f"Expected exactly one {TARGET_PROJECT}/{TARGET_SERVICE} container, "
            f"found {len(containers)}"
        )
    return containers[0]


def set_admin_enabled(enabled: bool) -> dict:
    container = _find_admin_container()
    container_id = container["Id"]
    previous_state = container.get("State", "unknown")
    desired_state = "running" if enabled else "exited"
    changed = previous_state != desired_state

    if enabled and previous_state != "running":
        status, _ = _docker_request("POST", f"/containers/{container_id}/start")
        if status not in (204, 304):
            raise RuntimeError(f"Docker returned HTTP {status} while starting admin")
    elif not enabled and previous_state == "running":
        status, _ = _docker_request("POST", f"/containers/{container_id}/stop?t=10")
        if status not in (204, 304):
            raise RuntimeError(f"Docker returned HTTP {status} while stopping admin")

    return {
        "ok": True,
        "enabled": enabled,
        "changed": changed,
        "previous_state": previous_state,
        "state": desired_state,
    }


def _write_json_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _process_request(path: Path, responses_dir: Path) -> None:
    request_id = path.stem
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        action = payload.get("action")
        if action not in ("start", "stop"):
            raise ValueError("Only start and stop actions are allowed")
        result = set_admin_enabled(action == "start")
        result["request_id"] = request_id
        logger.info("Admin container action completed: %s", action)
    except Exception as exc:
        logger.exception("Admin container action failed")
        result = {"ok": False, "request_id": request_id, "error": str(exc)}
    finally:
        path.unlink(missing_ok=True)

    _write_json_atomic(responses_dir / f"{request_id}.json", result)


def main() -> None:
    requests_dir = CONTROL_DIR / "requests"
    responses_dir = CONTROL_DIR / "responses"
    requests_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Admin controller started for %s/%s", TARGET_PROJECT, TARGET_SERVICE)

    while True:
        for path in sorted(requests_dir.glob("*.json")):
            _process_request(path, responses_dir)
        time.sleep(0.25)


if __name__ == "__main__":
    main()
