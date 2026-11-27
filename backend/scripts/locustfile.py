"""Locust scenario for `just load-test` (scripts/load_test.py prepares the users).

One virtual user = one patient's phone: mostly the home screen's reads, recording doses, now and
then the timeline, the emergency card and a small PDF upload. Think time 2-8 s (a person, not a
script). Dose records reuse today's slots: a repeat is merged by the server (200), not an error.
"""

import base64
import io
import itertools
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from locust import HttpUser, between, task

_USERS: list[dict[str, str]] = json.loads(
    open(os.environ["LOAD_USERS_FILE"], encoding="utf-8").read()  # noqa: SIM115
)
_NEXT = itertools.cycle(_USERS)
_UB = timezone(timedelta(hours=8))  # Ulaanbaatar, no DST (no tzdata needed on Windows)
# an empty A4 page made by pypdfium2 (the upload checks open it the same way); no personal data
_PDF = base64.b64decode(
    "JVBERi0xLjcNCiWhs8XXDQoxIDAgb2JqDQo8PC9QYWdlcyAyIDAgUiAvVHlwZS9DYXRhbG9nPj4NCmVuZG9iag0K"
    "MiAwIG9iag0KPDwvQ291bnQgMS9LaWRzWyA0IDAgUiBdL1R5cGUvUGFnZXM+Pg0KZW5kb2JqDQozIDAgb2JqDQo8"
    "PC9DcmVhdGlvbkRhdGUoRDoyMDI2MTExODA3MTcyOCswMCcwMCcpL0NyZWF0b3IoUERGaXVtKT4+DQplbmRvYmoN"
    "CjQgMCBvYmoNCjw8L01lZGlhQm94WyAwIDAgNTk1IDg0Ml0vUGFyZW50IDIgMCBSIC9SZXNvdXJjZXM8PD4+L1Jv"
    "dGF0ZSAwL1R5cGUvUGFnZT4+DQplbmRvYmoNCnhyZWYNCjAgNQ0KMDAwMDAwMDAwMCA2NTUzNSBmDQowMDAwMDAw"
    "MDE3IDAwMDAwIG4NCjAwMDAwMDAwNjYgMDAwMDAgbg0KMDAwMDAwMDEyMiAwMDAwMCBuDQowMDAwMDAwMTk5IDAw"
    "MDAwIG4NCnRyYWlsZXINCjw8DQovUm9vdCAxIDAgUg0KL0luZm8gMyAwIFINCi9TaXplIDUvSURbPEE5RTA5OEFG"
    "OEU0NDU0MkQ0RENGRjE2MzRBNjY1QUQ2PjxBOUUwOThBRjhFNDQ1NDJENERDRkYxNjM0QTY2NUFENj5dPj4NCnN0"
    "YXJ0eHJlZg0KMjkyDQolJUVPRg0K"
)


class Patient(HttpUser):
    wait_time = between(2, 8)

    def on_start(self) -> None:
        me = next(_NEXT)
        r = self.client.post(
            "/api/v1/auth/refresh", json={"refresh_token": me["refresh"]}, name="refresh"
        )
        r.raise_for_status()  # a user that cannot sign in stops loudly, never silently
        self.h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        self.p = f"/api/v1/patients/{me['patient']}"
        self.med = me["medication"]

    def _get(self, path: str, name: str) -> None:
        self.client.get(path, headers=self.h, name=name)

    @task(10)
    def home(self) -> None:
        self._get(f"{self.p}/dashboard", "dashboard")
        self._get(f"{self.p}/medications", "medications")
        now = datetime.now(_UB)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.client.get(
            f"{self.p}/intakes",
            params={"from": (day - timedelta(days=1)).isoformat(),
                    "to": (day + timedelta(days=1)).isoformat()},
            headers=self.h, name="intakes",
        )  # fmt: skip

    @task(4)
    def record_dose(self) -> None:
        today = datetime.now(_UB).date().isoformat()
        slot = f"{today}T08:00:00+08:00"
        body: dict[str, Any] = {
            "client_id": str(uuid.uuid4()),
            "medication_id": self.med,
            "scheduled_at": slot,
            "status": "taken",
            "taken_at": slot,
        }
        with self.client.post(
            f"{self.p}/intakes", json=body, headers=self.h, name="record dose", catch_response=True
        ) as r:
            if r.status_code in (200, 201, 409):
                r.success()

    @task(2)
    def timeline(self) -> None:
        self._get(f"{self.p}/timeline", "timeline")

    @task(1)
    def emergency_card(self) -> None:
        self._get(f"{self.p}/emergency-card", "emergency card")

    @task(1)
    def upload(self) -> None:
        # every upload a different file, as the API tests make them (a comment after %%EOF)
        data = _PDF + b"\n% " + str(uuid.uuid4()).encode() + b"\n"
        files = {"file": ("result.pdf", io.BytesIO(data), "application/pdf")}
        with self.client.post(
            f"{self.p}/documents", files=files, data={"client_id": str(uuid.uuid4())},
            headers=self.h, name="upload pdf",
            catch_response=True,
        ) as r:  # fmt: skip
            # 429: the per-user upload limit (20/min) is a designed refusal, not a failure
            if r.status_code in (200, 201, 202, 429):
                r.success()
            else:  # the error code only (no values): why an upload was refused
                try:
                    code = r.json().get("code")
                except ValueError:
                    code = None
                r.failure(f"{r.status_code} {code or ''}")
