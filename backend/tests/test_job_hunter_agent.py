"""Unit tests for app.job_hunter.agent (pure scoring / parsing logic)."""
import numpy as np
import pytest

from app.job_hunter import agent
from app.job_hunter.schemas import JobResult


# ── text / json helpers ──────────────────────────────────────────────────

def test_tokenize_lowercases_and_keeps_symbols():
    assert agent.tokenize("Python, C++ and C#.NET") == {"python", "c++", "c#.net", "and"}
    assert agent.tokenize(None) == set()


# ── location filtering ─────────────────────────────────────────────────────

def test_location_filter_empty_job_location_passes():
    assert agent.location_filter("", "pune") is True


def test_location_filter_remote():
    assert agent.location_filter("Remote - India", "remote") is True
    assert agent.location_filter("Pune, India", "remote") is False


def test_location_filter_hybrid_matches_remote_too():
    assert agent.location_filter("Hybrid role", "hybrid") is True
    assert agent.location_filter("Fully Remote", "hybrid") is True
    assert agent.location_filter("On-site Pune", "hybrid") is False


def test_location_filter_city_aliases():
    assert agent.location_filter("Bengaluru, KA", "bangalore") is True
    assert agent.location_filter("Bombay office", "mumbai") is True
    assert agent.location_filter("Chennai", "mumbai") is False


def test_location_filter_unknown_city_uses_literal_match():
    assert agent.location_filter("Kolkata, WB", "kolkata") is True
    assert agent.location_filter("Delhi", "kolkata") is False


# ── no invented listings; real Adzuna fields ───────────────────────────────

def test_no_adzuna_results_returns_empty_not_fake_jobs(monkeypatch):
    monkeypatch.setattr(agent, "fetch_jobs", lambda *a, **k: [])
    assert agent._fetch_jobs_with_fallback("Backend Engineer", "Pune") == []
    res = agent.job_finder_agent({"skills": ["Python"]}, "Backend Engineer", "Pune")
    assert res.jobs == [] and res.total_jobs_fetched == 0


def test_format_salary():
    assert agent._format_salary(600000, 1200000) == "₹6.0L – ₹12.0L"
    assert agent._format_salary(800000, 800000) == "₹8.0L"
    assert agent._format_salary(None, None) is None
    assert agent._format_salary(0, None) is None


def test_days_since():
    from datetime import datetime, timedelta, timezone
    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert agent._days_since(three_days_ago) == 3
    assert agent._days_since(None) is None
    assert agent._days_since("not a date") is None


# ── vector math ─────────────────────────────────────────────────────────────

def test_cosine_sim_identical_vectors():
    v = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert agent.cosine_sim(v, v) == pytest.approx(1.0, abs=1e-4)


def test_cosine_sim_orthogonal_vectors():
    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert agent.cosine_sim(a, b) == pytest.approx(0.0, abs=1e-6)


# ── resume representation ───────────────────────────────────────────────────

def test_build_resume_representation_aggregates_skills():
    resume = {
        "skills": ["Python", "SQL"],
        "programming_languages": ["Go"],
        "spoken_languages": ["English"],
        "keywords": ["ETL"],
        "experience": [{"technologies": ["Airflow"], "description_bullets": ["Built pipelines"]}],
        "projects": [{"technologies": ["Docker"], "description": "A project"}],
        "summary": "Data engineer",
    }
    structured, semantic = agent.build_resume_representation(resume)
    # spoken languages are not job skills
    assert structured["skills"] == {"python", "sql", "go", "etl", "airflow", "docker"}
    assert structured["has_experience"] is True
    assert structured["has_education"] is False
    assert "data engineer" in semantic.lower()
    assert "airflow" in semantic.lower()


def test_build_resume_representation_handles_empty_resume():
    structured, semantic = agent.build_resume_representation({})
    assert structured["skills"] == set()
    assert structured["has_experience"] is False
    assert structured["has_education"] is False
    assert semantic == ""


# ── scoring (no external embeddings -> deterministic fallback path) ─────────

