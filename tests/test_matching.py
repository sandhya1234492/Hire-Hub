from app.services.matching_service import MatchingService


def test_matching_returns_skill_details_and_percentage():
    result = MatchingService().calculate(
        {"skills": ["Python", "SQL", "MongoDB"], "experience_years": 3,
         "location": "Bengaluru", "expected_salary": 90000},
        {"skills": ["Python", "SQL", "MongoDB", "AWS"], "experience_min": 2,
         "experience_max": 5, "location": "Bengaluru", "salary_max": 120000,
         "work_mode": "HYBRID"},
    )
    assert result["matched_skills"] == ["MongoDB", "Python", "SQL"]
    assert result["missing_skills"] == ["AWS"]
    assert 0 <= result["score"] <= 100
