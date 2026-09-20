"""Quién está haciendo el pedido, tal como lo miran las reglas de negocio.

Se llena desde el usuario autenticado (:mod:`app.api.dependencies`). Es un tipo aparte del
modelo ``User`` para que los servicios dependan de dos datos —rol y nombre— y no de la
tabla entera.
"""

import uuid
from dataclasses import dataclass

ADMIN_ROLE = "ADMIN"


@dataclass(frozen=True)
class RequestUser:
    role: str = "staff"
    name: str | None = None
    id: uuid.UUID | None = None

    @property
    def is_admin(self) -> bool:
        return self.role.strip().upper() == ADMIN_ROLE


#: Usuario por defecto de las llamadas internas: el de menor privilegio.
STAFF = RequestUser()