def test_score_jobs_uses_semantic_fallback_when_embeddings_unavailable(monkeypatch):
    # Force the embedding call to fail so score_jobs takes the deterministic path.
    monkeypatch.setattr(agent, "embed_batch", lambda texts: (_ for _ in ()).throw(RuntimeError("no key")))
    resume = {"skills": ["Python", "SQL"], "experience": [{"title": "Eng"}], "education": [{"degree": "BS"}]}
    jobs = [
        {"title": "Python Developer", "description": "We love python and sql"},
        {"title": "Marketing Lead", "description": "brand campaigns"},
    ]
    scored = agent.score_jobs(resume, jobs)
    assert len(scored) == 2
    py = scored[0]["_scores"]
    mk = scored[1]["_scores"]
    # Python job overlaps both skills -> skill_overlap 1.0; marketing job -> 0.0
    assert py["skill_overlap"] == pytest.approx(1.0)
    assert mk["skill_overlap"] == pytest.approx(0.0)
    assert py["final"] > mk["final"]
    assert scored[0]["_matched_tokens"] == ["python", "sql"]
    # experience + education present -> full sub-scores
    assert py["experience"] == 1.0
    assert py["education"] == 1.0


def test_score_jobs_experience_education_defaults():
    # No experience / education -> reduced sub-scores, embeddings absent (no jina key).
    resume = {"skills": ["python"]}
    jobs = [{"title": "Dev", "description": "python role"}]
    scored = agent.score_jobs(resume, jobs)
    s = scored[0]["_scores"]
    assert s["experience"] == 0.4
    assert s["education"] == 0.5


def test_skill_overlap_matches_multi_word_skills_and_not_substrings(monkeypatch):
    monkeypatch.setattr(agent, "embed_batch", lambda texts: (_ for _ in ()).throw(RuntimeError("no key")))
    resume = {"skills": ["Machine Learning", "Java", "C++", "SQL", "Docker", "Kubernetes", "Go", "Rust"]}
    jobs = [{"title": "ML Engineer", "description": "Machine learning with C++ and JavaScript, plus SQL."}]
    scored = agent.score_jobs(resume, jobs)
    assert scored[0]["_matched_tokens"] == ["c++", "machine learning", "sql"]  # "java" must not match "javascript"
    # 8 resume skills but only 3 named in a short snippet -> 3/5, not 3/8
    assert scored[0]["_scores"]["skill_overlap"] == pytest.approx(0.6)


def test_title_boost_ignores_stopwords(monkeypatch):
    monkeypatch.setattr(agent, "embed_batch", lambda texts: (_ for _ in ()).throw(RuntimeError("no key")))
    resume = {"skills": ["python"], "headline": "Student in a data program"}
    unrelated = agent.score_jobs(resume, [{"title": "Head of Sales in a Bank", "description": ""}])[0]["_scores"]
    related = agent.score_jobs(resume, [{"title": "Data Engineer", "description": ""}])[0]["_scores"]
    assert related["final"] > unrelated["final"]


def test_infer_seniority():
    assert agent.infer_seniority("Machine Learning Intern") == "Intern"
    assert agent.infer_seniority("Sr. Backend Engineer") == "Senior"
    assert agent.infer_seniority("Data Analyst / Senior Data Analyst") == "Senior"
    assert agent.infer_seniority("Junior Developer") == "Junior"
    assert agent.infer_seniority("Associate Software Engineer") == "Entry"
    assert agent.infer_seniority("Software Engineer II") == "Mid"
    assert agent.infer_seniority("Backend Engineer") is None
    assert agent.infer_seniority("Internal Tools Engineer") is None


# ── compact resume + prompt building ────────────────────────────────────────

def test_build_compact_resume_for_llm():
    resume = {
        "skills": ["Python"],
        "experience": [{"title": "Eng", "company": "Acme", "start_date": "2020", "end_date": "2022", "technologies": ["Go", ""]}],
        "education": [{"degree": "BS", "institution": "MIT"}],
        "projects": [{"name": "Atlas", "technologies": ["Docker"]}],
    }
    compact = agent.build_compact_resume_for_llm(resume)
    assert compact["experience_titles"] == ["Eng at Acme (2020–2022)"]
    assert compact["experience_technologies"] == ["Go"]  # blank filtered out
    assert compact["education"] == ["BS from MIT"]
    assert compact["projects"] == ["Atlas"]
    assert compact["project_technologies"] == ["Docker"]


