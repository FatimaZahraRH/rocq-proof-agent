"""Recherche de preuves similaires dans le corpus.

Deux méthodes, comparables par ablation :

- « lexical » : similarité de Jaccard sur les identifiants des énoncés. C'est
  la référence utilisée par RocqStar (Khramov et al., 2025).
  Limite observée sur ce benchmark : deux lemmes de même forme mais aux noms
  différents (read/write vs lookup/replace) n'ont presque aucun mot commun,
  et ne sont donc pas rapprochés.

- « shape » (par défaut) : on ANONYMISE l'énoncé avant de comparer. Les
  variables liées deviennent V, les fonctions propres au projet deviennent F ;
  on ne garde tels quels que les symboles de la bibliothèque standard et les
  opérateurs. On compare ensuite les n-grammes (n = 1..3) de cette « forme ».
  Ainsi « read (write m i v) j = read m j » et
  « lookup (replace l n v) p = lookup l p » deviennent identiques.
"""
from __future__ import annotations

import re

from .benchmark import Theorem

_IDENT = re.compile(r"[A-Za-z_][\w']*")
_STOP = {"forall", "Theorem", "Lemma", "nat", "list", "Prop", "exists", "fun"}

# Symboles conservés tels quels dans la « forme » : opérateurs et noms standard.
_TOKEN = re.compile(r"[A-Za-z_][\w'.]*|<>|<=|->|<->|\+\+|/\\|\\/|[=<>+*~()\[\]]")
_KEEP = {"length", "Some", "None", "rev", "map", "exists", "forall", "S", "O",
         "true", "false", "nat", "list", "option", "bool", "fun"}


# ------------------------------- lexical ------------------------------- #
def tokens(statement: str) -> set[str]:
    toks = set(_IDENT.findall(statement)) - _STOP
    m = re.match(r"\s*(?:Theorem|Lemma)\s+([\w']+)", statement)
    if m:
        toks.discard(m.group(1))
    return toks


# -------------------------------- shape -------------------------------- #
def _body(statement: str) -> str:
    body = statement.split(":", 1)[1] if ":" in statement else statement
    return body.strip().rstrip(".")


def _bound_vars(body: str) -> set[str]:
    """Noms introduits par forall/exists — sans leurs types (« (m : mem) » -> m)."""
    out: set[str] = set()
    for m in re.finditer(r"(?:forall|exists)\s+(.*?),", body):
        binders = re.sub(r":[^()]*", "", m.group(1))
        out.update(_IDENT.findall(binders))
    return out


def shape(statement: str) -> list[str]:
    """Énoncé anonymisé, sous forme de suite de symboles."""
    body = _body(statement)
    bound = _bound_vars(body)
    seq: list[str] = []
    for tok in _TOKEN.findall(body):
        if tok in _KEEP or not re.match(r"[A-Za-z_]", tok):
            seq.append(tok)
        elif tok in bound:
            seq.append("V")
        else:
            seq.append("F")
    return seq


def _ngrams(seq: list[str], n_max: int = 3) -> set[tuple[str, ...]]:
    return {tuple(seq[i:i + n]) for n in range(1, n_max + 1)
            for i in range(len(seq) - n + 1)}


# ------------------------------- commun -------------------------------- #
def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def similarity(target: Theorem, cand: Theorem, method: str = "shape") -> float:
    if method == "lexical":
        return jaccard(tokens(target.statement), tokens(cand.statement))
    if method == "shape":
        return jaccard(_ngrams(shape(target.statement)),
                       _ngrams(shape(cand.statement)))
    raise ValueError(f"Méthode inconnue : {method}")


def top_k(target: Theorem, corpus: list[Theorem], k: int = 3,
          method: str = "shape") -> list[Theorem]:
    return sorted(corpus, key=lambda c: similarity(target, c, method),
                  reverse=True)[:k]
