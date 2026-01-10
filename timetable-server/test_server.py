import json
from fastapi.testclient import TestClient
from .server import app

client = TestClient(app)

def test_solve_timetable_endpoint():
    # Load sample data
    with open("../timetable_input.sample.json") as f:
        sample_input = json.load(f)

    response = client.post("/solve/S1", json=sample_input)

    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "objective_value" in data
    assert "payload" in data
    
    payload = data["payload"]
    assert "timetables" in payload
    assert "teacher_allocations" in payload
    
    timetables = payload["timetables"]
    assert isinstance(timetables, list)
    if len(timetables) > 0:
        timetable = timetables[0]
        assert "class_name" in timetable
        assert "timetable" in timetable
        assert isinstance(timetable["timetable"], dict)

    teacher_allocations = payload["teacher_allocations"]
    assert "teacher_allocations" in teacher_allocations
    assert isinstance(teacher_allocations["teacher_allocations"], list)
    if len(teacher_allocations["teacher_allocations"]) > 0:
        teacher_allocation = teacher_allocations["teacher_allocations"][0]
        assert "teacher" in teacher_allocation
        assert "total_periods" in teacher_allocation
        assert "allocations" in teacher_allocation
        assert isinstance(teacher_allocation["allocations"], list)

