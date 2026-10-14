"""Construction des prompts envoyés au LLM."""
from __future__ import annotations

from .benchmark import Theorem

SYSTEM = """Tu es un expert de l'assistant de preuve Rocq (anciennement Coq, version 8.18).
On te donne des définitions et un énoncé. Écris un script de preuve complet.

Règles :
- Réponds UNIQUEMENT avec le script de preuve dans un bloc ```coq ... ```.
- N'écris ni « Proof. » ni « Qed. » : ils sont ajoutés automatiquement.
- N'utilise jamais admit, Admitted, Axiom ni aucun moyen de contourner la preuve :
  ta preuve sera refusée.
- Tu peux utiliser les tactiques standard (intros, induction, destruct, simpl,
  rewrite, apply, lia, discriminate...) et les lemmes de la bibliothèque standard
  importée, mais PAS les théorèmes que tu ne vois pas dans le contexte.
- Les énoncés sont indépendants : n'utilise pas d'autre théorème du benchmark ;
  si tu as besoin d'un lemme intermédiaire, prouve-le dans ta preuve avec assert.
"""


def build_prompt(theorem: Theorem, examples: list[Theorem] | None = None,
                 previous: str | None = None, error: str | None = None,
                 error_line: int | None = None) -> str:
    parts = [
        "### Contexte (définitions disponibles)\n```coq\n"
        + theorem.context.strip() + "\n```",
    ]
    if examples:
        ex = "\n\n".join(
            f"{e.statement}\nProof.\n{e.reference_proof}\nQed." for e in examples)
        parts.append(
            "### Exemples de preuves sur des énoncés proches "
            "(autres définitions : à imiter pour le style, pas à réutiliser)\n"
            "```coq\n" + ex + "\n```")
    parts.append("### Énoncé à prouver\n```coq\n" + theorem.statement + "\n```")
    if previous is not None:
        where = f" (ligne {error_line} de ta preuve)" if error_line else ""
        parts.append(
            "### Ta tentative précédente a été refusée par Rocq\n"
            "```coq\n" + previous + "\n```\n"
            f"Erreur{where} :\n```\n{error}\n```\n"
            "Corrige la preuve en tenant compte de cette erreur.")
    return "\n\n".join(parts)
