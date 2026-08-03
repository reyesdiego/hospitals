from fastapi.testclient import TestClient

from app.main import app


def test_admission_endpoints_are_exposed_in_openapi():
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/admissions" in paths
    assert "/api/v1/admissions/{admission_id}/administrative-discharge" in paths
    assert "/api/v1/patients/duplicates" in paths
    assert "/api/v1/rooms" in paths
    assert "/api/v1/rooms/{room_id}" in paths
    assert "/api/v1/beds/{bed_id}/room" in paths
