"""Robustesse de l'évaluation : limites de débit, sauvegarde et reprise."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proof_agent.checker import coqc_available  # noqa: E402
from proof_agent.llm import LLMClient, QuotaExhausted, parse_wait_seconds  # noqa: E402

TPD_MSG = ("Error code: 429 - Rate limit reached for model `openai/gpt-oss-120b` "
           "on tokens per day (TPD): Limit 200000, Used 197041. "
           "Please try again in 3m51.119999999s.")


def test_parse_wait_seconds():
    assert parse_wait_seconds("Please try again in 3m51.5s.") == pytest.approx(231.5)
    assert parse_wait_seconds("try again in 2.5s") == pytest.approx(2.5)
    assert parse_wait_seconds("try again in 1h2m") == pytest.approx(3720)
    assert parse_wait_seconds("no hint here") is None


class _FakeCompletions:
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        if self.errors:
            raise RuntimeError(self.errors.pop(0))
        msg = SimpleNamespace(content="```coq\nreflexivity.\n```")
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                               usage=SimpleNamespace(total_tokens=42))


def _fake_client(errors):
    comp = _FakeCompletions(errors)
    return SimpleNamespace(chat=SimpleNamespace(completions=comp)), comp


def test_daily_quota_raises_quota_exhausted_immediately():
    llm = LLMClient("baseline")
    fake, comp = _fake_client([TPD_MSG])
    with pytest.raises(QuotaExhausted):
        llm._chat_openai_compatible(fake, "s", "u")
    assert comp.calls == 1          # pas d'attente inutile de plusieurs minutes


def test_short_rate_limit_waits_then_succeeds(monkeypatch):
    monkeypatch.setattr("proof_agent.llm.time.sleep", lambda s: None)
    llm = LLMClient("baseline")
    fake, comp = _fake_client(["429 rate limit, please try again in 1.2s"])
    out = llm._chat_openai_compatible(fake, "s", "u")
    assert "reflexivity" in out and comp.calls == 2
    assert llm.tokens == 42


def test_other_errors_are_not_swallowed():
    llm = LLMClient("baseline")
    fake, _ = _fake_client(["401 invalid api key"])
    with pytest.raises(RuntimeError):
        llm._chat_openai_compatible(fake, "s", "u")


@pytest.mark.skipif(not coqc_available(), reason="coqc absent")
def test_resume_completes_a_partial_run_without_redoing_work(tmp_path):
    """On simule une évaluation interrompue, puis on la reprend."""
    script = ROOT / "scripts" / "evaluate.py"
    args = [sys.executable, str(script), "--provider", "baseline",
            "--suite", "memory_isolation", "--configs", "zero-shot"]
    subprocess.run(args, check=True, capture_output=True, cwd=ROOT)
    produced = sorted((ROOT / "results").glob("baseline_*.json"))[-1]
    data = json.loads(produced.read_text())
    assert data["complete"] and len(data["runs"]["zero-shot"]) == 11

    # On tronque à 4 théorèmes faits, marqués d'un drapeau, comme après une coupure.
    data["runs"]["zero-shot"] = data["runs"]["zero-shot"][:4]
    for r in data["runs"]["zero-shot"]:
        r["marker"] = "deja_fait"
    data["complete"] = False
    partial = tmp_path / "partial.json"
    partial.write_text(json.dumps(data))
    produced.unlink()
    produced.with_suffix(".md").unlink()

    out = subprocess.run(args + ["--resume", str(partial)], check=True,
                         capture_output=True, text=True, cwd=ROOT)
    resumed = json.loads(partial.read_text())
    runs = resumed["runs"]["zero-shot"]
    assert resumed["complete"] and len(runs) == 11
    assert sum(r.get("marker") == "deja_fait" for r in runs) == 4   # pas refaits
    assert out.stdout.count("[zero-shot") == 7                        # seulement les 7 restants
