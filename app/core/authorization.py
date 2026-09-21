"""Qué permiso pide cada operación que modifica datos.

Una tabla en vez de un decorador por endpoint: así se lee de corrido quién puede hacer qué,
que es justamente la pregunta que uno quiere contestar sin recorrer seis routers.

Leer no figura acá: cualquier usuario con sesión puede consultar. Lo que no figura y
modifica datos queda solo para administración, para que agregar un endpoint y olvidarse de
esta tabla falle cerrado y no abierto.
"""

from app.core.permissions import Permission

#: (método, ruta sin el prefijo de versión) → permiso necesario.
WRITE_PERMISSIONS: dict[tuple[str, str], Permission] = {
    # --------------------------------------------------------------- admisión
    ("POST", "/patients"): Permission.ADMISSION,
    ("PUT", "/patients/{patient_id}"): Permission.ADMISSION,
    ("DELETE", "/patients/{patient_id}"): Permission.ADMISSION,
    ("POST", "/patients/{patient_id}/identifiers"): Permission.ADMISSION,
    ("POST", "/patients/{patient_id}/contacts"): Permission.ADMISSION,
    ("POST", "/patients/{patient_id}/coverages"): Permission.ADMISSION,
    ("PUT", "/coverages/{coverage_id}"): Permission.ADMISSION,
    ("DELETE", "/coverages/{coverage_id}"): Permission.ADMISSION,
    ("POST", "/admissions"): Permission.ADMISSION,
    ("POST", "/admissions/{admission_id}/authorizations"): Permission.ADMISSION,
    ("POST", "/authorizations/{authorization_id}/resolve"): Permission.ADMISSION,
    ("POST", "/admissions/{admission_id}/administrative-discharge"): Permission.ADMISSION,
    # Consulta al financiador: no modifica datos, pero va por POST porque lleva cuerpo.
    ("POST", "/payer-mock/authorizations"): Permission.ADMISSION,
    ("POST", "/hospitalizations"): Permission.ADMISSION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/administrative-discharge",
    ): Permission.ADMISSION,
    # ------------------------------------------------------------ internación
    ("POST", "/hospitalizations/{hospitalization_id}/practices"): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/practices/{order_id}/perform",
    ): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/practices/{order_id}/cancel",
    ): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/service-assignments",
    ): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/care-team/members",
    ): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/care-team/members/{member_id}/end",
    ): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/discharge-plans",
    ): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/clinical-discharge",
    ): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/physical-departure",
    ): Permission.HOSPITALIZATION,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/authorizations",
    ): Permission.HOSPITALIZATION,
    ("POST", "/hospitalizations/{hospitalization_id}/diagnoses"): Permission.HOSPITALIZATION,
    (
        "PUT",
        "/hospitalizations/{hospitalization_id}/diagnoses/{entry_id}",
    ): Permission.HOSPITALIZATION,
    (
        "DELETE",
        "/hospitalizations/{hospitalization_id}/diagnoses/{entry_id}",
    ): Permission.HOSPITALIZATION,
    # ------------------------------------------------------ tareas de enfermería
    ("POST", "/nursing-tasks/{order_id}/perform"): Permission.NURSING_TASKS,
    ("POST", "/nursing-tasks/{order_id}/cancel"): Permission.NURSING_TASKS,
    # Recetas e indicaciones del alta: las escribe quien conduce la internación.
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/discharge-prescriptions",
    ): Permission.HOSPITALIZATION,
    (
        "PUT",
        "/hospitalizations/{hospitalization_id}/discharge-prescriptions/{prescription_id}",
    ): Permission.HOSPITALIZATION,
    (
        "DELETE",
        "/hospitalizations/{hospitalization_id}/discharge-prescriptions/{prescription_id}",
    ): Permission.HOSPITALIZATION,
    # --------------------------------------------------------- limpieza de camas
    ("POST", "/beds/{bed_id}/cleaning/start"): Permission.BED_CLEANING,
    ("POST", "/beds/{bed_id}/cleaning/complete"): Permission.BED_CLEANING,
    ("POST", "/beds/{bed_id}/status"): Permission.BED_CLEANING,
    # ------------------------------------------------------------ gestión de camas
    ("POST", "/hospitalizations/{hospitalization_id}/bed-assignments"): Permission.BED_MANAGEMENT,
    ("POST", "/hospitalizations/{hospitalization_id}/release-bed"): Permission.BED_MANAGEMENT,
    ("POST", "/hospitalizations/{hospitalization_id}/transfers"): Permission.BED_MANAGEMENT,
    ("POST", "/hospitalizations/{hospitalization_id}/bed-reservations"): Permission.BED_MANAGEMENT,
    ("POST", "/bed-reservations/{reservation_id}/cancel"): Permission.BED_MANAGEMENT,
    ("POST", "/bed-reservations/expire-due"): Permission.BED_MANAGEMENT,
    # ------------------------------------------------------------------ cuenta
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/account/charge-items",
    ): Permission.BILLING,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/account/charge-items/{charge_item_id}/void",
    ): Permission.BILLING,
    ("POST", "/hospitalizations/{hospitalization_id}/account/payments"): Permission.BILLING,
    (
        "POST",
        "/hospitalizations/{hospitalization_id}/account/payments/{payment_id}/void",
    ): Permission.BILLING,
    ("POST", "/accounts/{account_id}/close"): Permission.BILLING,
    # ---------------------------------------------------------------- catálogos
    ("POST", "/facilities"): Permission.CATALOG,
    ("POST", "/rooms"): Permission.CATALOG,
    ("PUT", "/rooms/{room_id}"): Permission.CATALOG,
    ("DELETE", "/rooms/{room_id}"): Permission.CATALOG,
    ("POST", "/beds"): Permission.CATALOG,
    ("PUT", "/beds/{bed_id}"): Permission.CATALOG,
    ("POST", "/beds/{bed_id}/room"): Permission.CATALOG,
    ("POST", "/services"): Permission.CATALOG,
    ("PUT", "/services/{service_id}"): Permission.CATALOG,
    ("DELETE", "/services/{service_id}"): Permission.CATALOG,
    ("POST", "/specialties"): Permission.CATALOG,
    ("PUT", "/specialties/{specialty_id}"): Permission.CATALOG,
    ("DELETE", "/specialties/{specialty_id}"): Permission.CATALOG,
    ("POST", "/professionals"): Permission.CATALOG,
    ("PUT", "/professionals/{professional_id}"): Permission.CATALOG,
    ("DELETE", "/professionals/{professional_id}"): Permission.CATALOG,
    ("POST", "/practices"): Permission.CATALOG,
    ("PUT", "/practices/{practice_id}"): Permission.CATALOG,
    ("DELETE", "/practices/{practice_id}"): Permission.CATALOG,
    ("POST", "/practices/{practice_id}/tariffs"): Permission.CATALOG,
    ("PUT", "/practices/{practice_id}/tariffs/{tariff_id}"): Permission.CATALOG,
    ("DELETE", "/practices/{practice_id}/tariffs/{tariff_id}"): Permission.CATALOG,
    ("POST", "/diagnoses"): Permission.CATALOG,
    ("PUT", "/diagnoses/{diagnosis_id}"): Permission.CATALOG,
    ("DELETE", "/diagnoses/{diagnosis_id}"): Permission.CATALOG,
    ("POST", "/payers"): Permission.CATALOG,
    ("PUT", "/payers/{payer_id}"): Permission.CATALOG,
    ("DELETE", "/payers/{payer_id}"): Permission.CATALOG,
    ("POST", "/payers/{payer_id}/health-plans"): Permission.CATALOG,
    ("PUT", "/health-plans/{health_plan_id}"): Permission.CATALOG,
    ("DELETE", "/health-plans/{health_plan_id}"): Permission.CATALOG,
    ("POST", "/health-plans/{health_plan_id}/practices"): Permission.CATALOG,
    ("POST", "/health-plans/{health_plan_id}/practices/bulk"): Permission.CATALOG,
    ("PUT", "/health-plans/{health_plan_id}/practices/{plan_practice_id}"): Permission.CATALOG,
    (
        "DELETE",
        "/health-plans/{health_plan_id}/practices/{plan_practice_id}",
    ): Permission.CATALOG,
}

#: Lo que modifica datos y no está en la tabla queda para administración.
DEFAULT_WRITE_PERMISSION = Permission.USER_ADMIN

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def permission_for(method: str, path: str) -> Permission | None:
    """Permiso que pide una operación, o ``None`` si es de solo lectura."""

    if method.upper() not in WRITE_METHODS:
        return None
    return WRITE_PERMISSIONS.get((method.upper(), path), DEFAULT_WRITE_PERMISSION)
