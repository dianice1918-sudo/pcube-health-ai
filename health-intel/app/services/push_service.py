import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


def _stringify_data(data: Optional[dict]) -> dict[str, str]:
    if not data:
        return {}
    out: dict[str, str] = {}
    for key, value in data.items():
        out[str(key)] = "" if value is None else str(value)
    return out


def _load_service_account_info() -> dict | None:
    raw_or_path = (os.getenv("FCM_SERVICE_ACCOUNT_JSON", "") or "").strip()
    if raw_or_path:
        if raw_or_path.startswith("{"):
            try:
                return json.loads(raw_or_path)
            except Exception:
                return None
        candidate = Path(raw_or_path)
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                return None

    file_path = (os.getenv("FCM_SERVICE_ACCOUNT_FILE", "") or "").strip()
    if not file_path:
        file_path = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "") or "").strip()
    if not file_path:
        return None

    candidate = Path(file_path)
    if not candidate.exists():
        return None
    try:
        return json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_fcm_access_token_and_project() -> tuple[str, str] | None:
    info = _load_service_account_info()
    if not info:
        return None

    try:
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
    except Exception:
        return None

    scope = os.getenv("FCM_OAUTH_SCOPE", "https://www.googleapis.com/auth/firebase.messaging")
    try:
        creds = service_account.Credentials.from_service_account_info(info, scopes=[scope])
        creds.refresh(Request())
    except Exception:
        return None

    token = getattr(creds, "token", None)
    project_id = (
        (os.getenv("FCM_PROJECT_ID", "") or "").strip()
        or (os.getenv("FIREBASE_PROJECT_ID", "") or "").strip()
        or getattr(creds, "project_id", None)
        or info.get("project_id")
    )
    if not token or not project_id:
        return None
    return token, str(project_id)


def _send_v1(
    *,
    push_token: str,
    title: str,
    body: str,
    data: Optional[dict],
) -> bool:
    auth = _get_fcm_access_token_and_project()
    if not auth:
        return False
    access_token, project_id = auth

    endpoint = os.getenv("FCM_V1_ENDPOINT", f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send")
    payload = {
        "message": {
            "token": push_token,
            "notification": {"title": title, "body": body},
            "data": _stringify_data(data),
        }
    }
    req = urllib.request.Request(
        url=endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=UTF-8",
            "Authorization": f"Bearer {access_token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False


def send_push_notification(
    *,
    push_token: str,
    title: str,
    body: str,
    data: Optional[dict] = None,
) -> bool:
    """
    Send push notification via Firebase Cloud Messaging HTTP v1.
    Requires service-account credentials and project id.
    """
    if not push_token:
        return False
    return _send_v1(push_token=push_token, title=title, body=body, data=data)
