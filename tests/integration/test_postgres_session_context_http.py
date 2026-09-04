from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from aeroeyes_monitoring_api.domain.identity import uuid7
from aeroeyes_monitoring_api.main import create_app


@pytest.fixture(autouse=True)
def clean_database() -> Iterator[None]:
    """Override create_all cleanup: this module runs on an Alembic-built schema."""
    yield


def test_context_journey_persists_across_independent_app_instances(
    test_database_url: str,
) -> None:
    with TestClient(create_app(database_url=test_database_url)) as first_client:
        session_response = first_client.post("/sessions")
        assert session_response.status_code == 201
        session_id = session_response.json()["session_id"]

        created_response = first_client.put(
            f"/sessions/{session_id}/context",
            json={
                "flight_number": " la8084 ",
                "departure_icao": " sbgr ",
                "destination_icao": " sbrj ",
            },
        )
        assert created_response.status_code == 200
        canonical_context = {
            "session_id": session_id,
            "flight_number": "LA8084",
            "departure_icao": "SBGR",
            "destination_icao": "SBRJ",
        }
        assert created_response.json() == canonical_context

        retrieved_response = first_client.get(
            f"/sessions/{session_id}/context"
        )
        assert retrieved_response.status_code == 200
        assert retrieved_response.json() == canonical_context

    with TestClient(create_app(database_url=test_database_url)) as second_client:
        persisted_response = second_client.get(
            f"/sessions/{session_id}/context"
        )
        assert persisted_response.status_code == 200
        assert persisted_response.json() == canonical_context

        replacement_response = second_client.put(
            f"/sessions/{session_id}/context",
            json={"departure_icao": "SBSP"},
        )
        replacement = {
            "session_id": session_id,
            "flight_number": None,
            "departure_icao": "SBSP",
            "destination_icao": None,
        }
        assert replacement_response.status_code == 200
        assert replacement_response.json() == replacement

        replaced_get_response = second_client.get(
            f"/sessions/{session_id}/context"
        )
        assert replaced_get_response.status_code == 200
        assert replaced_get_response.json() == replacement

        completion_response = second_client.post(
            f"/sessions/{session_id}/complete"
        )
        assert completion_response.status_code == 200
        assert completion_response.json()["status"] == "COMPLETED"

        completed_replacement_response = second_client.put(
            f"/sessions/{session_id}/context",
            json={"destination_icao": "SBRJ"},
        )
        assert completed_replacement_response.status_code == 200
        assert completed_replacement_response.json() == {
            "session_id": session_id,
            "flight_number": None,
            "departure_icao": None,
            "destination_icao": "SBRJ",
        }

        delete_response = second_client.delete(
            f"/sessions/{session_id}/context"
        )
        assert delete_response.status_code == 204
        assert delete_response.content == b""

        missing_context_response = second_client.get(
            f"/sessions/{session_id}/context"
        )
        assert missing_context_response.status_code == 404
        assert missing_context_response.json() == {
            "detail": {
                "code": "SESSION_CONTEXT_NOT_FOUND",
                "message": "Session context not found",
            }
        }

        repeated_delete_response = second_client.delete(
            f"/sessions/{session_id}/context"
        )
        assert repeated_delete_response.status_code == 204
        assert repeated_delete_response.content == b""

        parent_response = second_client.get(f"/sessions/{session_id}")
        assert parent_response.status_code == 200
        assert parent_response.json()["session_id"] == session_id
        assert parent_response.json()["status"] == "COMPLETED"


def test_context_routes_reject_missing_parent(test_database_url: str) -> None:
    missing_session_id = uuid7()

    with TestClient(create_app(database_url=test_database_url)) as client:
        put_response = client.put(
            f"/sessions/{missing_session_id}/context",
            json={"flight_number": "LA8084"},
        )
        get_response = client.get(
            f"/sessions/{missing_session_id}/context"
        )

    expected_error = {
        "detail": {
            "code": "SESSION_NOT_FOUND",
            "message": "Session not found",
        }
    }
    assert put_response.status_code == 404
    assert put_response.json() == expected_error
    assert get_response.status_code == 404
    assert get_response.json() == expected_error


def test_real_composition_exposes_openapi_rubric_and_docs(
    test_database_url: str,
) -> None:
    app = create_app(database_url=test_database_url)

    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()
        docs_response = client.get("/docs")

    required_operations = {
        ("/sessions", "post"),
        ("/sessions/{session_id}", "get"),
        ("/sessions/{session_id}/events", "post"),
        ("/sessions/{session_id}/context", "get"),
        ("/sessions/{session_id}/context", "put"),
        ("/sessions/{session_id}/context", "delete"),
    }
    assert all(
        method in schema["paths"][path]
        for path, method in required_operations
    )
    assert {method for _, method in required_operations} == {
        "get",
        "post",
        "put",
        "delete",
    }
    assert docs_response.status_code == 200