def test_build_bulk_explanation_prompt_contains_ids():
    resume = {"skills": ["Python"]}
    jobs = [{"job_id": "abc", "title": "Dev", "company": "Acme", "description": "x" * 1000, "_scores": {"final": 0.5}}]
    prompt = agent.build_bulk_explanation_prompt(resume, jobs)
    assert "abc" in prompt
    assert "exact job_id" in prompt
    # description is truncated to 800 chars in the compact job payload
    assert "x" * 801 not in prompt


# ── explanations ─────────────────────────────────────────────────────────────

def test_explain_jobs_keys_by_string_id(monkeypatch):
    result = agent._JobExplanations(jobs=[agent._JobExplanation(job_id="42", strengths=["python"], gaps=[], reasoning="ok")])
    monkeypatch.setattr(agent, "invoke_llm", lambda *a, **k: result)
    assert agent.explain_jobs("p")["42"]["strengths"] == ["python"]


def test_fallback_explanations_never_invents_gaps():
    resume = {"skills": ["Python", "Testing"]}
    jobs = [
        {"job_id": "1", "title": "Python Engineer", "description": "python testing role"},
        {"job_id": "2", "title": "Engineer", "description": "great team"},
    ]
    out = agent._fallback_explanations(resume, jobs)
    assert out["1"]["strengths"] == ["python", "testing"]
    assert out["1"]["gaps"] == [] and out["2"]["gaps"] == []
    assert "python" in out["1"]["reasoning"]
    assert out["2"]["strengths"] == []


# ── result builder ───────────────────────────────────────────────────────────

def test_build_job_result_maps_scores_and_explanation():
    job = {
        "job_id": "j1", "title": "Dev", "company": "Acme", "location": "Remote",
        "apply_url": "https://apply", "description": "desc", "_matched_tokens": ["python"],
    }
    scores = {"semantic": 0.812345, "skill_overlap": 0.5, "experience": 1.0, "education": 0.5, "final": 0.6789}
    explanation = {"strengths": ["python"], "gaps": ["cloud"], "reasoning": "good fit"}
    result = agent._build_job_result(job, scores, explanation)
    assert isinstance(result, JobResult)
    assert result.job_id == "j1"
    assert result.score.final == pytest.approx(67.89)
    assert result.match_pct == 68
    assert result.remote is True
    assert result.matched == ["python"]
    assert result.missing == ["cloud"]
    assert result.explanation.reasoning == "good fit"


# ── end-to-end agent (hermetic: no adzuna/jina/gemini keys) ─────────────────

def _offline(monkeypatch, jobs):
    monkeypatch.setattr(agent, "fetch_jobs", lambda *a, **k: jobs)
    monkeypatch.setattr(agent, "embed_batch", lambda texts: (_ for _ in ()).throw(RuntimeError("no jina")))


def test_job_finder_agent_falls_back_per_job(monkeypatch):
    jobs = [
        {"job_id": str(i), "title": f"Senior Backend Engineer {i}", "location": "Pune", "description": "python apis", "apply_url": f"https://a/{i}"}
        for i in range(3)
    ]
    _offline(monkeypatch, jobs)
    # LLM explains only job "0"; the other two must get the per-job fallback, not "No explanation".
    partial = agent._JobExplanations(jobs=[agent._JobExplanation(job_id="0", strengths=["APIs"], gaps=["Go"], reasoning="Strong fit")])
    monkeypatch.setattr(agent, "invoke_llm", lambda *a, **k: partial)
    resp = agent.job_finder_agent({"skills": ["python"], "experience": [{"title": "eng"}]}, "Backend Engineer", "Pune", top_k=3)
    by_id = {j.job_id: j for j in resp.jobs}
    assert by_id["0"].explanation.reasoning == "Strong fit"
    assert by_id["1"].explanation.strengths == ["python"]
    assert all(j.seniority == "Senior" for j in resp.jobs)
    assert all(j.score.skill_overlap == 1.0 for j in resp.jobs)


def test_job_finder_agent_survives_llm_failure(monkeypatch):
    _offline(monkeypatch, [{"job_id": "a", "title": "Dev", "location": "Pune", "description": "python", "apply_url": "https://a"}])
    monkeypatch.setattr(agent, "invoke_llm", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no llm")))
    resp = agent.job_finder_agent({"skills": ["python"]}, "Backend Engineer", "Pune", top_k=3)
    assert resp.query_role == "Backend Engineer" and len(resp.jobs) == 1
    assert resp.jobs[0].explanation.reasoning
    assert all(j.explanation.reasoning for j in resp.jobs)
