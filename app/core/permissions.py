"""Qué puede hacer cada tipo de usuario.

Los permisos son por tarea, no por pantalla: el mismo permiso puede habilitar endpoints de
varios routers, y una pantalla puede necesitar más de uno. Leer está permitido a cualquier
usuario con sesión; los permisos gobiernan lo que modifica datos.
"""

import enum


class Permission(str, enum.Enum):
    ADMISSION = "ADMISSION"  # registrar pacientes, coberturas y admitir
    HOSPITALIZATION = "HOSPITALIZATION"  # internación: prácticas, equipo, altas
    BED_CLEANING = "BED_CLEANING"  # higiene de camas
    NURSING_TASKS = "NURSING_TASKS"  # ejecutar lo que el médico indica: inyectables, tomas, Holter
    BED_MANAGEMENT = "BED_MANAGEMENT"  # asignar, reservar y transferir camas
    BILLING = "BILLING"  # cuenta de la internación
    CATALOG = "CATALOG"  # nomenclador, coberturas, centros, servicios, profesionales
    USER_ADMIN = "USER_ADMIN"  # altas y bajas de usuarios


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    RECEPTIONIST = "RECEPTIONIST"
    DOCTOR = "DOCTOR"
    NURSE = "NURSE"


ROLE_PERMISSIONS: dict[UserRole, frozenset[Permission]] = {
    # El administrador hace todo, incluido modificar una internación con alta médica.
    UserRole.ADMIN: frozenset(Permission),
    # Recepción admite: registra al paciente, su cobertura y la solicitud de internación.
    UserRole.RECEPTIONIST: frozenset({Permission.ADMISSION}),
    # El médico conduce la internación y lo que se le indica al paciente.
    UserRole.DOCTOR: frozenset({Permission.HOSPITALIZATION}),
    # Enfermería ejecuta lo indicado al paciente y deja las camas en condiciones.
    UserRole.NURSE: frozenset({Permission.BED_CLEANING, Permission.NURSING_TASKS}),
}

ROLE_LABELS: dict[UserRole, str] = {
    UserRole.ADMIN: "Administración",
    UserRole.RECEPTIONIST: "Recepción",
    UserRole.DOCTOR: "Profesional médico",
    UserRole.NURSE: "Enfermería",
}


def permissions_of(role: UserRole) -> frozenset[Permission]:
    return ROLE_PERMISSIONS.get(role, frozenset())
