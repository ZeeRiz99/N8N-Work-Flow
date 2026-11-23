"""Evaluation harness (master prompt §8.9). Measures the production pipeline on the dataset.

    cd backend
    .venv\\Scripts\\python ..\\evals\\run_eval.py --provider fake
    .venv\\Scripts\\python ..\\evals\\run_eval.py --provider gemini

Writes evals/reports/YYYY-MM-DD-<provider>.md (and .json). Report only these numbers, with the
dataset size stated. Live answers are cached in evals/cache/ by input hash, so a run stopped by
a rate limit resumes where it left off and never pays twice for the same inquiry. A report is
marked PARTIAL until every case has a result.
"""

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))

from app.ai.pipeline import LeadFacts, assess, prepare  # noqa: E402
from app.ai.prompts import analysis_v1 as prompt  # noqa: E402
from app.ai.provider import AIInvalidOutput, AIUnavailable  # noqa: E402
from app.ai.schemas import AnalysisOutput  # noqa: E402
from app.services.org import DEMO_SERVICES  # noqa: E402

ORG_NAME, ORG_CURRENCY = "Harbor Web Studio", "USD"
CATALOG = [
    {"name": n, "keywords": k, "price_min_minor": lo, "price_max_minor": hi}
    for n, k, lo, hi in DEMO_SERVICES
]
BANDS = ["low", "medium", "high"]


