"""Vérification d'une preuve candidate par Rocq (coqc).

C'est le « juge » du pipeline : une preuve n'est acceptée que si Rocq la
vérifie. Trois garde-fous, car un LLM peut produire quelque chose qui
« compile » sans rien prouver :

1. refus des constructions qui contournent la preuve (admit, Admitted, Axiom,
   Parameter, Hypothesis, Variable, Abort...) AVANT même d'appeler Rocq ;
2. compilation par coqc avec une limite de temps ;
3. « Print Assumptions » : le théorème doit être « Closed under the global
   context », c'est-à-dire ne dépendre d'aucun axiome caché.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .benchmark import Theorem

FORBIDDEN = re.compile(
    r"\b(admit|Admitted|Abort|Axiom|Axioms|Parameter|Parameters|Hypothesis|"
    r"Hypotheses|Variable|Variables|Conjecture|Unset|Local\s+Unset)\b"
)
_LOC = re.compile(r'line (\d+), characters (\d+)-(\d+):\s*\n(.*)', re.DOTALL)


@dataclass
class CheckResult:
    ok: bool
    error: str = ""          # message lisible, renvoyé au LLM en cas d'échec
    error_line: int | None = None  # ligne DANS la preuve (1 = première ligne)
    rejected: bool = False   # True si refusée par les garde-fous avant Rocq


def coqc_available() -> bool:
    return shutil.which("coqc") is not None


def clean_proof(raw: str) -> str:
    """Extrait le script de preuve d'une réponse de LLM.

    Retire les balises de code, et un éventuel « Proof. » / « Qed. » que le
    modèle aurait ajouté (le vérificateur les ajoute lui-même).
    """
    m = re.search(r"```(?:coq|rocq|v)?\s*\n(.*?)```", raw, re.DOTALL)
    text = m.group(1) if m else raw
    lines = [l.rstrip() for l in text.strip().splitlines()]
    while lines and lines[0].strip() in ("Proof.", ""):
        lines.pop(0)
    while lines and lines[-1].strip() in ("Qed.", "Defined.", ""):
        lines.pop()
    return "\n".join(lines)


def check(theorem: Theorem, proof: str, timeout: int = 30) -> CheckResult:
    proof = clean_proof(proof)
    if not proof.strip():
        return CheckResult(ok=False, error="Preuve vide.", rejected=True)
    bad = FORBIDDEN.search(proof)
    if bad:
        return CheckResult(
            ok=False, rejected=True,
            error=f"Construction interdite « {bad.group(0)} » : elle contourne "
                  "la preuve au lieu de la faire.")

    header = theorem.context + "\n" + theorem.statement + "\nProof.\n"
    first_proof_line = header.count("\n") + 1
    source = (header + proof + "\nQed.\n"
              + f"Print Assumptions {theorem.name}.\n")

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "Candidate.v"
        f.write_text(source)
        try:
            r = subprocess.run(["coqc", "-q", str(f)], cwd=tmp,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return CheckResult(ok=False, error=f"Délai dépassé ({timeout} s) : "
                               "la preuve boucle ou est trop coûteuse.")

    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0:
        m = _LOC.search(out)
        if m:
            line = int(m.group(1)) - first_proof_line + 1
            msg = m.group(4).strip()
            return CheckResult(ok=False, error_line=line if line >= 1 else None,
                               error=msg[:1500])
        return CheckResult(ok=False, error=out.strip()[:1500])

    if "Closed under the global context" not in out:
        return CheckResult(ok=False, error="La preuve dépend d'axiomes : "
                           + out.strip()[:500])
    return CheckResult(ok=True)
