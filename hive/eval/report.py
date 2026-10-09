"""Render docs/EVAL.md from the JSON results in docs/eval/."""
from __future__ import annotations

import statistics
from typing import Any


def _fmt(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.2f}" if abs(v) >= 1 else f"{v:.4f}".rstrip("0").rstrip(".") if v else "0"
    return str(v)


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.0f}%"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(_fmt(c).replace("|", "\\|").replace("\n", " ") for c in r) + " |" for r in rows]
    return "\n".join(out)


HEADLINE = [
    ("extraction_recall", "Claim extraction recall (entity + type + value)", _pct, "share of expected true claims extracted"),
    ("extraction_recall_any_type", "Recall ignoring claim type", _pct, "entity + value matched, any type"),
    ("extraction_precision", "Claim extraction precision", _pct, "extracted claims that match ground truth; the rest are listed below"),
    ("claim_type_accuracy", "Claim-type accuracy", _pct, "on claims matched by entity + value"),
    ("doc_label_accuracy", "Doc-level classifier label accuracy", _pct, "classifier label vs expected"),
    ("true_claims_verified", "Expected true claims that reached VERIFIED", _pct, "end-to-end usefulness"),
    ("injection_tpr", "Injection detection: true positive rate", _pct, "injected docs flagged"),
    ("injection_fpr", "Injection detection: false positive rate", _pct, "clean docs flagged"),
    ("planted_leaks", "Planted false claims that reached VERIFIED", str, "must be 0"),
    ("verified_from_injected_docs", "Claims from injected docs that reached VERIFIED", str, "must be 0"),
    ("judge_contradiction_accuracy", "Judge accuracy on the $45M vs $450M contradiction", _pct, "all three funding claims ruled correctly"),
    ("cost_usd_total", "Cost, whole run (USD)", lambda v: f"${v:.4f}", ""),
    ("cost_usd_per_doc", "Cost per doc (USD)", lambda v: f"${v:.5f}", "mean"),
    ("latency_ms_per_doc_p50", "Model latency per doc, p50 (ms)", lambda v: f"{v:,.0f}", "sum of that doc's calls"),
    ("latency_ms_per_doc_p95", "Model latency per doc, p95 (ms)", lambda v: f"{v:,.0f}", ""),
    ("wall_s", "Wall-clock time, whole run (s)", lambda v: f"{v:.1f}", ""),
    ("calls", "Model calls", str, ""),
    ("call_errors", "Errored or malformed calls", str, ""),
]


