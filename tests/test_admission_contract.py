from fastapi.testclient import TestClient

from app.main import app

WORKFLOW_PATHS = (
    "/api/v1/admissions",
    "/api/v1/admissions/{admission_id}",
    "/api/v1/admissions/{admission_id}/administrative-discharge",
    "/api/v1/admissions/{admission_id}/authorizations",
    "/api/v1/authorizations/{authorization_id}/resolve",
    "/api/v1/patients/{patient_id}",
    "/api/v1/patients/duplicates",
    "/api/v1/patients/search",
    "/api/v1/patients/{patient_id}/identifiers",
    "/api/v1/patients/{patient_id}/contacts",
    "/api/v1/patients/{patient_id}/coverages",
    "/api/v1/payers",
    "/api/v1/payers/{payer_id}/health-plans",
    "/api/v1/rooms",
    "/api/v1/rooms/{room_id}",
    "/api/v1/beds/available",
    "/api/v1/beds/{bed_id}/room",
    "/api/v1/beds/{bed_id}/status-history",
    "/api/v1/beds/{bed_id}/cleaning/start",
    "/api/v1/beds/{bed_id}/cleaning/complete",
    "/api/v1/bed-reservations/{reservation_id}/cancel",
    "/api/v1/hospitalizations/{hospitalization_id}",
    "/api/v1/hospitalizations/{hospitalization_id}/service-assignments",
    "/api/v1/hospitalizations/{hospitalization_id}/care-team",
    "/api/v1/hospitalizations/{hospitalization_id}/care-team/members",
    "/api/v1/hospitalizations/{hospitalization_id}/bed-reservations",
    "/api/v1/hospitalizations/{hospitalization_id}/bed-assignments",
    "/api/v1/hospitalizations/{hospitalization_id}/transfers",
    "/api/v1/hospitalizations/{hospitalization_id}/discharge-plans",
    "/api/v1/hospitalizations/{hospitalization_id}/clinical-discharge",
    "/api/v1/hospitalizations/{hospitalization_id}/physical-departure",
    "/api/v1/hospitalizations/{hospitalization_id}/administrative-discharge",
    "/api/v1/hospitalizations/{hospitalization_id}/events",
    "/api/v1/hospitalizations/{hospitalization_id}/account",
    "/api/v1/hospitalizations/{hospitalization_id}/account/charge-items",
    "/api/v1/hospitalizations/{hospitalization_id}/account/charge-items/{charge_item_id}/void",
    "/api/v1/accounts/{account_id}/close",
)


def openapi_paths() -> dict:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    return response.json()["paths"]


def test_hospitalization_workflow_endpoints_are_exposed_in_openapi():
    paths = openapi_paths()

    missing = [path for path in WORKFLOW_PATHS if path not in paths]
    assert missing == []
    assert "put" in paths["/api/v1/patients/{patient_id}"]
    assert "delete" in paths["/api/v1/patients/{patient_id}"]
    assert "get" in paths["/api/v1/hospitalizations/{hospitalization_id}/bed-assignments"]


def test_hospitalization_creation_requires_an_admission_request():
    paths = openapi_paths()
    schema = paths["/api/v1/hospitalizations"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]

    assert schema["$ref"].endswith("HospitalizationCreate")


def test_release_bed_stays_available_but_deprecated():
    paths = openapi_paths()
    release = paths["/api/v1/hospitalizations/{hospitalization_id}/release-bed"]["post"]

    assert release["deprecated"] is True
