"""Caregiver routes (Phase 2.8d): invite by username, answer, manage, alerts, leave."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack import consents
from labtrack.db.sql import bound_text

from .conftest import ClientFactory
from .test_patients import REQUIRED, _child_birth, _create, _signed_in

pytestmark = pytest.mark.db

Headers = dict[str, str]
SHARING = {
    "kind": "caregiver_sharing",
    "version": consents.VERSIONS["caregiver_sharing"],
    "granted": True,
}


async def _username(owner_engine: AsyncEngine, user: UUID) -> str:
    async with owner_engine.connect() as conn:
        name: str = (
            await conn.execute(
                bound_text("select username::text from users where id = :u"), {"u": user}
            )
        ).scalar_one()
    return name


async def _share(c: AsyncClient, h: Headers, granted: bool = True) -> None:
    r = await c.post(
        "/api/v1/me/consents", json={"items": [{**SHARING, "granted": granted}]}, headers=h
    )
    assert r.status_code == 204


async def _family(
    c: AsyncClient, owner_engine: AsyncEngine
) -> tuple[Headers, str, UUID, Headers, str]:
    """An owner with a profile (and the sharing consent), and a would-be caregiver."""
    _, owner = await _signed_in(c, owner_engine)
    _, profile = await _create(c, owner, full_name="Бат", relation="self")
    await _share(c, owner)
    carer_id, carer = await _signed_in(c, owner_engine)
    return (
        owner,
        f"/api/v1/patients/{profile['id']}",
        carer_id,
        carer,
        await _username(owner_engine, carer_id),
    )


async def _accepted(
    c: AsyncClient, owner_engine: AsyncEngine
) -> tuple[Headers, str, UUID, Headers]:
    owner, base, carer_id, carer, name = await _family(c, owner_engine)
    assert (
        await c.post(f"{base}/caregiver-invitations", json={"username": name}, headers=owner)
    ).status_code == 202
    [inv] = (await c.get("/api/v1/me/caregiver-invitations", headers=carer)).json()
    r = await c.post(
        "/api/v1/me/caregiver-invitations/respond",
        json={"invitation_id": inv["id"], "accept": True},
        headers=carer,
    )
    assert r.status_code == 204
    return owner, base, carer_id, carer


async def test_invite_accept_and_the_owner_sees_the_caregiver(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, carer_id, carer, name = await _family(c, owner_engine)
        # the same answer for a real username and for nobody (no id, no body)
        real = await c.post(f"{base}/caregiver-invitations", json={"username": name}, headers=owner)
        nobody = await c.post(
            f"{base}/caregiver-invitations",
            json={"username": f"x{uuid4().hex[:10]}"},
            headers=owner,
        )
        assert (real.status_code, real.content) == (nobody.status_code, nobody.content)
        assert real.status_code == 202
        listed = (await c.get(f"{base}/caregivers", headers=owner)).json()
        assert listed["caregivers"] == []
        [pending] = listed["invitations"]
        assert pending["username"] == name  # decision (a): the username, no display name
        assert set(pending) == {"id", "username", "created_at", "expires_at"}

        # the invited person sees who asks, for which profile; nothing before accepting
        assert (await c.get(base, headers=carer)).status_code == 404
        [inv] = (await c.get("/api/v1/me/caregiver-invitations", headers=carer)).json()
        assert inv["inviter_name"] == "Тест"
        assert "patient_name" not in inv  # no profile name before accepting (Q45)
        assert "Бат" not in str(inv)
        r = await c.post(
            "/api/v1/me/caregiver-invitations/respond",
            json={"invitation_id": inv["id"], "accept": True},
            headers=carer,
        )
        assert r.status_code == 204
        assert (await c.get(base, headers=carer)).json()["access_level"] == "caregiver"
        listed = (await c.get(f"{base}/caregivers", headers=owner)).json()
        assert listed["invitations"] == []
        [person] = listed["caregivers"]
        assert person["user_id"] == str(carer_id)
        assert (person["display_name"], person["missed_dose_after_min"]) == ("Тест", None)
        assert person["since"] is not None
        # a caregiver does not manage caregivers
        r = await c.get(f"{base}/caregivers", headers=carer)
        assert (r.status_code, r.json()["code"]) == (403, "caregiver.owner_only")
        r = await c.post(f"{base}/caregiver-invitations", json={"username": name}, headers=carer)
        assert r.status_code == 403


async def test_no_invitation_without_the_sharing_consent_nor_on_a_childs_profile(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, owner = await _signed_in(c, owner_engine)
        _, profile = await _create(c, owner, full_name="Бат", relation="self")
        base = f"/api/v1/patients/{profile['id']}"
        carer_id, _ = await _signed_in(c, owner_engine)
        name = await _username(owner_engine, carer_id)
        r = await c.post(f"{base}/caregiver-invitations", json={"username": name}, headers=owner)
        assert (r.status_code, r.json()["code"]) == (409, "caregiver.consent_required")
        await _share(c, owner)
        _, child = await _create(
            c, owner, full_name="Тэмүүлэн", relation="child", birth_date=_child_birth()
        )
        r = await c.post(
            "/api/v1/me/consents",
            json={"items": REQUIRED, "patient_id": child["id"]},
            headers=owner,
        )
        assert r.status_code == 204
        r = await c.post(
            f"/api/v1/patients/{child['id']}/caregiver-invitations",
            json={"username": name},
            headers=owner,
        )
        assert (r.status_code, r.json()["code"]) == (409, "caregiver.minor_profile")
        r = await c.post(
            f"/api/v1/patients/{child['id']}/caregiver-invitations",
            json={"username": f"x{uuid4().hex[:10]}"},
            headers=owner,
        )
        assert (r.status_code, r.json()["code"]) == (409, "caregiver.minor_profile")
        # the sharing consent is the user's own, never one given for a profile
        r = await c.post(
            "/api/v1/me/consents",
            json={"items": [SHARING], "patient_id": child["id"]},
            headers=owner,
        )
        assert r.status_code == 422
        for bad in ("Bad Name", "ab", "x" * 33, ""):
            r = await c.post(f"{base}/caregiver-invitations", json={"username": bad}, headers=owner)
            assert r.status_code == 422


async def test_decline_cancel_and_strangers(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, _, carer, name = await _family(c, owner_engine)
        _, stranger = await _signed_in(c, owner_engine)
        await c.post(f"{base}/caregiver-invitations", json={"username": name}, headers=owner)
        [inv] = (await c.get("/api/v1/me/caregiver-invitations", headers=carer)).json()
        # only the invited person answers; to anyone else it does not exist
        for who in (stranger, owner):
            r = await c.post(
                "/api/v1/me/caregiver-invitations/respond",
                json={"invitation_id": inv["id"], "accept": True},
                headers=who,
            )
            assert (r.status_code, r.json()["code"]) == (404, "caregiver.invitation_not_found")
        assert (await c.get("/api/v1/me/caregiver-invitations", headers=stranger)).json() == []
        # the owner cancels: the invitation is gone for the invited person
        [pending] = (await c.get(f"{base}/caregivers", headers=owner)).json()["invitations"]
        r = await c.delete(f"{base}/caregiver-invitations/{pending['id']}", headers=owner)
        assert r.status_code == 204
        assert (await c.get("/api/v1/me/caregiver-invitations", headers=carer)).json() == []
        r = await c.delete(f"{base}/caregiver-invitations/{pending['id']}", headers=owner)
        assert r.status_code == 404
        # a stranger reaches nothing of the profile
        assert (await c.get(f"{base}/caregivers", headers=stranger)).status_code == 404

        # a "no" is final for 30 days (no notice spam)
        await c.post(f"{base}/caregiver-invitations", json={"username": name}, headers=owner)
        [inv] = (await c.get("/api/v1/me/caregiver-invitations", headers=carer)).json()
        r = await c.post(
            "/api/v1/me/caregiver-invitations/respond",
            json={"invitation_id": inv["id"], "accept": False},
            headers=carer,
        )
        assert r.status_code == 204
        await c.post(f"{base}/caregiver-invitations", json={"username": name}, headers=owner)
        assert (await c.get("/api/v1/me/caregiver-invitations", headers=carer)).json() == []
        assert (await c.get(base, headers=carer)).status_code == 404


async def test_alerts_belong_to_the_caregiver_and_the_owner_pauses_them(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, carer_id, carer = await _accepted(c, owner_engine)
        first = (await c.get(f"{base}/caregiver-alerts", headers=carer)).json()
        assert first == {
            "missed_dose_after_min": None,
            "critical_result": False,
            "owner_paused": False,
            "chosen": False,
            "watched_medications": 0,
        }
        for bad in (5, 241, 14, -30):
            r = await c.put(
                f"{base}/caregiver-alerts",
                json={"missed_dose_after_min": bad, "critical_result": True},
                headers=carer,
            )
            assert r.status_code == 422
        r = await c.put(
            f"{base}/caregiver-alerts",
            json={"missed_dose_after_min": 45, "critical_result": True},
            headers=carer,
        )
        assert r.json() == {
            "missed_dose_after_min": 45,
            "critical_result": True,
            "owner_paused": False,
            "chosen": True,
            "watched_medications": 0,
        }
        r = await c.put(
            f"{base}/caregiver-alerts",
            json={"missed_dose_after_min": 30, "critical_result": False},
            headers=owner,
        )
        assert (r.status_code, r.json()["code"]) == (403, "caregiver.not_caregiver")
        r = await c.put(f"{base}/caregivers/{carer_id}/pause", json={"paused": True}, headers=owner)
        assert r.status_code == 204
        assert (await c.get(f"{base}/caregiver-alerts", headers=carer)).json()["owner_paused"]
        [person] = (await c.get(f"{base}/caregivers", headers=owner)).json()["caregivers"]
        assert (person["missed_dose_after_min"], person["owner_paused"]) == (45, True)
        r = await c.put(f"{base}/caregivers/{uuid4()}/pause", json={"paused": True}, headers=owner)
        assert r.status_code == 404
        # a caregiver whose access ended is nobody to pause (security review L1)
        assert (await c.delete(f"{base}/caregivers/{carer_id}", headers=owner)).status_code == 204
        r = await c.put(f"{base}/caregivers/{carer_id}/pause", json={"paused": True}, headers=owner)
        assert r.status_code == 404
        owner, base, carer_id, carer = await _accepted(c, owner_engine)
        r = await c.put(
            f"{base}/caregivers/{carer_id}/pause", json={"paused": False}, headers=carer
        )
        assert r.status_code == 403


async def test_the_owner_ends_access_and_a_caregiver_can_leave(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, carer_id, carer = await _accepted(c, owner_engine)
        assert (await c.delete(f"{base}/caregivers/{carer_id}", headers=carer)).status_code == 403
        assert (await c.delete(f"{base}/caregivers/{carer_id}", headers=owner)).status_code == 204
        assert (await c.get(base, headers=carer)).status_code == 404
        assert (await c.delete(f"{base}/caregivers/{carer_id}", headers=owner)).status_code == 404
        assert (await c.get(f"{base}/caregivers", headers=owner)).json()["caregivers"] == []

        owner, base, _, carer = await _accepted(c, owner_engine)
        r = await c.post(f"{base}/leave", headers=owner)  # the owner is not a caregiver
        assert (r.status_code, r.json()["code"]) == (403, "caregiver.not_caregiver")
        assert (await c.post(f"{base}/leave", headers=carer)).status_code == 204
        assert (await c.get(base, headers=carer)).status_code == 404
        assert (await c.get(f"{base}/caregivers", headers=owner)).json()["caregivers"] == []


async def test_withdrawing_the_sharing_consent_ends_every_caregiver(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    """Q42 through the API: the consent the app shows is the one that lets caregivers in."""
    async with client_from() as c:
        owner, base, _, carer = await _accepted(c, owner_engine)
        await _share(c, owner, granted=False)
        assert (await c.get(base, headers=carer)).status_code == 404
        assert (await c.get(f"{base}/caregivers", headers=owner)).json()["caregivers"] == []


async def _dose_alert(owner_engine: AsyncEngine, base: str, carer_id: UUID) -> tuple[int, UUID]:
    """A dose alert and its notice, as the worker leaves them (arranged as the schema owner)."""
    patient = UUID(base.rsplit("/", 1)[1])
    async with owner_engine.connect() as conn, conn.begin():
        med = (
            await conn.execute(
                bound_text(
                    "insert into medications (patient_id, client_id, name, reminders_enabled)"
                    " values (:p, gen_random_uuid(), 'Такролимус', true) returning id"
                ),
                {"p": patient},
            )
        ).scalar_one()
        alert = (
            await conn.execute(
                bound_text(
                    "insert into dose_alerts (patient_id, medication_id, slot_at, alerted_user_id)"
                    " values (:p, :m, date_trunc('minute', now()) - interval '40 minutes', :u)"
                    " returning id"
                ),
                {"p": patient, "m": med, "u": carer_id},
            )
        ).scalar_one()
        await conn.execute(
            bound_text(
                "insert into notifications (user_id, kind, patient_id, entity_id, title_key)"
                " values (:u, 'dose_overdue', :p, :e, 'notification.dose_overdue')"
            ),
            {"u": carer_id, "p": patient, "e": str(alert)},
        )
    return int(alert), med


async def test_a_dose_alert_shows_what_is_recorded_now(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, carer_id, carer = await _accepted(c, owner_engine)
        alert, _ = await _dose_alert(owner_engine, base, carer_id)
        [notice] = [
            n
            for n in (await c.get("/api/v1/me/notifications", headers=carer)).json()
            if n["kind"] == "dose_overdue"
        ]
        assert notice["patient_id"] == base.rsplit("/", 1)[1]
        assert notice["entity_id"] == str(alert)
        r = await c.get(f"{base}/dose-alerts/{alert}", headers=carer)
        assert (r.status_code, r.json()["recorded"], r.json()["medication_name"]) == (
            200,
            None,
            "Такролимус",
        )
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text(
                    "insert into medication_intakes (patient_id, medication_id, client_id,"
                    " scheduled_at, taken_at, status) select patient_id, medication_id,"
                    " gen_random_uuid(), slot_at, now(), 'taken' from dose_alerts where id = :i"
                ),
                {"i": alert},
            )
        assert (await c.get(f"{base}/dose-alerts/{alert}", headers=carer)).json()["recorded"] == (
            "taken"
        )
        # the owner sees it too; a stranger reaches nothing; a wrong profile is 404
        assert (await c.get(f"{base}/dose-alerts/{alert}", headers=owner)).status_code == 200
        _, stranger = await _signed_in(c, owner_engine)
        assert (await c.get(f"{base}/dose-alerts/{alert}", headers=stranger)).status_code == 404
        assert (
            await c.get(f"{base}/dose-alerts/{alert + 10**9}", headers=carer)
        ).status_code == 404

        # access ended: the notice leaves the list, the alert is unreachable
        assert (await c.delete(f"{base}/caregivers/{carer_id}", headers=owner)).status_code == 204
        kinds = [n["kind"] for n in (await c.get("/api/v1/me/notifications", headers=carer)).json()]
        assert "dose_overdue" not in kinds
        assert (await c.get(f"{base}/dose-alerts/{alert}", headers=carer)).status_code == 404


async def test_a_dose_alert_is_only_for_its_caregiver_and_its_profile(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, carer_id, carer = await _accepted(c, owner_engine)
        alert, _ = await _dose_alert(owner_engine, base, carer_id)
        # a second caregiver of the same profile was not alerted: nothing to see
        second_id, second = await _signed_in(c, owner_engine)
        await c.post(
            f"{base}/caregiver-invitations",
            json={"username": await _username(owner_engine, second_id)},
            headers=owner,
        )
        [inv] = (await c.get("/api/v1/me/caregiver-invitations", headers=second)).json()
        await c.post(
            "/api/v1/me/caregiver-invitations/respond",
            json={"invitation_id": inv["id"], "accept": True},
            headers=second,
        )
        assert (await c.get(f"{base}/dose-alerts/{alert}", headers=second)).status_code == 404
        # through a profile the caregiver can open (their own), someone else's alert id: 404
        _, own = await _create(c, carer, full_name="Сараа", relation="self")
        r = await c.get(f"/api/v1/patients/{own['id']}/dose-alerts/{alert}", headers=carer)
        assert r.status_code == 404


async def test_an_invitations_notice_stays_only_while_it_can_be_answered(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, base, _, carer, name = await _family(c, owner_engine)
        await c.post(f"{base}/caregiver-invitations", json={"username": name}, headers=owner)

        async def kinds() -> list[str]:
            return [
                n["kind"] for n in (await c.get("/api/v1/me/notifications", headers=carer)).json()
            ]

        assert "share_invite" in await kinds()
        [pending] = (await c.get(f"{base}/caregivers", headers=owner)).json()["invitations"]
        await c.delete(f"{base}/caregiver-invitations/{pending['id']}", headers=owner)
        assert "share_invite" not in await kinds()
