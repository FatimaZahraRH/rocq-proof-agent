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
  python scripts/evaluate.py --provider groq --resume results/groq_XXXX.json

Les résultats sont enregistrés APRÈS CHAQUE THÉORÈME dans
results/<fournisseur>_<date>.json (+ .md). Si le quota du fournisseur est épuisé
(ex. limite de tokens par jour de Groq), le script s'arrête proprement : relance
plus tard avec --resume <fichier.json> pour reprendre là où il s'était arrêté.
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
from proof_agent.llm import LLMClient, QuotaExhausted  # noqa: E402

CONFIGS = {
    "zero-shot": (False, False),
    "feedback": (False, True),
    "retrieval": (True, False),
    "retrieval+feedback": (True, True),
}


def summarize(results: dict) -> list[str]:
    md = [f"# Résultats — {results['provider']} / {results['model']}",
          f"Tentatives max par théorème : {results['max_attempts']} · température : "
          f"{results['temperature']} · recherche d'exemples : {results['retriever']}"
          + (f" · effort de raisonnement : {results['reasoning_effort']}"
             if results.get("reasoning_effort") else ""),
          f"Tokens consommés : {results.get('tokens', 0)}"
          + ("  ·  **ÉVALUATION INCOMPLÈTE**" if not results.get("complete") else ""),
          "", "| Configuration | Suite | Prouvés | Du 1er coup | Preuves refusées (admit…) |",
          "|---|---|---|---|---|"]
    for cfg, runs in results["runs"].items():
        for suite in sorted({r["suite"] for r in runs}):
            sr = [r for r in runs if r["suite"] == suite]
            ok = sum(r["proved"] for r in sr)
            first = sum(r["proved"] and r["n_attempts"] == 1 for r in sr)
            rej = sum(a["rejected"] for r in sr for a in r["attempts"])
            expected = results["expected"].get(suite, len(sr))
            done = "" if len(sr) == expected else f" — {len(sr)}/{expected} faits"
            md.append(f"| {cfg} | {suite} | {ok}/{len(sr)} ({100*ok/len(sr):.0f} %){done} "
                      f"| {first} | {rej} |")
    return md


def show(path: Path) -> str:
    """Chemin lisible : relatif au projet si possible, absolu sinon."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def save(results: dict, base: Path) -> None:
    base.with_suffix(".json").write_text(json.dumps(results, indent=2, ensure_ascii=False))
    base.with_suffix(".md").write_text("\n".join(summarize(results)) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default=None, help="groq|gemini|openai|ollama|baseline")
    ap.add_argument("--model", default=None)
    ap.add_argument("--configs", default=",".join(CONFIGS),
                    help="liste séparée par des virgules")
    ap.add_argument("--suite", default=None, help="basics|memory_isolation (défaut : toutes)")
    ap.add_argument("--max-attempts", type=int, default=3)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--retriever", default="shape", choices=["shape", "lexical"])
    ap.add_argument("--resume", default=None,
                    help="fichier results/*.json d'une évaluation interrompue")
    args = ap.parse_args()

    if not coqc_available():
        print("coqc introuvable. Installe Rocq/Coq : sudo apt install coq")
        return 2

    theorems = (load_suite(ROOT / "benchmarks" / f"{args.suite}.v")
                if args.suite else load_dir(ROOT / "benchmarks"))
    corpus = load_dir(ROOT / "corpus")
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    client = LLMClient(args.provider, args.model, args.temperature)

    if args.resume:
        base = Path(args.resume).with_suffix("")
        results = json.loads(Path(args.resume).read_text())
        if (results["provider"], results["model"]) != (client.provider, client.model):
            print(f"Le fichier à reprendre a été produit avec {results['provider']}/"
                  f"{results['model']}, pas {client.provider}/{client.model}.")
            return 2
        print(f"Reprise de {args.resume}")
    else:
        (ROOT / "results").mkdir(exist_ok=True)
        base = ROOT / "results" / f"{client.provider}_{time.strftime('%Y%m%d-%H%M%S')}"
        results = {"provider": client.provider, "model": client.model,
                   "max_attempts": args.max_attempts, "temperature": args.temperature,
                   "retriever": args.retriever,
                   "reasoning_effort": client.reasoning_effort,
                   "tokens": 0, "complete": False, "runs": {}}
    results["expected"] = {s: sum(t.suite == s for t in theorems)
                           for s in {t.suite for t in theorems}}
    tokens_before = results.get("tokens", 0)

    try:
        for cfg in configs:
            use_r, use_f = CONFIGS[cfg]
            done = {(r["suite"], r["theorem"]) for r in results["runs"].get(cfg, [])}
            results["runs"].setdefault(cfg, [])
            for th in theorems:
                if (th.suite, th.name) in done:
                    continue
                run = prove(th, client, corpus, use_r, use_f, args.max_attempts,
                            retriever=results["retriever"])
                results["runs"][cfg].append(asdict(run) | {"n_attempts": run.n_attempts})
                results["tokens"] = tokens_before + client.tokens
                save(results, base)
                mark = "OK " if run.proved else "-- "
                print(f"[{cfg:<18}] {mark}{th.suite}/{th.name} ({run.n_attempts} essai(s))")
        results["complete"] = True
        save(results, base)
    except QuotaExhausted as e:
        save(results, base)
        print("\n⚠ Quota du fournisseur épuisé : évaluation mise en pause, "
              "résultats déjà obtenus enregistrés.")
        print(f"  Détail : {str(e)[:300]}")
        print(f"  Pour reprendre plus tard :\n  python scripts/evaluate.py "
              f"--provider {client.provider} --resume {show(base.with_suffix('.json'))}")
    except KeyboardInterrupt:
        save(results, base)
        print(f"\nInterrompu. Résultats partiels enregistrés : "
              f"{show(base.with_suffix('.json'))} (reprise possible avec --resume)")
        return 130

    print("\n" + "\n".join(summarize(results)))
    print(f"\nDétail : {show(base.with_suffix('.json'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
