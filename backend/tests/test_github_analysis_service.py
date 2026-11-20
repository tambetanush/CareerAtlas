"""Unit tests for app.github_analysis.service pure helpers."""
from app.github_analysis import service
from app.github_analysis.service import SkillEvidence


# ── select_files ─────────────────────────────────────────────────────────────

def test_select_files_manifest_first_ordering():
    tree = [
        "src/app.py",
        "README.md",
        "requirements.txt",
        "main.py",
        "utils/helpers.py",
    ]
    selected = service.select_files(tree)
    # manifests, then readme, then entrypoints, then remaining shallow source
    assert selected[0] == "requirements.txt"
    assert selected[1] == "README.md"
    # main.py and src/app.py are both entrypoints -> they precede utils/helpers.py
    assert selected.index("main.py") < selected.index("utils/helpers.py")
    assert selected.index("src/app.py") < selected.index("utils/helpers.py")


def test_select_files_skips_vendor_dirs_tests_and_deep_source():
    tree = [
        "node_modules/pkg/index.js",
        "src/a/b/c/deep.py",   # depth > 3 -> excluded from source bucket
        "tests/test_x.py",     # 'test' in name -> excluded
        "app.py",
    ]
    selected = service.select_files(tree)
    assert "node_modules/pkg/index.js" not in selected
    assert "src/a/b/c/deep.py" not in selected
    assert "tests/test_x.py" not in selected
    assert "app.py" in selected


def test_select_files_respects_cap():
    tree = [f"module{i}.py" for i in range(30)]
    assert len(service.select_files(tree, cap=5)) == 5


# ── _filter_evidence ─────────────────────────────────────────────────────────

def test_filter_evidence_keeps_path_backed_skill():
    skills = [SkillEvidence(skill="FastAPI", evidence="requirements.txt", confidence="high")]
    out = service._filter_evidence(skills, ["requirements.txt"], {})
    assert out[0].confidence == "high"


def test_filter_evidence_keeps_language_backed_skill():
    skills = [SkillEvidence(skill="Python", evidence="python is dominant", confidence="high")]
    out = service._filter_evidence(skills, [], {"Python": 90.0})
    assert out[0].confidence == "high"


def test_filter_evidence_caps_unbacked_skill_to_low():
    skills = [SkillEvidence(skill="Rust", evidence="I feel like they know rust", confidence="high")]
    out = service._filter_evidence(skills, ["package.json"], {"JavaScript": 100.0})
    assert out[0].confidence == "low"
    assert out[0].skill == "Rust"


# ── _commit_context ──────────────────────────────────────────────────────────

def test_commit_context_no_commits():
    assert service._commit_context({"commit_count": 0}) == "no owner-authored commits found"
    assert service._commit_context({}) == "no owner-authored commits found"


def test_commit_context_with_span():
    ctx = service._commit_context({
        "commit_count": 12,
        "first_commit_at": "2023-01-15T00:00:00Z",
        "last_commit_at": "2023-06-20T00:00:00Z",
    })
    assert ctx == "12 owner-authored commits between 2023-01-15 and 2023-06-20"


def test_commit_context_marks_100_plus():
    ctx = service._commit_context({"commit_count": 150})
    assert ctx.startswith("150+ owner-authored commits")


# ── evidence: whole-word language match ─────────────────────────────────────

def test_one_letter_language_does_not_back_unrelated_skill():
    skills = [SkillEvidence(skill="Docker", evidence="containers are used", confidence="high")]
    out = service._filter_evidence(skills, [], {"C": 60.0, "R": 40.0})
    assert out[0].confidence == "low"  # "Docker" contains "c" and "r" but isn't backed by C or R


def test_one_letter_language_still_backs_itself():
    skills = [SkillEvidence(skill="C", evidence="most code is C", confidence="high")]
    assert service._filter_evidence(skills, [], {"C": 60.0})[0].confidence == "high"


# ── repo fan-out: LLM concurrency cap + summary failure ──────────────────────

import asyncio

from app.github_analysis.schemas import GitHubRepoInfo


def _repo(i):
    return GitHubRepoInfo(name=f"me/r{i}", owner="me", url="u", stargazerCount=0, isOwner=True)


def _fake_github(monkeypatch, n_repos):
    async def ok(*a, **k):
        return "me"

    async def tree(*a, **k):
        return ["README.md", "main.py"]

    async def langs(*a, **k):
        return {"Python": 100.0}

    async def stats(*a, **k):
        return {"commit_count": 3}

    async def content(*a, **k):
        return "x" * 5000

    async def top(*a, **k):
        return [_repo(i) for i in range(n_repos)]

    for name, fn in [("fetch_authenticated_login", ok), ("fetch_repo_file_tree", tree), ("fetch_languages", langs),
                     ("fetch_commit_stats", stats), ("fetch_file_content", content), ("fetch_top_repositories", top)]:
        monkeypatch.setattr(service, name, fn)


async def test_repo_llm_calls_capped_and_summary_failure_survives(monkeypatch):
    _fake_github(monkeypatch, 6)
    state = {"now": 0, "peak": 0, "prompt_chars": 0}

    class _RepoChain:
        async def ainvoke(self, payload):
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
            state["prompt_chars"] = max(state["prompt_chars"], len(payload["file_contents"]))
            await asyncio.sleep(0.01)
            state["now"] -= 1
            return service.RepoAnalysisResult(summary="s", coding_behavior="b", inferred_skills=[])

    class _BrokenProfileChain:
        async def ainvoke(self, payload):
            raise RuntimeError("rate limited")

    monkeypatch.setattr(
        service, "build_structured_chain",
        lambda prompt, schema, temperature=0.2: _RepoChain() if schema is service.RepoAnalysisResult else _BrokenProfileChain(),
    )
    out = await service.analyze_selected_repositories("u1", [f"me/r{i}" for i in range(6)], "tok")
    assert state["peak"] <= service.MAX_PARALLEL_REPO_LLM_CALLS
    assert state["prompt_chars"] < 2 * (service.MAX_FILE_CHARS + 100)  # two 5k files truncated to ~2k each
    assert len(out["repo_analyses"]) == 6
    assert out["profile"]["summary"] == "Profile summary unavailable right now."
