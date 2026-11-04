"""/patients (Phase 2.0) and the consent gate on every health-data route."""

from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.dependencies.models import Dependant
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from labtrack import consents
from labtrack.api import deps
from labtrack.db.sql import bound_text

from .conftest import ClientFactory, login_body, make_active_user
from .test_admin_auth import _ANONYMOUS, _PATH_SAMPLES

pytestmark = pytest.mark.db

# Account routes: usable before any consent (the consent screen itself lives under /me).
# /me is listed path by path: a health-data route added under /me later is not exempt.
_ACCOUNT_PREFIXES = ("/api/v1/auth/", "/api/v1/admin")
_ACCOUNT_PATHS = {
    "/api/v1/me",
    "/api/v1/me/consents",
    "/api/v1/me/admin-actions",
    "/api/v1/me/notifications",
    "/api/v1/me/notifications/{notification_id}/read",
    "/api/v1/me/report-unwanted-admin-action",
    "/api/v1/me/delete",
}
REQUIRED = [
    {"kind": k, "version": consents.VERSIONS[k], "granted": True} for k in consents.REQUIRED
]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _signed_in(
    c: AsyncClient, owner_engine: AsyncEngine, *, consented: bool = True
) -> tuple[UUID, dict[str, str]]:
    uid, username = await make_active_user(owner_engine)
    r = await c.post("/api/v1/auth/login", json=login_body(username))
    h = _auth(r.json()["access_token"])
    if consented:
        r = await c.post("/api/v1/me/consents", json={"items": REQUIRED}, headers=h)
        assert r.status_code == 204
    return uid, h


async def _create(c: AsyncClient, h: dict[str, str], **body: object) -> tuple[int, dict]:  # type: ignore[type-arg]
    r = await c.post("/api/v1/patients", json=body, headers=h)
    return r.status_code, r.json()


def _child_birth(years: int = 8) -> str:
    return date(datetime.now(UTC).date().year - years, 3, 1).isoformat()


# FastAPI's own schema/docs pages (no data).
_FRAMEWORK_DOCS = {"openapi", "swagger_ui_html", "swagger_ui_redirect", "redoc_html"}


def _is_account(path: str) -> bool:
    return path in _ANONYMOUS or path in _ACCOUNT_PATHS or path.startswith(_ACCOUNT_PREFIXES)


def _calls(dependant: Dependant) -> Iterator[Callable[..., object]]:
    for sub in dependant.dependencies:
        if sub.call is not None:
            yield sub.call
        yield from _calls(sub)


def _served(routes: Iterable[object]) -> Iterator[object]:
    """The routes as served, with full paths. FastAPI 0.13x keeps an included router as one
    `_IncludedRouter` entry whose `effective_route_contexts()` yields the real routes."""
    for route in routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            yield from contexts()
        else:
            yield route


def test_every_route_declares_its_gate() -> None:
    """Every route the app serves (not only those in the OpenAPI schema) outside the account
    routes is gated: the user's consents (phi_db) and, for a route on one profile, access to
    it plus a minor's profile consents (patient_read_db, or patient_write_db when it writes)."""
    from labtrack.main import create_app  # noqa: PLC0415

    app = create_app()
    checked = 0
    for route in _served(app.routes):
        path = getattr(route, "path", "")
        if not path.startswith("/api/") or _is_account(path):
            continue
        if getattr(route, "name", None) in _FRAMEWORK_DOCS:
            continue
        dependant = getattr(route, "dependant", None)
        assert isinstance(dependant, Dependant), path  # no mounts/websockets without a gate
        calls = set(_calls(dependant))
        assert deps.phi_db in calls, path
        methods: set[str] = getattr(route, "methods", set())
        # a health record is reached through its profile, never by its own id alone (the
        # profile gate - access, a minor's consents - must run for every one of them)
        if "{" in path:
            assert path.startswith("/api/v1/patients/{patient_id}"), path
        if "{patient_id}" in path:
            gate = deps.patient_read_db if methods == {"GET"} else deps.patient_write_db
            assert gate in calls, (methods, path)
        checked += 1
    assert checked >= 4


