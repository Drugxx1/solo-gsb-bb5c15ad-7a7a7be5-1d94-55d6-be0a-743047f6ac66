"""POST /api/v1/chains/redundancy 的 API 层测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def redundancy_payload():
    return {
        "datum_points": ["A"],
        "measure_points": ["B", "C", "D"],
        "constraints": [
            {"id": "c1", "start": "A", "end": "B", "lower": 10, "upper": 12},
            {"id": "c2", "start": "B", "end": "C", "lower": 5, "upper": 8},
            {"id": "c3", "start": "A", "end": "C", "lower": 14, "upper": 21},
            {"id": "c4", "start": "C", "end": "D", "lower": 0, "upper": 3},
        ],
    }


def test_redundancy_marks_implied_constraint():
    r = client.post("/api/v1/chains/redundancy", json=redundancy_payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "feasible"
    assert body["unit"] == "um"
    # c3 被 c1+c2 蕴含（推导 [15,20] ⊆ [14,21]）；c4 是 D 的唯一连接，两侧无界
    assert body["results"] == [
        {"constraint_id": "c1", "derived_lower": 6, "derived_upper": 16, "redundant": False},
        {"constraint_id": "c2", "derived_lower": 2, "derived_upper": 11, "redundant": False},
        {"constraint_id": "c3", "derived_lower": 15, "derived_upper": 20, "redundant": True},
        {"constraint_id": "c4", "derived_lower": None, "derived_upper": None, "redundant": False},
    ]


def test_redundancy_results_follow_constraint_order():
    payload = redundancy_payload()
    payload["constraints"] = [payload["constraints"][i] for i in (2, 0, 3, 1)]
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 200, r.text
    assert [x["constraint_id"] for x in r.json()["results"]] == ["c3", "c1", "c4", "c2"]


def test_redundancy_single_constraint_unbounded():
    payload = {
        "datum_points": ["A"],
        "measure_points": ["B"],
        "constraints": [
            {"id": "c1", "start": "A", "end": "B", "lower": 0, "upper": 10}
        ],
    }
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["results"] == [
        {"constraint_id": "c1", "derived_lower": None, "derived_upper": None, "redundant": False}
    ]


def test_redundancy_infeasible_uses_same_response():
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


def test_redundancy_static_validation_422():
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


def test_redundancy_reversed_interval_422():
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


def test_redundancy_pydantic_type_errors_422():
    # 公差给小数：沿用严格整数风格走 pydantic 422
    payload = redundancy_payload()
    payload["constraints"][0]["lower"] = 1.5
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 422


def test_redundancy_rejects_extra_field_422():
    payload = redundancy_payload()
    payload["bogus"] = 1
    r = client.post("/api/v1/chains/redundancy", json=payload)
    assert r.status_code == 422


def test_redundancy_openapi_documented():
    schema = client.get("/openapi.json").json()
    assert "/api/v1/chains/redundancy" in schema["paths"]
    assert "RedundancyResponse" in schema["components"]["schemas"]
