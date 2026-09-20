"""Usuarios iniciales, uno por rol.

Se corre una vez sobre una base nueva para poder entrar al sistema. No pisa usuarios ya
creados, así que volver a correrlo no cambia contraseñas.

    python -m app.db.seeds.users                       # con la contraseña por defecto
    python -m app.db.seeds.users --password 'Otra.Clave.2026'
"""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import ROLE_LABELS, UserRole, permissions_of
from app.db.session import SessionFactory, engine
from app.services.auth import ensure_user

#: Contraseña de arranque. Es pública: hay que cambiarla apenas se entra.
DEFAULT_PASSWORD = "Hospital.2026"

INITIAL_USERS = [
    ("admin@hospital.local", "Administración del sistema", UserRole.ADMIN),
    ("recepcion@hospital.local", "Recepción", UserRole.RECEPTIONIST),
    ("medico@hospital.local", "Profesional médico", UserRole.DOCTOR),
    ("enfermeria@hospital.local", "Enfermería", UserRole.NURSE),
]


async def seed_users(session: AsyncSession, *, password: str = DEFAULT_PASSWORD) -> list[str]:
    """Devuelve los correos de los usuarios que se crearon en esta corrida."""

    created: list[str] = []
    async with session.begin():
        for email, full_name, role in INITIAL_USERS:
            _, is_new = await ensure_user(
                session, email=email, full_name=full_name, role=role, password=password
            )
            if is_new:
                created.append(email)
    return created


async def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Crea los usuarios iniciales del sistema")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Contraseña inicial")
    args = parser.parse_args(argv)

    async with SessionFactory() as session:
        created = await seed_users(session, password=args.password)
    await engine.dispose()

    if not created:
        print("Los usuarios iniciales ya estaban creados: no se modificó ninguna contraseña.")
    else:
        print(f"Usuarios creados con la contraseña '{args.password}' (cambiela al entrar):")
        for email, _, role in INITIAL_USERS:
            if email in created:
                permissions = ", ".join(sorted(p.value for p in permissions_of(role)))
                print(f"  {email:<28} {ROLE_LABELS[role]:<20} {permissions}")


if __name__ == "__main__":
    asyncio.run(main())