def load_cases(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def make_provider(name: str):
    if name == "fake":
        from app.ai.fake_provider import FakeAIProvider

        return FakeAIProvider()
    from app.ai.gemini_provider import GeminiProvider
    from app.core.config import get_settings

    s = get_settings()
    model, fallback = s.gemini_models
    # One attempt per model: a quota error should stop the run, not burn retries.
    return GeminiProvider(
        s.gemini_api_key,
        model,
        fallback,
        s.ai_timeout_seconds,
        max_attempts=2,
        daily_budget=s.gemini_daily_budget,
    )


def budget_ok(expect: dict, grounded: dict) -> bool:
    b = grounded.get("budget")
    want = expect.get("budget_max")
    if want is None:
        return b is None or b.get("source") == "form"
    if not b or b.get("max_minor") is None:
        return False
    got = b["max_minor"] / 100
    same_cur = (b.get("currency") or "").upper() == (expect.get("currency") or "").upper()
    return same_cur and abs(got - want) <= 0.01 * want


def score_case(case: dict, out: AnalysisOutput | None) -> dict:
    lead = case["lead"]
    prep = prepare(case["message"], case["form"], CATALOG, ORG_NAME)
    facts = LeadFacts(lead["full_name"], lead["email"] or None, lead["phone"], lead["company"])
    done = assess(out, prep, case["form"], CATALOG, ORG_CURRENCY, facts)
    g = done.grounded.as_dict()
    e = case["expect"]
    got_services = {s["name"] for s in g["services"] if s["name"] != "other"}
    want_services = set(e["services"])
    intents = {e["intent"], *e.get("intent_also_ok", [])}
    intent = out.assessment.intent if out else None
    band = done.result.band
    rejected = len(g["rejected"])
    return {
        "id": case["id"],
        "category": case["category"],
        "service": got_services == want_services,
        "service_recall": len(got_services & want_services) / len(want_services)
        if want_services
        else float(not got_services),
        "budget": budget_ok(e, g),
        "timeline": g["timeline"]["urgency"] == e["urgency"],
        "intent": intent in intents,
        "band": band == e["band"],
        "band_within_one": abs(BANDS.index(band) - BANDS.index(e["band"])) <= 1,
        "got": {
            "services": sorted(got_services),
            "budget": g["budget"],
            "urgency": g["timeline"]["urgency"],
            "intent": intent,
            "band": band,
            "score": done.result.total,
        },
        "want": e,
        "accepted": done.grounded.accepted,
        "rejected": rejected,
        "needs_review": done.needs_review,
    }


def stratified(cases: list[dict], n: int) -> list[dict]:
    """n cases taken round-robin across categories (dataset order inside each), so a small
    sample still covers every kind of inquiry."""
    groups: dict[str, list[dict]] = {}
    for c in cases:
        groups.setdefault(c["category"], []).append(c)
    picked, i = [], 0
    while len(picked) < min(n, len(cases)):
        for g in groups.values():
            if i < len(g) and len(picked) < n:
                picked.append(g[i])
        i += 1
    return picked


def run(provider_name: str, dataset: Path, limit: int | None, sample: int | None = None) -> int:
    cases = load_cases(dataset)[:limit]
    full_size = len(cases)
    if sample:
        cases = stratified(cases, sample)
    cache_file = ROOT / "cache" / f"{provider_name}-{prompt.PROMPT_VERSION}.jsonl"
    cache_file.parent.mkdir(exist_ok=True)
    cache = {}
    if cache_file.exists() and provider_name != "fake":
        for line in cache_file.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            cache[row["input_hash"]] = row
    provider = make_provider(provider_name)
    results, runs, failures, stopped = [], [], [], None
    for case in cases:
        prep = prepare(case["message"], case["form"], CATALOG, ORG_NAME)
        row = cache.get(prep.input_hash)
        if row is None and stopped is None:
            try:
                r = provider.analyze(prompt.SYSTEM, prep.user_prompt)
                row = {
                    "input_hash": prep.input_hash,
                    "id": case["id"],
                    "model": r.model,
                    "latency_ms": r.latency_ms,
                    "input_tokens": r.input_tokens,
                    "output_tokens": r.output_tokens,
                    "output": r.output.model_dump(mode="json"),
                }
                if provider_name != "fake":
                    with cache_file.open("a", encoding="utf-8", newline="\n") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    time.sleep(4)  # stay under free-tier requests per minute
            except AIInvalidOutput as exc:
                failures.append({"id": case["id"], "error": str(exc)})
            except AIUnavailable as exc:
                stopped = f"{case['id']}: {exc}"
        if row is None:
            continue
        runs.append(row)
        results.append(score_case(case, AnalysisOutput.model_validate(row["output"])))
        print(
            f"{case['id']:>4} {results[-1]['got']['band']:<6} "
            f"{'ok' if results[-1]['band'] else 'MISS'}",
            flush=True,
        )
    write_report(provider_name, len(cases), results, runs, failures, stopped, full_size)
    return 0 if len(results) == len(cases) else 3


def pct(xs: list[bool | float]) -> str:
    return f"{100 * sum(xs) / len(xs):.0f}%" if xs else "n/a"


def write_report(provider, total, results, runs, failures, stopped, full_size=None) -> None:
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    (ROOT / "reports").mkdir(exist_ok=True)
    suffix = f"-sample{total}" if full_size and full_size != total else ""
    out = ROOT / "reports" / f"{today}-{provider}{suffix}"
    complete = len(results) == total
    lat = [r["latency_ms"] for r in runs if r.get("latency_ms") is not None]
    tok_in = [r["input_tokens"] for r in runs if r.get("input_tokens")]
    tok_out = [r["output_tokens"] for r in runs if r.get("output_tokens")]
    acc, rej = sum(r["accepted"] for r in results), sum(r["rejected"] for r in results)
    models = sorted({r["model"] for r in runs})
    inj = [r for r in results if r["category"] == "injection"]
    lines = [
        f"# Evaluation report: {provider} ({today})",
        "",
        f"**Status:** {'complete' if complete else 'PARTIAL'}: {len(results)} of {total} "
        f"cases scored{f'; stopped at {stopped}' if stopped else ''}.",
        "",
        f"- Dataset: `evals/datasets/inquiries.jsonl`, {total} fictional inquiries"
        + (
            f" (stratified sample of {full_size}, every category included)"
            if full_size and full_size != total
            else ""
        )
        + "; expected values written by hand before any model run.",
        f"- Provider: {provider}; model(s): {', '.join(models) or 'n/a'}; prompt "
        f"`{prompt.PROMPT_VERSION}`; schema `{prompt.SCHEMA_VERSION}`.",
        "- Pipeline: the production code (`app/ai/pipeline.py`): guard, prompt, provider, "
        "grounding, deterministic scoring with default weights.",
        "",
        "## Results",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Service (exact set) | {pct([r['service'] for r in results])} |",
        f"| Service (recall) | {pct([r['service_recall'] for r in results])} |",
        f"| Budget (amount and currency) | {pct([r['budget'] for r in results])} |",
        f"| Timeline urgency | {pct([r['timeline'] for r in results])} |",
        f"| Intent | {pct([r['intent'] for r in results])} |",
        f"| Priority band agreement | {pct([r['band'] for r in results])} |",
        f"| Band within one step | {pct([r['band_within_one'] for r in results])} |",
        f"| Grounding rejection rate (claims without a real quote) | "
        f"{f'{100 * rej / (acc + rej):.1f}%' if acc + rej else 'n/a'} ({rej} of {acc + rej}) |",
        f"| Injection cases flagged for review | {sum(r['needs_review'] for r in inj)} of "
        f"{len(inj)} |",
        f"| Schema-invalid outputs | {len(failures)} |",
        f"| Mean latency | {f'{statistics.mean(lat) / 1000:.2f} s' if lat else 'n/a'} |",
        f"| p95 latency | "
        f"{f'{sorted(lat)[int(0.95 * (len(lat) - 1))] / 1000:.2f} s' if lat else 'n/a'} |",
        f"| Mean tokens in / out | "
        f"{f'{statistics.mean(tok_in):.0f} / {statistics.mean(tok_out):.0f}' if tok_in else 'n/a'}"
        " |",
        "",
        "## Band agreement by category",
        "",
        "| Category | Cases | Band agreement |",
        "|---|---|---|",
    ]
    cats: dict[str, list[dict]] = {}
    for r in results:
        cats.setdefault(r["category"], []).append(r)
    for cat, rs in cats.items():
        lines.append(f"| {cat} | {len(rs)} | {pct([r['band'] for r in rs])} |")
    misses = [r for r in results if not (r["band"] and r["service"] and r["budget"])]
    lines += ["", "## Misses (band, service or budget)", ""]
    if not misses:
        lines.append("None.")
    for r in misses:
        g, w = r["got"], r["want"]
        b = g["budget"]
        got_budget = f"{b['max_minor'] / 100:g} {b['currency']}" if b else "none"
        lines.append(
            f"- `{r['id']}` ({r['category']}): band {g['band']} ({g['score']}) vs {w['band']}; "
            f"services {g['services']} vs {w['services']}; budget {got_budget} vs "
            f"{w['budget_max']} {w['currency'] or ''}; intent {g['intent']} vs {w['intent']}"
        )
    if failures:
        lines += ["", "## Schema-invalid outputs", ""]
        lines += [f"- `{f['id']}`: {f['error']}" for f in failures]
    lines += [
        "",
        "## Limits of this evaluation",
        "",
        f"- {total} cases is a small sample; one case moves a percentage by "
        f"{100 / total:.1f} points.",
        "- Expected bands are one person's sales judgment, not ground truth.",
        "- The fake provider is keyword rules; its numbers test the pipeline, not AI quality.",
    ]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    out.with_suffix(".json").write_text(
        json.dumps(
            {"provider": provider, "complete": complete, "results": results},
            indent=1,
            ensure_ascii=False,
        ),
        encoding="utf-8",
        newline="\n",
    )
    print(f"report: {out.with_suffix('.md')}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["fake", "gemini"], default="fake")
    ap.add_argument("--dataset", type=Path, default=ROOT / "datasets" / "inquiries.jsonl")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--sample", type=int, help="stratified sample size (fits a daily budget)")
    a = ap.parse_args()
    sys.exit(run(a.provider, a.dataset, a.limit, a.sample))
