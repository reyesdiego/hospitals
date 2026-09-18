"""Payers, plans and patient coverages are exposed as a CRUD."""

from fastapi.testclient import TestClient

from app.main import app

COVERAGE_PATHS = {
    "/api/v1/payers": {"get", "post"},
    "/api/v1/payers/{payer_id}": {"get", "put", "delete"},
    "/api/v1/payers/{payer_id}/health-plans": {"get", "post"},
    "/api/v1/health-plans": {"get"},
    "/api/v1/health-plans/{health_plan_id}": {"get", "put", "delete"},
    "/api/v1/patients/{patient_id}/coverages": {"get", "post"},
    "/api/v1/coverages/{coverage_id}": {"get", "put", "delete"},
    "/api/v1/health-plans/{health_plan_id}/practices": {"get", "post"},
    "/api/v1/health-plans/{health_plan_id}/practices/bulk": {"post"},
    "/api/v1/health-plans/{health_plan_id}/practices/{plan_practice_id}": {"put", "delete"},
}


def openapi() -> dict:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    return response.json()


def test_coverage_crud_is_exposed_in_openapi():
    paths = openapi()["paths"]

    for path, methods in COVERAGE_PATHS.items():
        assert path in paths, path
        assert methods <= set(paths[path]), path


def test_payers_and_plans_can_be_filtered():
    paths = openapi()["paths"]
    payer_params = {p["name"] for p in paths["/api/v1/payers"]["get"]["parameters"]}
    plan_params = {p["name"] for p in paths["/api/v1/health-plans"]["get"]["parameters"]}

    assert "search" in payer_params
    assert "payer_id" in plan_params


def test_updating_a_coverage_does_not_take_the_patient_or_the_plan_payer():
    schemas = openapi()["components"]["schemas"]

    assert "patient_id" not in schemas["PatientCoverageUpdate"]["properties"]
    assert "payer_id" not in schemas["HealthPlanUpdate"]["properties"]
    assert {"payer_id", "health_plan_id", "member_number", "status"} <= set(
        schemas["PatientCoverageUpdate"]["properties"]
    )


def test_the_cartilla_carries_the_conditions_of_the_plan():
    schemas = openapi()["components"]["schemas"]

    assert {
        "is_covered",
        "waiting_period_days",
        "copayment_amount",
        "requires_authorization",
        # Lo que exige el nomenclador viaja aparte de lo que exige el plan.
        "practice_requires_authorization",
        "practice_code",
        "practice_name",
    } <= set(schemas["HealthPlanPracticeRead"]["properties"])


def test_the_cartilla_can_be_filtered_by_chapter_text_and_coverage():
    paths = openapi()["paths"]
    parameters = {
        parameter["name"]
        for parameter in paths["/api/v1/health-plans/{health_plan_id}/practices"]["get"][
            "parameters"
        ]
    }

    assert {"chapter", "search", "only_covered"} <= parameters
