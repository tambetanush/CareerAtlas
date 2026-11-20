# Agent review: proposed improvements

This review covers every agent in `backend/app`, as of November 2026. ☑ = built (20 November 2026) with tests in `backend/tests`. ☐ = still open; tick the ones to build next.

**Impact** is how much users or reviewers would notice. **Effort:** S = under an hour, M = a few hours, L = a day.

## Already done (provider-layer change)

These shared problems were fixed when the AI provider switch was built (`backend/app/utils/llm_factory.py`):

- **Retired default model.** The default Gemini model was `gemini-1.5-flash`. It's now `GEMINI_MODEL` in `.env`.
- **Retrying on every error.** The factory retried on any error, including 400, 401 and 404, and slept for up to 15 seconds in total. Retries are now left to each provider's own client, which only retries rate limits (429), server errors (5xx) and connection failures.
- **Blocking sleep.** `time.sleep` inside the sync helper blocked the server's event loop. It's gone.
- **No Groq fallback.** Groq-only chains (deep researcher, GitHub analysis, gap analysis) had no fallback. Every agent now falls back across all providers the server has keys for.
- **No timeouts.** Every model call now has a 60-second timeout.

## Proposed fixes

| ✓ | Agent | Fix | Where | Impact | Effort |
|---|---|---|---|---|---|
| ☑ | Job hunter | **Fix skill-overlap scoring.** `tokenize` splits the job text into single words, so a multi-word skill ("machine learning") never matches. The score is also divided by the size of the resume. Match normalised skill phrases against the job text instead, and score the share of the job's mentioned skills that the candidate has. | `job_hunter/agent.py:238-284` | **High.** "Skill overlap 0%" is visible on every job card. | M |
| ☑ | Job hunter | **Title boost uses stop-words.** Headline words like "a" or "in" match almost any title. Ignore stop-words and short tokens. | `job_hunter/agent.py:~260` | Medium | S |
| ☑ | Job hunter | **Make explanations structured.** Replace `safe_json_parse` with `invoke_llm(..., schema=...)`. Fall back per job using `_fallback_explanations` (today it only runs when every job fails). Stop that fallback inventing generic "gaps" (cloud, communication). | `job_hunter/agent.py:~45, ~392, ~462` | **High.** Fixes "No strengths extracted yet". | M |
| ☐ | Job hunter | **Stop at the first Adzuna query that works.** Up to 5 role variants are tried one after another with a 25s timeout each. Try them in parallel, or cap the total time. | `job_hunter/agent.py:_fetch_jobs_with_fallback` | Medium (latency) | S |
| ☑ | Job hunter | **Seniority filter does nothing.** `seniority` is always `None`, so the Intern/Entry/Junior/Mid/Senior chips filter out everything. Infer seniority from the title, or remove the chips. | `job_hunter/agent.py:_build_job_result`, `_app.jobs.tsx` | Medium (visible) | S |
| ☑ | Resume extraction | **Blocking route.** `async def` routes run synchronous PDF parsing, DB and LLM work on the event loop. While one upload is running, every other user waits. Make them plain `def` routes. The job hunter `POST` route has the same problem. | `resume_extraction/router.py:~323`, `job_hunter/router.py:~192` | **High** under load | S |
| ☐ | Resume extraction | **Batch the database inserts.** About 50–150 single-row inserts per resume; one insert per table is enough. A failure halfway also leaves a partial resume that becomes the "latest" one. | `resume_extraction/router.py:70-139` | Medium (speed, data safety) | M |
| ☐ | Resume extraction | **Spoken languages counted as skills.** "English" and "Hindi" are merged into `skills`, then feed gap analysis and job matching. | `resume_extraction/service.py:501-505`, `router.py:56-59` | Medium | S |
| ☐ | Resume extraction | **`_delete_other_resumes` is never called.** Old resumes pile up. Call it or delete it. | `resume_extraction/router.py:179` | Low | S |
| ☑ | Gap analysis | **Decide in code which skills the user already has.** Today the LLM decides, and retrieval ranks skills the user already has highest. Filter them out before the LLM call, and drop any LLM gap that isn't in the retrieved list. | `gap_analysis/service.py`, `hybrid_retrieval.py:131,154` | **High.** Fewer "gaps" the user already has. | M |
| ☐ | Gap analysis | **Retrieval does nothing for small taxonomies.** Each role has 8–20 skills, but retrieval asks for 30, so every request returns the whole role and the embedding, Pinecone, BM25 and Jina calls only reorder it. Skip retrieval when a role has ≤ 30 rows. | `gap_analysis/service.py:84-92` | Medium (≈3 fewer network calls) | S |
| ☐ | Gap analysis | **Taxonomy generation fixes:** embed rows in parallel (`asyncio.gather`), label generated taxonomies as generated (not "curated"), add a per-role lock, and clear the cache for one role only. | `gap_analysis/taxonomy_gen.py:106-118`, `service.py:79` | Medium | M |
| ☐ | Deep researcher | **Plan every query up front, search in parallel.** Make one query per gap in a single call, run the Tavily searches concurrently, and drop the critic loop. That's fewer LLM calls and better coverage, which also avoids most judge retries. | `deep_researcher/agent.py` | **High** (speed and quality) | L |
| ☐ | Deep researcher | **Compute pass/fail in code from `rubric_scores`.** Today the model decides; use average ≥ 4 with no score below 3. On retry, keep the best-scoring pathway. | `deep_researcher/judge.py:53`, `agent.py:judge_route` | Medium | S |
| ☐ | Deep researcher | **Give the structurer numbered sources.** It currently gets free text; a numbered list of source URLs stops it inventing links. | `deep_researcher/agent.py:~125`, `prompts.py` | Medium | S |
| ☐ | Deep researcher | **Prompt says "Iteration 0".** The counter starts at 1. | `deep_researcher/prompts.py:25` | Low | S |
| ☑ | GitHub analysis | **Fetch files in parallel, cap concurrent LLM calls.** Up to 12 files are fetched one by one. Up to 10 repos are analysed at once with ~15–20k-token prompts, which hits rate limits. Use `gather` for files, a semaphore of 3 for repos, and ~2,000 chars per file. | `github_analysis/service.py:220-250` | **High** (fewer "Analysis failed") | S |
| ☑ | GitHub analysis | **Evidence check is too loose.** One-letter languages ("c", "r") substring-match almost any skill, so nearly everything counts as backed. Require exact matches for short names. | `github_analysis/service.py:202` | Medium | S |
| ☑ | GitHub analysis | **Profile call has no error handling.** If it fails, the whole request returns 500 even though the per-repo results succeeded. | `github_analysis/service.py:287` | Medium | S |
| ☐ | Roadmap | **Bulk upsert mixes rows with and without `id`.** This likely fails with a NOT NULL error on `id` for new milestones, and duplicate skills crash the upsert. Split it into an insert for new rows and an upsert for existing ones, and deduplicate by key. | `roadmap_generation/service.py:73-89` | Medium (needs a live check) | S |
| ☐ | All routers | **Raw exception text in 500 responses.** It can leak internals. Log it, and return a short message. | `gap_analysis/router.py:190`, `deep_researcher/router.py:234`, others | Low (security hygiene) | S |

## Quality evaluation gap

The notebooks in `Notebooks/` have no saved outputs, so there are no recorded scores showing which agent is weakest. Before tuning prompts, a small eval would help: for example 10 real resumes × 3 roles, scored by an LLM judge for gap correctness and job relevance. Then each fix above can be measured instead of guessed.

## Before deploying

Check the live database for the `job_matches.seniority NOT NULL` constraint (`sql/001_schema.sql:114`). The agent writes `seniority = None`, so if production still has that constraint, saving job matches fails.
