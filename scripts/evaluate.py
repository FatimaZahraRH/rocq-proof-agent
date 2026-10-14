#!/usr/bin/env python3
"""Évaluation : lance l'agent sur le benchmark dans plusieurs configurations.

Configurations (ablation 2x2) :
  zero-shot           : ni exemples, ni retour d'erreur
  feedback            : retour d'erreur seulement
  retrieval           : exemples similaires seulement
  retrieval+feedback  : les deux

Exemples :
  python scripts/evaluate.py --provider baseline           # sans LLM, sans clé
  python scripts/evaluate.py --provider groq               # vrai LLM (clé dans .env)
  python scripts/evaluate.py --provider groq --configs retrieval+feedback --suite memory_isolation

Sorties : results/<fournisseur>_<date>.json (tout le détail, preuves comprises)
          results/<fournisseur>_<date>.md   (tableau de synthèse)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from proof_agent.agent import prove  # noqa: E402
from proof_agent.benchmark import load_dir, load_suite  # noqa: E402
from proof_agent.checker import coqc_available  # noqa: E402
from proof_agent.llm import LLMClient  # noqa: E402

CONFIGS = {
    "zero-shot": (False, False),
    "feedback": (False, True),
    "retrieval": (True, False),
    "retrieval+feedback": (True, True),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None, help="groq|gemini|openai|ollama|baseline")
    ap.add_argument("--model", default=None)
    ap.add_argument("--configs", default=",".join(CONFIGS),
                    help="liste séparée par des virgules")
    ap.add_argument("--suite", default=None, help="basics|memory_isolation (défaut : toutes)")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--retriever", default="shape", choices=["shape", "lexical"],
                    help="méthode de recherche d'exemples (voir retrieval.py)")
    args = ap.parse_args()

    if not coqc_available():
        print("coqc introuvable. Installe Rocq/Coq : sudo apt install coq")
        return 2

    theorems = (load_suite(ROOT / "benchmarks" / f"{args.suite}.v")
                if args.suite else load_dir(ROOT / "benchmarks"))
    corpus = load_dir(ROOT / "corpus")
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]

    results = {"provider": None, "model": None, "max_attempts": args.max_attempts,
               "temperature": args.temperature, "retriever": args.retriever,
               "runs": {}}
    table = []
    for cfg in configs:
        use_r, use_f = CONFIGS[cfg]
        client = LLMClient(args.provider, args.model, args.temperature)
        results["provider"], results["model"] = client.provider, client.model
        runs = []
        for th in theorems:
            run = prove(th, client, corpus, use_r, use_f, args.max_attempts,
                        retriever=args.retriever)
            runs.append(run)
            mark = "OK " if run.proved else "-- "
            print(f"[{cfg:<18}] {mark}{th.suite}/{th.name} ({run.n_attempts} essai(s))")
        results["runs"][cfg] = [asdict(r) | {"n_attempts": r.n_attempts} for r in runs]
        for suite in sorted({r.suite for r in runs}):
            sr = [r for r in runs if r.suite == suite]
            ok = sum(r.proved for r in sr)
            first = sum(r.proved and r.n_attempts == 1 for r in sr)
            rej = sum(a.rejected for r in sr for a in r.attempts)
            table.append((cfg, suite, ok, len(sr), first, rej, client.calls))

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = out / f"{results['provider']}_{stamp}"
    base.with_suffix(".json").write_text(json.dumps(results, indent=2, ensure_ascii=False))

    md = [f"# Résultats — {results['provider']} / {results['model']}",
          f"Tentatives max par théorème : {args.max_attempts} · température : "
          f"{args.temperature} · recherche d'exemples : {args.retriever}",
          "", "| Configuration | Suite | Prouvés | Du 1er coup | Preuves refusées (admit…) |",
          "|---|---|---|---|---|"]
    for cfg, suite, ok, n, first, rej, _ in table:
        md.append(f"| {cfg} | {suite} | {ok}/{n} ({100*ok/n:.0f} %) | {first} | {rej} |")
    base.with_suffix(".md").write_text("\n".join(md) + "\n")
    print("\n" + "\n".join(md))
    print(f"\nDétail : {base.with_suffix('.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
