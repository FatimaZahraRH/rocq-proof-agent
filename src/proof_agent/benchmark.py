"""Lecture des suites de théorèmes (.v) au format du projet.

Un fichier contient :
- un CONTEXTE (imports, définitions) : tout ce qui précède le premier marqueur ;
- des blocs « (* @theorem nom | difficulté *) » suivis de l'énoncé, de
  « Proof. », d'une preuve de référence et de « Qed. ».

L'agent ne reçoit que le contexte et l'énoncé. La preuve de référence sert
uniquement à vérifier que l'énoncé est prouvable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_MARKER = re.compile(r"\(\*\s*@theorem\s+(\S+)\s*\|\s*(\S+)\s*\*\)")
_STMT = re.compile(
    r"(?P<stmt>(?:Theorem|Lemma)\s+(?P<name>[A-Za-z_][\w']*)\b.*?\.)\s*\n\s*Proof\.\s*\n"
    r"(?P<proof>.*?)\n\s*Qed\.",
    re.DOTALL,
)


@dataclass(frozen=True)
class Theorem:
    suite: str
    name: str
    difficulty: str
    statement: str        # « Theorem nom : ... . »
    reference_proof: str  # jamais montrée à l'agent
    context: str          # imports + définitions de la suite


def load_suite(path: str | Path) -> list[Theorem]:
    path = Path(path)
    text = path.read_text()
    markers = list(_MARKER.finditer(text))
    if not markers:
        raise ValueError(f"Aucun marqueur @theorem dans {path}")
    context = text[: markers[0].start()].rstrip() + "\n"
    suite = path.stem
    theorems: list[Theorem] = []
    for idx, mk in enumerate(markers):
        end = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
        block = text[mk.end():end]
        m = _STMT.search(block)
        if not m:
            raise ValueError(f"Bloc mal formé pour {mk.group(1)} dans {path}")
        if m.group("name") != mk.group(1):
            raise ValueError(
                f"Marqueur {mk.group(1)} != énoncé {m.group('name')} dans {path}")
        theorems.append(Theorem(
            suite=suite,
            name=m.group("name"),
            difficulty=mk.group(2),
            statement=m.group("stmt").strip(),
            reference_proof=m.group("proof").strip("\n"),
            context=context,
        ))
    return theorems


def load_dir(directory: str | Path) -> list[Theorem]:
    out: list[Theorem] = []
    for p in sorted(Path(directory).glob("*.v")):
        out.extend(load_suite(p))
    return out
