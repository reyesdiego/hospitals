"""Inicio de sesión, sesiones y permisos por rol."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.api.dependencies import SessionUser, enforce_permissions
from app.core.authorization import DEFAULT_WRITE_PERMISSION, permission_for
from app.core.exceptions import DomainError
from app.core.permissions import Permission, UserRole, permissions_of
from app.core.security import hash_password, hash_token, verify_password
from app.db.seeds.users import INITIAL_USERS, seed_users
from app.models.user import User, UserSession
from app.schemas.auth import UserCreate, UserUpdate
from app.services.auth import AuthService
from tests.conftest import requires_postgres, run_db

PASSWORD = "Hospital.2026"


def test_a_password_is_stored_hashed_and_salted():
    first, second = hash_password("secreta"), hash_password("secreta")

    assert first != second  # sal distinta por contraseña
    assert "secreta" not in first
    assert verify_password("secreta", first)
    assert not verify_password("otra", first)
    assert not verify_password("secreta", "hash-ilegible")


def test_each_role_can_do_what_its_job_needs():
    assert permissions_of(UserRole.RECEPTIONIST) == frozenset({Permission.ADMISSION})
    assert permissions_of(UserRole.DOCTOR) == frozenset({Permission.HOSPITALIZATION})
    assert permissions_of(UserRole.NURSE) == frozenset(
        {Permission.BED_CLEANING, Permission.NURSING_TASKS}
    )
    assert permissions_of(UserRole.ADMIN) == frozenset(Permission)


def test_reading_needs_no_permission_and_an_unlisted_write_is_for_administration():
    assert permission_for("GET", "/patients") is None
    assert permission_for("POST", "/patients") is Permission.ADMISSION
    assert permission_for("POST", "/beds/{bed_id}/cleaning/start") is Permission.BED_CLEANING
    assert (
        permission_for("POST", "/hospitalizations/{hospitalization_id}/practices")
        is Permission.HOSPITALIZATION
    )
    # Un endpoint nuevo que nadie agregó a la tabla queda cerrado, no abierto.
    assert permission_for("POST", "/algo-que-no-existe") is DEFAULT_WRITE_PERMISSION


@requires_postgres
def test_the_initial_users_are_created_once_and_can_log_in():
    async def case(factory):
        async with factory() as session:
            created = await seed_users(session, password=PASSWORD)
        async with factory() as session:
            again = await seed_users(session, password="otra-distinta")
        async with factory() as session:
            user, token, expires_at = await AuthService(session).login(
                "recepcion@hospital.local", PASSWORD
            )
            return created, again, user.role, bool(token), expires_at > datetime.now(UTC)

    created, again, role, has_token, valid = run_db(case)
    assert sorted(created) == sorted(email for email, _, _ in INITIAL_USERS)
    assert again == []  # volver a correrlo no pisa contraseñas
    assert role is UserRole.RECEPTIONIST
    assert has_token and valid


@requires_postgres
def test_a_wrong_password_an_unknown_user_and_a_disabled_one_answer_the_same():
    async def case(factory):
        async with factory() as session:
            await seed_users(session, password=PASSWORD)
        messages = []
        for email, password in (
            ("admin@hospital.local", "equivocada"),
            ("nadie@hospital.local", PASSWORD),
        ):
            async with factory() as session:
                with pytest.raises(DomainError) as excinfo:
                    await AuthService(session).login(email, password)
                messages.append((excinfo.value.status_code, excinfo.value.message))
        async with factory() as session:
            user = await AuthService(session).create_user(
                UserCreate(
                    email="baja@hospital.local",
                    full_name="De baja",
                    role=UserRole.DOCTOR,
                    password=PASSWORD,
                    is_active=False,
                )
            )
            user_id = user.id
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AuthService(session).login("baja@hospital.local", PASSWORD)
            messages.append((excinfo.value.status_code, excinfo.value.message))
        return messages, user_id

    messages, _ = run_db(case)
    assert {message for _, message in messages} == {"Usuario o contraseña incorrectos"}
    assert {code for code, _ in messages} == {401}


@requires_postgres
def test_the_token_is_not_stored_and_logging_out_kills_the_session():
    async def case(factory):
        async with factory() as session:
            await seed_users(session, password=PASSWORD)
        async with factory() as session:
            _, token, _ = await AuthService(session).login("medico@hospital.local", PASSWORD)
        async with factory() as session:
            stored = await session.scalar(
                UserSession.__table__.select().with_only_columns(UserSession.token_hash)
            )
            resolved = await AuthService(session).resolve(token)
            role = resolved.role
        async with factory() as session:
            await AuthService(session).logout(token)
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AuthService(session).resolve(token)
            after = excinfo.value.status_code
        async with factory() as session:
            await AuthService(session).logout(token)  # dos veces no es un error
        return stored, token, role, after

    stored, token, role, after = run_db(case)
    assert stored == hash_token(token)
    assert stored != token
    assert role is UserRole.DOCTOR
    assert after == 401


@requires_postgres
def test_an_expired_session_is_no_session():
    async def case(factory):
        async with factory() as session:
            await seed_users(session, password=PASSWORD)
        async with factory() as session:
            _, token, _ = await AuthService(session).login("enfermeria@hospital.local", PASSWORD)
        async with factory() as session:
            row = await session.scalar(
                UserSession.__table__.select().with_only_columns(UserSession.id)
            )
            expired = await session.get(UserSession, row)
            expired.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            await session.commit()
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AuthService(session).resolve(token)
            return excinfo.value.status_code

    assert run_db(case) == 401


@requires_postgres
def test_changing_the_role_closes_the_sessions_that_were_open():
    async def case(factory):
        async with factory() as session:
            await seed_users(session, password=PASSWORD)
        async with factory() as session:
            user, token, _ = await AuthService(session).login("medico@hospital.local", PASSWORD)
            user_id = user.id
        async with factory() as session:
            await AuthService(session).update_user(
                user_id,
                UserUpdate(
                    email="medico@hospital.local",
                    full_name="Profesional médico",
                    role=UserRole.NURSE,
                ),
            )
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AuthService(session).resolve(token)
            code = excinfo.value.status_code
        async with factory() as session:
            updated = await session.get(User, user_id)
            return code, updated.role

    code, role = run_db(case)
    assert code == 401
    assert role is UserRole.NURSE


@requires_postgres
def test_two_users_cannot_share_the_email():
    async def case(factory):
        async with factory() as session:
            await seed_users(session, password=PASSWORD)
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AuthService(session).create_user(
                    UserCreate(
                        email="ADMIN@hospital.local",
                        full_name="Otro admin",
                        role=UserRole.ADMIN,
                        password=PASSWORD,
                    )
                )
            return excinfo.value.status_code

    assert run_db(case) == 409


@requires_postgres
def test_an_unknown_user_is_404():
    async def case(factory):
        async with factory() as session:
            with pytest.raises(DomainError) as excinfo:
                await AuthService(session).get(uuid.uuid4())
            return excinfo.value.status_code

    assert run_db(case) == 404


class _Route:
    def __init__(self, path: str):
        self.path = path


class _Request:
    """Lo mínimo que mira ``enforce_permissions``: método y ruta ya resuelta."""

    def __init__(self, method: str, path: str):
        self.method = method
        self.scope = {"route": _Route(f"/api/v1{path}")}
        self.url = _Route(f"/api/v1{path}")


def session_user(role: UserRole) -> SessionUser:
    return SessionUser(
        id=uuid.uuid4(),
        email=f"{role.value.lower()}@hospital.local",
        full_name=role.value,
        role=role,
        is_active=True,
        last_login_at=None,
        created_at=datetime.now(UTC),
    )


def allowed(role: UserRole, method: str, path: str) -> bool:
    import asyncio

    try:
        asyncio.run(enforce_permissions(_Request(method, path), session_user(role)))
    except DomainError as denied:
        assert denied.status_code == 403
        return False
    return True


def test_the_gate_lets_each_role_through_only_where_it_should():
    # Recepción admite; la internación y las camas no son lo suyo.
    assert allowed(UserRole.RECEPTIONIST, "POST", "/admissions")
    assert not allowed(
        UserRole.RECEPTIONIST, "POST", "/hospitalizations/{hospitalization_id}/practices"
    )
    assert not allowed(UserRole.RECEPTIONIST, "POST", "/beds/{bed_id}/cleaning/start")

    # El médico conduce la internación, no admite ni limpia.
    assert allowed(UserRole.DOCTOR, "POST", "/hospitalizations/{hospitalization_id}/practices")
    assert allowed(
        UserRole.DOCTOR, "POST", "/hospitalizations/{hospitalization_id}/clinical-discharge"
    )
    assert not allowed(UserRole.DOCTOR, "POST", "/admissions")

    # Enfermería deja las camas listas.
    assert allowed(UserRole.NURSE, "POST", "/beds/{bed_id}/cleaning/complete")
    assert not allowed(UserRole.NURSE, "POST", "/practices")

    # Leer es de todos.
    for role in UserRole:
        assert allowed(role, "GET", "/hospitalizations")


def test_the_administrator_can_do_everything():
    for method, path in (
        ("POST", "/admissions"),
        ("POST", "/hospitalizations/{hospitalization_id}/practices"),
        ("POST", "/beds/{bed_id}/cleaning/start"),
        ("POST", "/payers"),
        ("POST", "/users"),
        ("POST", "/ruta-nueva-sin-tabla"),
    ):
        assert allowed(UserRole.ADMIN, method, path), path