async def test_every_health_route_needs_the_required_consents(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    """Fail closed for routes added later: anything outside /auth, /me and /admin is health
    data and answers 403 consent.required until terms, privacy and sensitive_data are given
    for the current text version."""
    from labtrack.main import create_app  # noqa: PLC0415

    paths = create_app().openapi()["paths"]
    async with client_from() as c:
        _, h = await _signed_in(c, owner_engine, consented=False)
        checked = 0
        for path, operations in paths.items():
            if _is_account(path):
                continue
            for method, operation in operations.items():
                url = path
                for p in operation.get("parameters", []):
                    if p["in"] == "path":
                        sample = _PATH_SAMPLES[p["schema"].get("format", p["schema"]["type"])]
                        url = url.replace(f"{{{p['name']}}}", sample)
                r = await c.request(method.upper(), url, headers=h, json={})
                assert (r.status_code, r.json().get("code")) == (403, "consent.required"), (
                    method,
                    path,
                )
                checked += 1
        assert checked >= 4

        # one required consent withdrawn is enough to close them again
        await c.post("/api/v1/me/consents", json={"items": REQUIRED}, headers=h)
        assert (await c.get("/api/v1/patients", headers=h)).status_code == 200
        withdraw = {"items": [{**REQUIRED[0], "granted": False}]}
        await c.post("/api/v1/me/consents", json=withdraw, headers=h)
        r = await c.get("/api/v1/patients", headers=h)
        assert (r.status_code, r.json()["code"]) == (403, "consent.required")


async def test_own_profile_once_and_children_only_as_minors(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h = await _signed_in(c, owner_engine)
        assert (await c.get("/api/v1/patients", headers=h)).json() == []
        status, me = await _create(c, h, full_name=" Болд ", relation="self")
        assert status == 201
        assert (me["full_name"], me["access_level"], me["is_minor"]) == ("Болд", "owner", False)
        status, body = await _create(c, h, full_name="Болд 2", relation="self")
        assert (status, body["code"]) == (409, "patient.self_exists")

        status, child = await _create(
            c, h, full_name="Тэмүүлэн", relation="child", birth_date=_child_birth(), sex="male"
        )
        assert (status, child["is_minor"]) == (201, True)
        for bad in (
            {"full_name": "Насанд хүрсэн", "relation": "child", "birth_date": _child_birth(19)},
            {"full_name": "Огноогүй", "relation": "child"},
            {
                "full_name": "Ирээдүй",
                "relation": "child",
                "birth_date": (datetime.now(UTC).date() + timedelta(days=3)).isoformat(),
            },
            {"full_name": "Ээж", "relation": "parent"},
            {
                "full_name": "Б" + chr(0x202E) + "Б",
                "relation": "child",
                "birth_date": _child_birth(),
            },
            {"full_name": "Б", "relation": "self", "role": "owner"},
        ):
            assert (await _create(c, h, **bad))[0] == 422, bad

        listed = (await c.get("/api/v1/patients", headers=h)).json()
        assert [p["id"] for p in listed] == [me["id"], child["id"]]  # own profile first


async def test_profile_cap(owner_engine: AsyncEngine, client_from: ClientFactory) -> None:
    async with client_from() as c:
        _, h = await _signed_in(c, owner_engine)
        for i in range(10):
            status, _ = await _create(
                c, h, full_name=f"Хүүхэд {i}", relation="child", birth_date=_child_birth()
            )
            assert status == 201
        status, body = await _create(
            c, h, full_name="Арав дахь", relation="child", birth_date=_child_birth()
        )
        assert (status, body["code"]) == (409, "patient.limit_reached")


async def test_profiles_of_others_are_invisible_and_only_owners_edit(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, h = await _signed_in(c, owner_engine)
        carer, carer_h = await _signed_in(c, owner_engine)
        _, stranger_h = await _signed_in(c, owner_engine)
        _, me = await _create(c, h, full_name="Сараа", relation="self")
        url = f"/api/v1/patients/{me['id']}"

        for verb in ("GET", "PATCH"):
            r = await c.request(verb, url, headers=stranger_h, json={"full_name": "Х"})
            assert (r.status_code, r.json()["code"]) == (404, "patient.not_found")
        assert (await c.get("/api/v1/patients", headers=stranger_h)).json() == []

        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text(
                    "insert into patient_access (patient_id, user_id, level, granted_by)"
                    " values (:p, :c, 'caregiver', :o)"
                ),
                {"p": me["id"], "c": carer, "o": owner},
            )
        seen = (await c.get(url, headers=carer_h)).json()
        assert (seen["full_name"], seen["access_level"]) == ("Сараа", "caregiver")
        r = await c.patch(url, json={"full_name": "Өөр"}, headers=carer_h)
        assert (r.status_code, r.json()["code"]) == (403, "patient.not_owner")

        r = await c.patch(url, json={"full_name": "Сараа Б", "sex": "female"}, headers=h)
        assert (r.json()["full_name"], r.json()["sex"]) == ("Сараа Б", "female")
        # an adult's empty birth date can be filled once, then stays
        assert (await c.patch(url, json={"birth_date": "1985-04-02"}, headers=h)).status_code == 200
        r = await c.patch(url, json={"birth_date": "1986-04-02"}, headers=h)
        assert (r.status_code, r.json()["code"]) == (409, "patient.birth_date_locked")

        async with owner_engine.connect() as conn:
            diffs = (
                await conn.execute(
                    bound_text(
                        "select action, diff::text from audit_logs where patient_id = :p"
                        " order by id"
                    ),
                    {"p": me["id"]},
                )
            ).all()
        assert [a for a, _ in diffs][:2] == ["patient.create", "patient.update"]
        assert all("Сараа" not in (d or "") and "1985" not in (d or "") for _, d in diffs)


async def test_a_minors_profile_needs_its_own_consents(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        parent, h = await _signed_in(c, owner_engine)
        carer, carer_h = await _signed_in(c, owner_engine)
        _, stranger_h = await _signed_in(c, owner_engine)
        _, adult = await _create(c, h, full_name="Аав", relation="self")
        _, child = await _create(c, h, full_name="Хүү", relation="child", birth_date=_child_birth())
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text(
                    "insert into patient_access (patient_id, user_id, level, granted_by)"
                    " values (:p, :c, 'caregiver', :o)"
                ),
                {"p": child["id"], "c": carer, "o": parent},
            )
        child_url = f"/api/v1/patients/{child['id']}"

        async def code(url: str, headers: dict[str, str], verb: str = "GET") -> str | int:
            r = await c.request(verb, url, headers=headers, json={"sex": "male"})
            return r.status_code if r.status_code < 400 else r.json()["code"]

        assert await code(f"/api/v1/patients/{adult['id']}", h) == 200  # own consents suffice
        for verb in ("GET", "PATCH"):
            assert await code(child_url, h, verb) == "consent.profile_required"
            # a stranger learns nothing, not even that the profile is a minor's
            assert await code(child_url, stranger_h, verb) == "patient.not_found"
        body = {"items": REQUIRED, "patient_id": child["id"]}
        assert (await c.post("/api/v1/me/consents", json=body, headers=h)).status_code == 204
        assert await code(child_url, h) == 200
        assert await code(child_url, h, "PATCH") == 200
        # the parent's consent for the child is not the caregiver's to rely on: fail closed
        assert await code(child_url, carer_h) == "consent.profile_required"
        # withdrawn by the parent: the child's profile closes again
        body = {"items": [{**REQUIRED[0], "granted": False}], "patient_id": child["id"]}
        assert (await c.post("/api/v1/me/consents", json=body, headers=h)).status_code == 204
        assert await code(child_url, h) == "consent.profile_required"
        # the list still shows it, so the app can ask for the consents again
        listed = (await c.get("/api/v1/patients", headers=h)).json()
        assert [p["is_minor"] for p in listed] == [False, True]


async def test_ages_must_fit_the_relation(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        _, h = await _signed_in(c, owner_engine)
        status, _ = await _create(c, h, full_name="Би", relation="self", birth_date=_child_birth())
        assert status == 422  # one's own profile is an adult's
        _, me = await _create(c, h, full_name="Би", relation="self")
        url = f"/api/v1/patients/{me['id']}"
        r = await c.patch(url, json={"birth_date": _child_birth()}, headers=h)
        assert (r.status_code, r.json()["code"]) == (422, "validation")
        r = await c.patch(url, json={"relation": "child"}, headers=h)
        assert r.status_code == 422


async def test_viewers_read_but_do_not_write(
    owner_engine: AsyncEngine, client_from: ClientFactory
) -> None:
    async with client_from() as c:
        owner, h = await _signed_in(c, owner_engine)
        viewer, viewer_h = await _signed_in(c, owner_engine)
        _, me = await _create(c, h, full_name="Дулам", relation="self")
        async with owner_engine.connect() as conn, conn.begin():
            await conn.execute(
                bound_text(
                    "insert into patient_access (patient_id, user_id, level, granted_by)"
                    " values (:p, :v, 'viewer', :o)"
                ),
                {"p": me["id"], "v": viewer, "o": owner},
            )
        url = f"/api/v1/patients/{me['id']}"
        assert (await c.get(url, headers=viewer_h)).json()["access_level"] == "viewer"
        r = await c.patch(url, json={"sex": "female"}, headers=viewer_h)
        assert (r.status_code, r.json()["code"]) == (403, "patient.read_only")
