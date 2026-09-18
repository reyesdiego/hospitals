"""The practice catalog is exposed as a CRUD, with its tariffs as a nested resource."""

from fastapi.testclient import TestClient

from app.main import app

PRACTICE_PATHS = {
    "/api/v1/practices": {"get", "post"},
    "/api/v1/practices/{practice_id}": {"get", "put", "delete"},
    "/api/v1/practices/{practice_id}/tariffs": {"get", "post"},
    "/api/v1/practices/{practice_id}/tariffs/effective": {"get"},
    "/api/v1/practices/{practice_id}/tariffs/{tariff_id}": {"put", "delete"},
    "/api/v1/hospitalizations/{hospitalization_id}/practices": {"get", "post"},
    "/api/v1/hospitalizations/{hospitalization_id}/practices/{order_id}/perform": {"post"},
    "/api/v1/hospitalizations/{hospitalization_id}/practices/{order_id}/cancel": {"post"},
}


def openapi_paths() -> dict:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    return response.json()["paths"]


def test_practice_crud_and_tariffs_are_exposed_in_openapi():
    paths = openapi_paths()

    for path, methods in PRACTICE_PATHS.items():
        assert path in paths, path
        assert methods <= set(paths[path]), path


def test_the_catalog_can_be_filtered_by_nomenclador_and_text():
    paths = openapi_paths()
    parameters = {
        parameter["name"] for parameter in paths["/api/v1/practices"]["get"]["parameters"]
    }

    assert {"nomenclador", "chapter", "practice_type", "setting", "search", "only_active"} <= (
        parameters
    )


def test_a_practice_carries_the_units_of_the_nomenclador():
    with TestClient(app) as client:
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
    properties = set(schemas["MedicalPracticeRead"]["properties"])

    assert {
        "nomenclador",
        "code",
        "chapter",
        "practice_type",
        "setting",
        "galeno_units",
        "expense_units",
        "anesthesia_units",
        "biochemical_units",
        "radiology_units",
        "requires_authorization",
        "requires_consent",
    } <= properties


def test_a_practice_of_a_hospitalization_carries_its_prescriber_and_its_charge():
    with TestClient(app) as client:
        schemas = client.get("/openapi.json").json()["components"]["schemas"]

    assert {"practice_id", "prescribed_by_id"} <= set(
        schemas["HospitalizationPracticeCreate"]["required"]
    )
    read = set(schemas["HospitalizationPracticeRead"]["properties"])
    assert {"prescribed_by_id", "performed_by_id", "status", "charge_item_id", "charge"} <= read
    assert {"practice_id", "practice_code"} <= set(schemas["ChargeItemRead"]["properties"])
