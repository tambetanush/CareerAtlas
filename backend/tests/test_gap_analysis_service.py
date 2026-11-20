"""Tests for the code-side gap filtering in app.gap_analysis.service."""
from app.gap_analysis import service
from app.gap_analysis.schemas import GapAnalysisResponse, GapSchema


def _gap(name):
    return GapSchema(skill=name, category="tool", relevance=50, difficulty="Medium", why="needed", prerequisites=[])


def test_norm_treats_js_spellings_as_one_skill():
    assert service._norm("React.js") == service._norm("ReactJS") == service._norm("react")
    assert service._norm("C++") != service._norm("C")


def test_filter_gaps_drops_known_invented_and_duplicate_gaps():
    reqs = ["Docker", "Kubernetes", "ETL and data pipelines basics", "SQL"]
    known = {service._norm(s) for s in ["sql", "Python"]}
    gaps = [_gap("Docker"), _gap("SQL"), _gap("docker"), _gap("Quantum Computing"), _gap("ETL and data pipelines")]
    out = [g.skill for g in service.filter_gaps(gaps, reqs, known)]
    assert out == ["Docker", "ETL and data pipelines"]


async def test_known_skills_never_reach_the_llm(monkeypatch):
    async def fake_taxonomy(_role):
        return "curated"

    async def fake_retrieve(**_kw):
        return [
            {"skill_name": "Python", "relevance_score": 0.4},
            {"skill_name": "Docker", "relevance_score": 0.3},
        ]

    seen = {}

    class _Chain:
        async def ainvoke(self, prompt_value):
            seen["prompt"] = prompt_value.to_string()
            return GapAnalysisResponse(gaps=[_gap("Python"), _gap("Docker")], justifications={})

    monkeypatch.setattr(service, "ensure_role_taxonomy", fake_taxonomy)
    monkeypatch.setattr(service, "hybrid_retrieve", fake_retrieve)
    monkeypatch.setattr("app.utils.llm_factory.get_runnable", lambda **_kw: _Chain())

    gaps, explain = await service.generate_gaps_for_user(["python"], "Backend Engineer")
    requirements = seen["prompt"].split("RETRIEVED ROLE REQUIREMENTS")[1].split("## RULES")[0]
    assert "Python" not in requirements and "Docker" in requirements
    assert [g.skill for g in gaps] == ["Docker"]
    assert explain["already_have"] == ["Python"]
