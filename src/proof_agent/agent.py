"""Agent de preuve : le LLM propose, Rocq juge, l'erreur revient au LLM.

Deux briques qu'on peut activer ou non, pour mesurer l'apport de chacune
(ablation) :
- retrieval : ajouter au prompt des preuves similaires tirées du corpus
  (idée de Rango et RocqStar) ;
- feedback : en cas d'échec, renvoyer au LLM sa tentative et le message
  d'erreur exact de Rocq (idée de « proof repair », ex. Baldur, First et al.
  2023). Sans feedback, chaque tentative repart du même prompt.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .benchmark import Theorem
from .checker import check, clean_proof
from .llm import LLMClient
from .prompts import SYSTEM, build_prompt
from .retrieval import top_k


@dataclass
class Attempt:
    proof: str
    ok: bool
    error: str = ""
    rejected: bool = False


@dataclass
class ProofRun:
    suite: str
    theorem: str
    difficulty: str
    proved: bool
    attempts: list[Attempt] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def n_attempts(self) -> int:
        return len(self.attempts)


def prove(theorem: Theorem, client: LLMClient, corpus: list[Theorem],
          use_retrieval: bool, use_feedback: bool, max_attempts: int = 3,
          k: int = 3, retriever: str = "shape") -> ProofRun:
    t0 = time.time()
    examples = top_k(theorem, corpus, k, retriever) if use_retrieval else None
    run = ProofRun(theorem.suite, theorem.name, theorem.difficulty, proved=False)
    previous = error = None
    error_line = None
    for _ in range(max_attempts):
        prompt = build_prompt(
            theorem, examples,
            previous=previous if use_feedback else None,
            error=error if use_feedback else None,
            error_line=error_line if use_feedback else None)
        raw = client.complete(SYSTEM, prompt)
        proof = clean_proof(raw)
        res = check(theorem, proof)
        run.attempts.append(Attempt(proof, res.ok, res.error, res.rejected))
        if res.ok:
            run.proved = True
            break
        previous, error, error_line = proof, res.error, res.error_line
    run.seconds = round(time.time() - t0, 2)
    return run
