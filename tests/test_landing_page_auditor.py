import sys
sys.path.insert(0, ".")
from engine.landing_page_auditor import compute_friction_score, audit_landing_page_code

def test_friction_score_good():
    score = compute_friction_score(ctr_pct=2.0, conversion_rate_pct=3.0)
    assert score["status"] == "good"
    assert score["score"] >= 80

def test_friction_score_warning():
    score = compute_friction_score(ctr_pct=2.0, conversion_rate_pct=0.8)
    assert score["status"] == "warning"

def test_friction_score_critical():
    score = compute_friction_score(ctr_pct=2.0, conversion_rate_pct=0.3)
    assert score["status"] == "critical"

def test_audit_landing_page_code_returns_dict():
    result = audit_landing_page_code()
    assert isinstance(result, dict)
    assert "issues" in result
    assert "score" in result
