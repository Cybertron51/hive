import asyncio
from pathlib import Path

import pytest

from hive.collectors import collect_all, load_sources
from hive.eval import report, score
from hive.models import AgentRun, Claim, ClaimStatus, Detector, InjectionEvent, JudgeVerdict, Role
from hive.swarm.orchestrator import SwarmResult

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "config/sources.yaml"


@pytest.fixture(scope="module")
def corpus():
    docs = asyncio.run(collect_all(SOURCES, kinds={"fixture"}))
    url_to_file = {s["url"]: Path(s["path"]).name for s in load_sources(SOURCES) if s["kind"] == "fixture"}
    fixture_of = {d.doc_id: url_to_file[d.url] for d in docs}
    by_file = {f: d for d_id, f in fixture_of.items() for d in docs if d.doc_id == d_id}
    return docs, fixture_of, by_file, score.load_ground_truth()


def _claim(doc, spec, status=ClaimStatus.VERIFIED, verdict=JudgeVerdict.AGREE, text=None):
    return Claim(run_id="r", doc_id=doc.doc_id, source_id=doc.source_id, entity=spec["entity"], claim_type=spec["claim_type"],
                 text=text or spec.get("value") or spec["entity"], value=spec.get("value", ""), confidence=0.9,
                 status=status, judge_verdict=verdict)


def _oracle(docs, by_file, gt):
    """A perfect swarm: every expected claim extracted and verified, planted ones quarantined, injection flagged."""
    claims, events, runs = [], [], []
    for fname, spec in gt["docs"].items():
        doc = by_file[fname]
        claims += [_claim(doc, e) for e in spec.get("expected") or []]
        for p in spec.get("planted") or []:
            text = by_file[fname].text
            claims.append(_claim(doc, p, status=ClaimStatus.QUARANTINED, verdict=JudgeVerdict.DISAGREE, text=text[:4000]))
        if spec.get("injected"):
            events.append(InjectionEvent(swarm_id="s", doc_id=doc.doc_id, source_id=doc.source_id, detector=Detector.HEURISTIC,
                                         pattern="ignore_instructions", snippet="x", severity=0.9))
        runs.append(AgentRun(swarm_id="s", role=Role.CLASSIFIER, model="m", doc_id=doc.doc_id, source_id=doc.source_id,
                             label=spec.get("label", "other"), cost_usd=0.001, latency_ms=100))
    return SwarmResult(swarm_id="s", runs=runs, claims=claims, injection_events=events)


def test_amount_normalisation():
    assert score.amounts("$450 million") == score.amounts("$450.0 million") == score.amounts("450M") == {(450e6, False)}
    assert (45e6, False) not in score.amounts("raised $450 million")
    assert score.amounts("41% faster") == {(41.0, True)}
    assert (0.15, False) in score.amounts("a flat $0.15 per GB")


def test_every_ground_truth_spec_is_satisfiable_by_its_fixture(corpus):
    docs, _, by_file, gt = corpus
    for fname, spec in gt["docs"].items():
        assert fname in by_file, f"{fname} in ground truth but not collected"
        text = by_file[fname].text
        for kind in ("expected", "optional", "planted"):
            for s in spec.get(kind) or []:
                c = Claim(run_id="r", doc_id="d", source_id="x", entity=s["entity"], claim_type=s["claim_type"], text=text, value="")
                assert score.value_matches(s, c), f"{s['id']} cannot match the text of {fname}"
    assert set(gt["docs"]) == {Path(s["path"]).name for s in load_sources(SOURCES) if s["kind"] == "fixture"}


def test_oracle_run_scores_perfectly(corpus):
    docs, fixture_of, by_file, gt = corpus
    res = _oracle(docs, by_file, gt)
    for s in gt["contradiction"]:
        doc = by_file[s["doc"]]
        for c in res.claims:
            if c.doc_id == doc.doc_id and score.matches(s, c):
                c.judge_verdict = JudgeVerdict(s["expected_verdict"])
    h = score.score_fixtures(docs, fixture_of, res, gt, 1.0)["headline"]
    assert h["extraction_recall"] == 1.0
    assert h["claim_type_accuracy"] == 1.0
    assert h["doc_label_accuracy"] == 1.0
    assert h["injection_tpr"] == 1.0 and h["injection_fpr"] == 0.0
    assert h["planted_leaks"] == 0 and h["verified_from_injected_docs"] == 0
    assert h["real_vendor_misattributions"] == 0


def test_real_vendor_misattribution_is_reported(corpus):
    docs, fixture_of, by_file, gt = corpus
    res = _oracle(docs, by_file, gt)
    blog = by_file["nullgrid_blog_update.html"]
    res.claims.append(_claim(blog, {"entity": "SentinelOne", "claim_type": "other", "value": "x"}, status=ClaimStatus.PENDING))
    out = score.score_fixtures(docs, fixture_of, res, gt, 1.0)
    assert out["headline"]["real_vendor_misattributions"] == 1
    assert any("REAL vendor SentinelOne" in f for f in out["failures"])


def test_planted_leak_and_missed_injection_are_reported(corpus):
    docs, fixture_of, by_file, gt = corpus
    res = _oracle(docs, by_file, gt)
    news = by_file["quillon_funding_news.html"]
    leak = next(c for c in res.claims if c.doc_id == news.doc_id and c.claim_type == "funding")
    leak.status = ClaimStatus.VERIFIED
    res.injection_events = []
    out = score.score_fixtures(docs, fixture_of, res, gt, 1.0)
    assert out["headline"]["planted_leaks"] == 1
    assert out["headline"]["injection_tpr"] == 0.0
    assert any("LEAKED" in f and "planted_quillon_45m" in f for f in out["failures"])
    assert any("nullgrid_blog_update.html was NOT flagged" in f for f in out["failures"])


def test_judge_contradiction_scoring(corpus):
    docs, fixture_of, by_file, gt = corpus
    res = _oracle(docs, by_file, gt)
    out = score.score_fixtures(docs, fixture_of, res, gt, 1.0)
    rows = {r["id"]: r for r in out["judge"]}
    assert rows["judge_quillon_45m"]["outcome"] == "correct"
    assert rows["judge_quillon_450m_pr"]["outcome"] == "correct"


def test_report_renders(corpus):
    docs, fixture_of, by_file, gt = corpus
    out = score.score_fixtures(docs, fixture_of, _oracle(docs, by_file, gt), gt, 1.0)
    md = report.render({"mode": "live", "generated_at": "t", "models": ["m"], "docs": 14, "runs": [out, out]}, None)
    assert "Mean of 2 runs" in md and "Planted false claims" in md
