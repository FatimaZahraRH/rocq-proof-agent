"""Tests : benchmark valide, garde-fous du vérificateur, boucle de l'agent."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proof_agent.agent import prove  # noqa: E402
from proof_agent.benchmark import load_dir  # noqa: E402
from proof_agent.checker import check, clean_proof, coqc_available  # noqa: E402
from proof_agent.llm import LLMClient  # noqa: E402
from proof_agent.prompts import build_prompt  # noqa: E402
from proof_agent.retrieval import top_k  # noqa: E402

needs_coq = pytest.mark.skipif(not coqc_available(), reason="coqc absent")

BENCH = load_dir(ROOT / "benchmarks")
CORPUS = load_dir(ROOT / "corpus")
BY_NAME = {t.name: t for t in BENCH}


# ----------------------------- Benchmark ----------------------------- #
def test_benchmark_loaded():
    assert len(BENCH) == 21
    assert {t.suite for t in BENCH} == {"basics", "memory_isolation"}
    assert len(CORPUS) == 10


def test_no_leakage_between_corpus_and_benchmark():
    """Le corpus ne doit contenir ni le nom ni l'énoncé d'un théorème évalué."""
    bench_names = {t.name for t in BENCH}
    assert not bench_names & {c.name for c in CORPUS}
    bench_bodies = {t.statement.split(":", 1)[1] for t in BENCH}
    corpus_bodies = {c.statement.split(":", 1)[1] for c in CORPUS}
    assert not bench_bodies & corpus_bodies


def test_reference_proofs_never_in_prompt():
    t = BY_NAME["write_read_other"]
    prompt = build_prompt(t, top_k(t, CORPUS))
    assert t.reference_proof not in prompt


@needs_coq
@pytest.mark.parametrize("th", BENCH + CORPUS, ids=lambda t: t.name)
def test_every_reference_proof_checks_alone(th):
    """Chaque énoncé est prouvable avec SEULEMENT le contexte (pas les autres théorèmes)."""
    assert check(th, th.reference_proof).ok


# ----------------------------- Vérificateur ----------------------------- #
def test_clean_proof_strips_fences_and_proof_qed():
    raw = "Voici :\n```coq\nProof.\n  intros n.\n  lia.\nQed.\n```\nFin."
    assert clean_proof(raw) == "  intros n.\n  lia."


@needs_coq
@pytest.mark.parametrize("cheat", ["admit.", "intros. Admitted.",
                                   "Axiom x : False. intros."])
def test_cheating_is_rejected_before_rocq(cheat):
    r = check(BY_NAME["add_zero_right"], cheat)
    assert not r.ok and r.rejected


@needs_coq
def test_wrong_proof_reports_rocq_error_and_line():
    r = check(BY_NAME["add_zero_right"], "intros n.\nreflexivity.")
    assert not r.ok and not r.rejected
    assert r.error_line == 2
    assert "Error" in r.error


# ----------------------------- Recherche ----------------------------- #
def test_shape_retrieval_finds_analogous_lemma_despite_different_names():
    """read/write vs lookup/replace : même forme, noms différents."""
    names = [c.name for c in top_k(BY_NAME["write_read_other"], CORPUS, 3, "shape")]
    assert names[0] == "lookup_replace_neq"


def test_lexical_retrieval_misses_it():
    """Constat documenté : la recherche par mots communs rate ce lemme."""
    names = [c.name for c in top_k(BY_NAME["write_read_other"], CORPUS, 3, "lexical")]
    assert "lookup_replace_neq" not in names


def test_shape_abstracts_names():
    from proof_agent.retrieval import shape
    a = shape(BY_NAME["write_read_other"].statement)
    b = shape(next(c for c in CORPUS if c.name == "lookup_replace_neq").statement)
    assert a[a.index("<>"):] == b[b.index("<>"):]


# ----------------------------- Agent ----------------------------- #
WRONG = "```coq\nintros n.\nreflexivity.\n```"
RIGHT = ("```coq\ninduction n as [| k IH]; simpl.\n- reflexivity.\n"
         "- rewrite IH. reflexivity.\n```")


@needs_coq
def test_agent_repairs_proof_with_feedback():
    client = LLMClient("scripted")
    client.set_script([WRONG, RIGHT])
    run = prove(BY_NAME["add_zero_right"], client, CORPUS,
                use_retrieval=False, use_feedback=True, max_attempts=3)
    assert run.proved and run.n_attempts == 2
    assert not run.attempts[0].ok and run.attempts[0].error


@needs_coq
def test_feedback_prompt_contains_previous_attempt_and_error():
    seen = []

    class Spy(LLMClient):
        def complete(self, system, user):
            seen.append(user)
            return super().complete(system, user)

    client = Spy("scripted")
    client.set_script([WRONG, RIGHT])
    prove(BY_NAME["add_zero_right"], client, CORPUS, False, True, 3)
    assert "tentative précédente" not in seen[0]
    assert "tentative précédente" in seen[1] and "reflexivity" in seen[1]


@needs_coq
def test_without_feedback_prompts_are_identical():
    seen = []

    class Spy(LLMClient):
        def complete(self, system, user):
            seen.append(user)
            return super().complete(system, user)

    client = Spy("scripted")
    client.set_script([WRONG, WRONG, WRONG])
    run = prove(BY_NAME["add_zero_right"], client, CORPUS, False, False, 3)
    assert not run.proved and run.n_attempts == 3
    assert seen[0] == seen[1] == seen[2]