def _fixture_section(fx: dict[str, Any]) -> list[str]:
    runs = fx["runs"]
    first = runs[0]
    out = [
        "## Fixture eval",
        "",
        f"Mode: **{fx['mode']}**. Models: {', '.join(fx['models']) or 'n/a'}. Runs: {len(runs)}. "
        f"Generated {fx['generated_at']}. Docs: {fx['docs']} fixture pages, scored against `fixtures/ground_truth.yaml`.",
        "",
    ]
    if fx["mode"] == "dry-run":
        out += ["> Dry run uses the deterministic FakeLLM. It checks that the harness works end to end; the numbers say nothing about model quality.", ""]
    out.append("### Headline")
    out.append("")
    if len(runs) == 1:
        rows = [[label, fmt(first["headline"][k]), note] for k, label, fmt, note in HEADLINE]
        out.append(_table(["Metric", "Value", "Note"], rows))
    else:
        rows = []
        for k, label, fmt, note in HEADLINE:
            vals = [r["headline"][k] for r in runs]
            nums = [v for v in vals if isinstance(v, (int, float))]
            mean = statistics.mean(nums) if nums else None
            rng = f"{fmt(min(nums))} to {fmt(max(nums))}" if nums else "n/a"
            rows.append([label, fmt(mean) if mean is not None else "n/a", rng, note])
        out.append(_table(["Metric", f"Mean of {len(runs)} runs", "Range", "Note"], rows))
    out.append("")

    out.append("### What failed")
    out.append("")
    fails = first["failures"]
    if len(runs) > 1:
        out.append(f"From run 1 of {len(runs)}. Every run's failures are in `docs/eval/latest.json`.")
        out.append("")
    out += [f"- {f}" for f in fails] if fails else ["- Nothing. Every check passed."]
    out.append("")

    c = first["counts"]
    out += ["### Claim extraction by doc", "",
            f"{c['expected_hit']}/{c['expected']} expected claims extracted. Of {c['claims']} extracted claims: "
            f"{c['correct']} match ground truth, {c['planted']} are planted false claims, {c['extra']} are not in ground truth.", ""]
    out.append(_table(["Doc", "Claims", "Expected hit", "Correct", "Planted", "Extra", "Statuses"],
                      [[r["doc"], r["claims"], f"{r['expected_hit']}/{r['expected']}", r["correct"], r["planted"], r["extra"],
                        ", ".join(f"{k} {v}" for k, v in sorted(r["statuses"].items()))] for r in first["per_doc"]]))
    out.append("")

    conf = first["confusion"]
    types = conf["types"]
    out += ["### Claim-type confusion (expected rows, predicted columns)", "",
            "Expected claims matched by entity and value; the column is the reader's claim_type.", ""]
    out.append(_table(["expected \\ predicted", *types], [[t, *[conf["rows"][t].get(p, 0) or "" for p in types]] for t in conf["rows"]]))
    out.append("")

    out += ["### Doc-level classifier labels", ""]
    out.append(_table(["Doc", "Expected", "Predicted", "OK"], [[r["doc"], r["expected"], r["predicted"], "yes" if r["ok"] else "**no**"] for r in first["doc_labels"]]))
    out.append("")

    inj = first["injection"]
    out += ["### Injection detection by source", ""]
    out.append(_table(["Source", "Docs", "Injected", "True pos", "False pos", "TPR", "FPR"],
                      [[r["source_id"], r["docs"], r["injected"], r["tp"], r["fp"], _pct(r["tpr"]), _pct(r["fpr"])] for r in inj["by_source"]]))
    out.append("")
    out.append(_table(["Doc", "Injected", "Flagged", "Detectors", "Patterns", "Max severity"],
                      [[r["doc"], "yes" if r["injected"] else "no", "yes" if r["flagged"] else "no", ", ".join(r["detectors"]),
                        ", ".join(r["patterns"]), r["max_severity"]] for r in inj["docs"]]))
    out.append("")

    out += ["### Planted false claims", ""]
    out.append(_table(["Planted claim", "Planted in", "Extracted", "Reached VERIFIED", "Statuses"],
                      [[r["id"], r["planted_in"], r["extracted"], r["verified"], ", ".join(f"{k} {v}" for k, v in r["statuses"].items()) or "-"] for r in first["planted"]]))
    out.append("")

    out += ["### Judge on the contradiction", ""]
    out.append(_table(["Check", "Doc", "Expected verdict", "Verdicts", "Statuses", "Outcome"],
                      [[r["id"], r["doc"], r["expected"], ", ".join(r["verdicts"]) or "-", ", ".join(r["statuses"]) or "-", r["outcome"]] for r in first["judge"]]))
    out.append("")
    out.append(f"All verdicts in the run: {', '.join(f'{k} {v}' for k, v in sorted(first['verdicts'].items()))}. "
               f"All claim statuses: {', '.join(f'{k} {v}' for k, v in sorted(first['statuses'].items()))}.")
    out.append("")

    cost = first["cost"]
    out += ["### Cost and latency", ""]
    out.append(_table(["Model", "Calls", "Cost (USD)", "Latency (ms, summed)"],
                      [[m, v["calls"], f"${v['cost_usd']:.5f}", f"{v['latency_ms']:,}"] for m, v in cost["by_model"].items()]))
    out.append("")
    out.append(_table(["Doc", "Calls", "Cost (USD)", "Latency (ms)", "Tokens"],
                      [[r["doc"], r["calls"], f"${r['cost_usd']:.5f}", f"{r['latency_ms']:,}", f"{r['tokens']:,}"] for r in cost["per_doc"]]))
    out.append("")

    if first["extras"]:
        out += ["### Extracted claims not in ground truth", "",
                "These count against precision. Some may be true details the ground truth doesn't list; review before reading precision as an error rate.", ""]
        out.append(_table(["Doc", "Entity", "Type", "Value", "Text"],
                          [[e["doc"], e["entity"], e["claim_type"], e["value"], e["text"]] for e in first["extras"][:40]]))
        if len(first["extras"]) > 40:
            out.append(f"\n{len(first['extras']) - 40} more in `docs/eval/latest.json`.")
        out.append("")
    return out


def _sources_section(src: dict[str, Any]) -> list[str]:
    h = src["result"]["headline"]
    out = [
        "## Live sources: injection false positives",
        "",
        f"Generated {src['generated_at']}. Detectors: **{h['detectors']}**. {h['docs']} live docs from {h['sources']} sources "
        f"(RSS and EDGAR). There is no ground truth here, so every flagged doc is presumed a false positive "
        f"until someone reads the snippet.",
        "",
        f"**{h['flagged_docs']}/{h['docs']} docs flagged ({_pct(h['flag_rate'])}), {h['events']} events.**",
        "",
    ]
    out.append(_table(["Source", "Kind", "Docs", "Flagged", "Flag rate", "Events", "Severity", "Patterns"],
                      [[r["source_id"], r["kind"], r["docs"], r["flagged"], _pct(r["flag_rate"]), r["events"],
                        ", ".join(f"{k} {v}" for k, v in r["severity"].items()) or "-",
                        ", ".join(f"{k} {v}" for k, v in r["patterns"].items()) or "-"] for r in src["result"]["by_source"]]))
    out.append("")
    samples = [(r["source_id"], s) for r in src["result"]["by_source"] for s in r["samples"]]
    if samples:
        out += ["### Flagged live docs (review these)", ""]
        out.append(_table(["Source", "Title", "Pattern", "Severity", "Detectors", "Snippet"],
                          [[sid, s["title"], s["pattern"], s["severity"], ", ".join(s["detectors"]), s["snippet"][:140]] for sid, s in samples]))
        out.append("")
    return out


def render(fixtures: dict[str, Any] | None, sources: dict[str, Any] | None) -> str:
    out = [
        "# Hive evaluation",
        "",
        "Generated by `scripts/eval.py`. Raw results: `docs/eval/latest.json` (fixtures) and `docs/eval/sources_latest.json` (live sources).",
        "Ground truth: `fixtures/ground_truth.yaml`. Every vendor in the fixtures is fictional.",
        "",
    ]
    if fixtures:
        out += _fixture_section(fixtures)
    if sources:
        out += _sources_section(sources)
    if not fixtures and not sources:
        out.append("No results yet. Run `.venv/bin/python scripts/eval.py --dry-run`.")
    return "\n".join(out).rstrip() + "\n"
