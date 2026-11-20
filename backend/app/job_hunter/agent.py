import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import numpy as np
import requests

from app.config import settings
from app.job_hunter.schemas import (
    JobExplanation,
    JobResult,
    JobSearchResponse,
    ScoreBreakdown,
)
from pydantic import BaseModel, Field

from app.utils.llm_factory import invoke_llm

logger = logging.getLogger(__name__)

INDIA_CITY_ALIASES = {
    "pune": {"pune", "poona"},
    "mumbai": {"mumbai", "bombay"},
    "bangalore": {"bangalore", "bengaluru"},
    "hyderabad": {"hyderabad", "hyd"},
    "delhi": {"delhi", "new delhi", "ncr", "gurugram", "noida", "gurgaon"},
    "chennai": {"chennai", "madras"},
}

STOPWORDS = {"a", "an", "and", "the", "of", "in", "at", "for", "to", "with", "on", "or", "i", "am", "my"}

# Spoken languages ("English", "Hindi") say nothing about fit for a tech job.
SKILL_FIELDS = ("skills", "programming_languages", "keywords")


def skill_in_text(skill: str, text: str) -> bool:
    """Whole-phrase match: "machine learning" and "c++" match, but "java" doesn't match "javascript"
    and "c" doesn't match "c++" or "c#"."""
    return re.search(r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9+#])", text) is not None


def resume_skill_set(resume: dict[str, Any]) -> set[str]:
    sources: list[Any] = []
    for field in SKILL_FIELDS:
        sources.extend(resume.get(field) or [])
    for item in (resume.get("experience") or []) + (resume.get("projects") or []):
        if isinstance(item, dict):
            sources.extend(item.get("technologies") or [])
    return {s.strip().lower() for s in sources if isinstance(s, str) and s.strip()}


def infer_seniority(title: str) -> str | None:
    """Map a job title to the jobs page filter chips; None when the title doesn't say."""
    t = (title or "").lower()
    for label, pattern in (
        ("Intern", r"\bintern(ship)?\b"),
        ("Senior", r"\b(senior|sr\.?|lead|principal|staff|head|manager)\b"),
        ("Junior", r"\b(junior|jr\.?)\b"),
        ("Entry", r"\b(entry|fresher|graduate|trainee|associate)\b"),
        ("Mid", r"\b(mid|mid-level|intermediate|ii|iii)\b"),
    ):
        if re.search(pattern, t):
            return label
    return None


def tokenize(text: str):
    return set(re.findall(r"[a-zA-Z0-9\+\#\.]+", (text or "").lower()))


def location_filter(job_loc: str, user_pref: str) -> bool:
    if not job_loc:
        return True
    job_loc_l = job_loc.lower()
    pref = (user_pref or "").lower().strip()
    if pref == "remote":
        return "remote" in job_loc_l
    if pref == "hybrid":
        return "hybrid" in job_loc_l or "remote" in job_loc_l
    aliases = INDIA_CITY_ALIASES.get(pref, {pref})
    return any(alias in job_loc_l for alias in aliases)


def fetch_jobs(query_role: str, where: str, results: int = 20) -> list[dict[str, Any]]:
    if not settings.adzuna_app_id or not settings.adzuna_app_key:
        return []
    url = "https://api.adzuna.com/v1/api/jobs/in/search/1"
    params = {
        "app_id": settings.adzuna_app_id,
        "app_key": settings.adzuna_app_key,
        "what": query_role,
        "where": where if where not in {"remote", "hybrid"} else "",
        "results_per_page": results,
        "content-type": "application/json",
    }
    r = requests.get(url, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()
    jobs = []
    for j in data.get("results", []):
        jobs.append(
            {
                "job_id": str(j.get("id")) if j.get("id") is not None else None,
                "title": j.get("title"),
                "company": (j.get("company") or {}).get("display_name"),
                "location": (j.get("location") or {}).get("display_name"),
                "description": j.get("description") or "",
                "apply_url": j.get("redirect_url"),
                "salary_min": j.get("salary_min"),
                "salary_max": j.get("salary_max"),
                "created": j.get("created"),
            }
        )
    return jobs


def _format_salary(lo: Any, hi: Any) -> str | None:
    """Adzuna India salaries are yearly INR; show a compact range, or None if absent."""
    vals = [float(v) for v in (lo, hi) if isinstance(v, (int, float)) and v > 0]
    if not vals:
        return None
    fmt = lambda v: f"₹{v / 100000:.1f}L"  # noqa: E731  (lakh is how Indian salaries are read)
    lo_v, hi_v = min(vals), max(vals)
    return fmt(lo_v) if lo_v == hi_v else f"{fmt(lo_v)} – {fmt(hi_v)}"


def _days_since(created: Any) -> int | None:
    if not created:
        return None
    try:
        dt = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, (datetime.now(timezone.utc) - dt).days)


def _fetch_jobs_with_fallback(query_role: str, user_location_pref: str, results: int = 20) -> list[dict[str, Any]]:
    search_variants = [
        query_role,
        f"{query_role} jobs",
        f"entry level {query_role}",
        f"senior {query_role}",
        f"{query_role} engineer",
    ]
    # Adzuna's `where` is a LOCATION, not the role. Passing the job title here
    # made every search return nothing and silently fall back to Google links.
    where = user_location_pref if user_location_pref.lower().strip() not in {"remote", "hybrid"} else ""

    for variant in search_variants:
        try:
            jobs = fetch_jobs(variant, where, results=results)
        except Exception:
            logger.warning("Adzuna fetch failed for variant %r", variant, exc_info=True)
            jobs = []
        if not jobs:
            continue

        strict = [j for j in jobs if location_filter(j.get("location") or "", user_location_pref)]
        if strict:
            return strict
        # If the strict location filter wipes everything out, prefer actual jobs over emptiness.
        return jobs

    # No invented listings: an empty result is shown to the user as "no live postings".
    return []


def embed_batch(texts: list[str]) -> np.ndarray:
    if not settings.jina_api_key:
        raise RuntimeError("JINA_API_KEY is required for job ranking embeddings.")
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.jina_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "jina-embeddings-v2-base-en",
        "input": texts,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()["data"]
    return np.array([d["embedding"] for d in data], dtype=np.float32)


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def build_resume_representation(resume: dict[str, Any]):
    skills = resume_skill_set(resume)
    exp_text = " ".join(
        " ".join((e.get("description_bullets", []) or []) + (e.get("technologies", []) or []))
        for e in (resume.get("experience") or [])
        if isinstance(e, dict)
    )
    proj_text = " ".join(
        " ".join(
            [
                p.get("description") or "",
                " ".join(p.get("technologies") or []),
            ]
        )
        for p in (resume.get("projects") or [])
        if isinstance(p, dict)
    )
    summary = resume.get("summary") or ""
    structured = {
        "skills": skills,
        "has_experience": len(resume.get("experience") or []) > 0,
        "has_education": len(resume.get("education") or []) > 0,
    }
    semantic_text = " ".join([summary, exp_text, proj_text]).strip()
    return structured, semantic_text


def score_jobs(resume: dict[str, Any], jobs: list[dict[str, Any]]):
    structured, resume_text = build_resume_representation(resume)
    job_texts = [f"{j.get('title') or ''} {j.get('description') or ''}".strip() for j in jobs]
    resume_skills = structured["skills"]
    headline_tokens = {t for t in tokenize(resume.get("headline", "")) if t not in STOPWORDS and len(t) > 2}
    try:
        embeds = embed_batch([resume_text] + job_texts)
        r_emb = embeds[0]
        j_embs = embeds[1:]
    except Exception:
        logger.warning("Jina embedding failed; falling back to heuristic scoring", exc_info=True)
        r_emb = None
        j_embs = None
    results = []
    for i, job in enumerate(jobs):
        j_text = job_texts[i].lower()
        overlap_tokens = {sk for sk in resume_skills if skill_in_text(sk, j_text)}
        # shortcut: Adzuna gives ~500-char description snippets that name only a few skills, so
        # 5 matched skills counts as full overlap; use the job's own skill list if full descriptions are fetched.
        skill_score = min(1.0, len(overlap_tokens) / min(5, max(len(resume_skills), 1)))
        title_boost = 0.1 if headline_tokens & tokenize(job.get("title") or "") else 0.0
        exp_score = 1.0 if structured["has_experience"] else 0.4
        edu_score = 1.0 if structured["has_education"] else 0.5
        if r_emb is not None and j_embs is not None:
            semantic = cosine_sim(r_emb, j_embs[i])
        else:
            semantic = min(1.0, 0.35 + 0.65 * skill_score + title_boost)
        final = min(
            1.0,
            (0.55 * semantic + 0.25 * skill_score + 0.10 * exp_score + 0.05 * edu_score + 0.05 * title_boost),
        )
        results.append(
            {
                **job,
                "_matched_tokens": sorted(overlap_tokens)[:15],
                "_scores": {
                    "semantic": semantic,
                    "skill_overlap": skill_score,
                    "experience": exp_score,
                    "education": edu_score,
                    "final": final,
                },
            }
        )
    return results


def build_compact_resume_for_llm(resume: dict[str, Any]) -> dict[str, Any]:
    return {
        "skills": resume.get("skills", []),
        "programming_languages": resume.get("programming_languages", []),
        "keywords": resume.get("keywords", []),
        "experience_titles": [
            f"{e.get('title')} at {e.get('company')} ({e.get('start_date')}–{e.get('end_date')})"
            for e in resume.get("experience", [])
            if isinstance(e, dict)
        ],
        "experience_technologies": [
            tech
            for e in resume.get("experience", [])
            if isinstance(e, dict)
            for tech in (e.get("technologies") or [])
            if isinstance(tech, str) and tech.strip()
        ],
        "education": [
            f"{e.get('degree')} from {e.get('institution')}"
            for e in resume.get("education", [])
            if isinstance(e, dict)
        ],
        "projects": [p.get("name") for p in resume.get("projects", []) if isinstance(p, dict)],
        "project_technologies": [
            tech
            for p in resume.get("projects", [])
            if isinstance(p, dict)
            for tech in (p.get("technologies") or [])
            if isinstance(tech, str) and tech.strip()
        ],
    }


def build_bulk_explanation_prompt(resume: dict[str, Any], jobs: list[dict[str, Any]]) -> str:
    compact_resume = build_compact_resume_for_llm(resume)
    compact_jobs = [
        {
            "job_id": j.get("job_id"),
            "title": j.get("title"),
            "company": j.get("company"),
            "description": (j.get("description") or "")[:800],
            "scores": j.get("_scores", {}),
        }
        for j in jobs
    ]
    return f"""
You are evaluating job fit for a candidate.
Explain each job's fit using only facts from the candidate profile and the job text.
Use the exact job_id given for each job.

Candidate profile:
{json.dumps(compact_resume)}

Jobs to evaluate:
{json.dumps(compact_jobs)}

""".strip()


class _JobExplanation(BaseModel):
    job_id: str
    strengths: list[str] = Field(description="Specific skills or experience from the candidate that match this job")
    gaps: list[str] = Field(description="Specific requirements in this job the candidate's profile does not show")
    reasoning: str = Field(description="1-2 sentence overall fit summary")


class _JobExplanations(BaseModel):
    jobs: list[_JobExplanation]


def explain_jobs(prompt: str) -> dict[str, dict[str, Any]]:
    result: _JobExplanations = invoke_llm(prompt, temperature=0.1, schema=_JobExplanations)
    return {str(e.job_id): e.model_dump() for e in result.jobs}


def _fallback_explanations(resume: dict[str, Any], jobs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Used per job when the LLM gives no explanation. States only what the text shows; never invents gaps."""
    skills = resume_skill_set(resume)
    output: dict[str, dict[str, Any]] = {}
    for job in jobs:
        job_text = f"{job.get('title') or ''} {job.get('description') or ''}".lower()
        matched = sorted(sk for sk in skills if skill_in_text(sk, job_text))[:5]
        output[str(job.get("job_id") or job.get("id") or "")] = {
            "strengths": matched,
            "gaps": [],
            "reasoning": (
                f"The posting mentions {', '.join(matched)} from your profile."
                if matched
                else "The posting snippet doesn't name specific skills; open it to compare the full requirements."
            ),
        }
    return output


def _build_job_result(job: dict[str, Any], scores: dict[str, float], explanation: dict[str, Any]) -> JobResult:
    final_pct = round(float(scores["final"]) * 100, 2)
    matched = job.get("_matched_tokens", [])
    gaps = explanation.get("gaps", [])
    reasoning = explanation.get("reasoning", "") or job.get("description") or ""
    return JobResult(
        job_id=str(job.get("job_id") or job.get("id") or ""),
        title=job.get("title") or "Untitled role",
        company=job.get("company"),
        location=job.get("location"),
        apply_url=job.get("apply_url"),
        score=ScoreBreakdown(
            semantic=round(float(scores["semantic"]), 4),
            skill_overlap=round(float(scores["skill_overlap"]), 4),
            experience=round(float(scores["experience"]), 4),
            education=round(float(scores["education"]), 4),
            final=final_pct,
        ),
        explanation=JobExplanation(
            strengths=explanation.get("strengths", []) or [],
            gaps=gaps or [],
            reasoning=reasoning,
        ),
        remote="remote" in (job.get("location") or "").lower(),
        seniority=infer_seniority(job.get("title") or ""),
        match_pct=int(round(final_pct)),
        matched=matched or [],
        missing=gaps or [],
        salary=_format_salary(job.get("salary_min"), job.get("salary_max")),
        posted_days=_days_since(job.get("created")),
        description=job.get("description") or reasoning,
        external_url=job.get("apply_url"),
    )


def job_finder_agent(
    resume: dict[str, Any],
    target_role: str,
    user_location_pref: str,
    top_k: int = 5,
) -> JobSearchResponse:
    jobs = _fetch_jobs_with_fallback(target_role, user_location_pref, results=25)
    if not jobs:
        return JobSearchResponse(
            query_role=target_role,
            user_location_preference=user_location_pref,
            total_jobs_fetched=0,
            jobs=[],
        )
    scored = score_jobs(resume, jobs)
    scored = sorted(scored, key=lambda x: x["_scores"]["final"], reverse=True)[: max(top_k, 7)]
    shown = scored[:top_k]
    try:
        explanations = explain_jobs(build_bulk_explanation_prompt(resume, shown))
    except Exception:
        logger.warning("LLM job explanations failed; using heuristic fallback", exc_info=True)
        explanations = {}
    fallback = _fallback_explanations(resume, shown)

    out_jobs: list[JobResult] = []
    for j in shown:
        key = str(j.get("job_id") or j.get("id") or "")
        e = explanations.get(key)
        if not e or not (e.get("strengths") or e.get("reasoning")):
            e = fallback[key]
        out_jobs.append(_build_job_result(j, j["_scores"], e))

    return JobSearchResponse(
        query_role=target_role,
        user_location_preference=user_location_pref,
        total_jobs_fetched=len(jobs),
        jobs=out_jobs,
    )
