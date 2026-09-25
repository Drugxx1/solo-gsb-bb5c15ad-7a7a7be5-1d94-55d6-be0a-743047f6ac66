"""POST /api/v1/chains/redundancy 的 API 层测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_redundancy_endpoint_feasible():
    payload = {
        "datum_points": ["A"],
        "measure_points": ["B", "C"],
        "constraints": [
            {"id": "c1", "start": "A", "end": "B", "lower": 10, "upper": 12},
            {"id": "c2", "start": "B", "end": "C", "lower": 5, "upper": 8},
            {"id": "c3", "start": "A", "end": "C", "lower": 14, "upper": 22},
        ],
    }
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 200, r.text
    assert r.json() == {
        "status": "feasible",
        "unit": "um",
        "constraints": [
            {"id": "c1", "derived_lower": 6, "derived_upper": 17, "redundant": False},
            {"id": "c2", "derived_lower": 2, "derived_upper": 12, "redundant": False},
            {"id": "c3", "derived_lower": 15, "derived_upper": 20, "redundant": True},
        ],
    }


def test_redundancy_endpoint_follows_request_order():
    # 同一张链，约束顺序打乱：结果顺序必须与请求 constraints 顺序一致
    payload = {
        "datum_points": ["A"],
        "measure_points": ["B", "C"],
        "constraints": [
            {"id": "c3", "start": "A", "end": "C", "lower": 14, "upper": 22},
            {"id": "c1", "start": "A", "end": "B", "lower": 10, "upper": 12},
            {"id": "c2", "start": "B", "end": "C", "lower": 5, "upper": 8},
        ],
    }
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 200, r.text
    assert [i["id"] for i in r.json()["constraints"]] == ["c3", "c1", "c2"]


def test_redundancy_endpoint_null_for_unbounded_sides():
    payload = {
        "datum_points": ["A"],
        "measure_points": ["B", "C"],
        "constraints": [
            {"id": "c1", "start": "A", "end": "B", "lower": 10, "upper": 12},
            {"id": "c2", "start": "B", "end": "C", "lower": 5, "upper": 8},
        ],
    }
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 200, r.text
    for item in r.json()["constraints"]:
        assert item["derived_lower"] is None
        assert item["derived_upper"] is None
        assert item["redundant"] is False


def test_redundancy_endpoint_infeasible_uses_existing_response():
    payload = {
        "datum_points": ["A"],
        "measure_points": ["B", "C"],
        "constraints": [
            {"id": "c1", "start": "A", "end": "B", "lower": 9, "upper": 10},
            {"id": "c2", "start": "B", "end": "C", "lower": 9, "upper": 10},
            {"id": "c3", "start": "C", "end": "A", "lower": -1, "upper": 0},
        ],
    }
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "infeasible"
    assert set(body["conflicting_constraint_ids"]) == {"c1", "c2", "c3"}
    assert body["cycle_weight"] < 0
    assert body["cycle_edges"]


def test_redundancy_endpoint_static_validation_422():
    payload = {
        "datum_points": ["A"],
        "measure_points": ["B", "C"],
        "constraints": [
            {"id": "c1", "start": "A", "end": "B", "lower": 1, "upper": 2}
        ],
    }
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 422
    assert r.json()["detail"][0]["code"] == "point_not_connected_to_datum"


def test_redundancy_endpoint_reversed_interval_422():
    payload = {
        "datum_points": ["A"],
        "measure_points": ["B"],
        "constraints": [
            {"id": "c1", "start": "A", "end": "B", "lower": 9, "upper": 1}
        ],
    }
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 422
    assert r.json()["detail"][0]["code"] == "reversed_interval"


def test_redundancy_endpoint_unknown_field_422():
    payload = {
        "datum_points": ["A"],
        "measure_points": ["B"],
        "constraints": [
            {"id": "c1", "start": "A", "end": "B", "lower": 1, "upper": 2, "bogus": 1}
        ],
    }
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 422


def test_redundancy_endpoint_openapi_documented():
    schema = client.get("/openapi.json").json()
    assert "/api/v1/chains/redundancy" in schema["paths"]
    assert "RedundancyResponse" in schema["components"]["schemas"]
    assert "ConstraintRedundancy" in schema["components"]["schemas"]
