from fastapi.testclient import TestClient
import sys
sys.path.insert(0, ".")
from main import app

client = TestClient(app)

def test_audit_log_returns_list():
    response = client.get("/audit-log")
    assert response.status_code == 200
    data = response.json()
    assert "actions" in data
    assert isinstance(data["actions"], list)

def test_audit_log_accepts_limit_param():
    response = client.get("/audit-log?limit=5")
    assert response.status_code == 200

def test_audit_log_accepts_action_type_filter():
    response = client.get("/audit-log?action_type=rename_campaign")
    assert response.status_code == 200
    data = response.json()
    assert "actions" in data
