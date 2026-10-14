# Rocq Proof Agent

**Un LLM propose des preuves formelles, Rocq les vérifie, l'erreur revient au LLM.**
Reproduction et évaluation, à petite échelle, d'approches récentes d'assistance
à la vérification formelle par IA, appliquées à des propriétés de **sécurité
mémoire** (accès hors bornes, isolation entre zones mémoire).

> **État actuel.** Le benchmark, le vérificateur, l'agent et l'évaluation sont
> fonctionnels et testés (50 tests). Premiers résultats avec un vrai LLM
> (gpt-oss-120b) : une seule passe, interrompue par le quota gratuit de l'API —
> à lire comme une tendance, pas comme une mesure définitive.

---

## Pourquoi

Prouver qu'un logiciel respecte une propriété de sécurité (par exemple : « une
écriture en mémoire ne modifie que sa propre case ») se fait avec un assistant
de preuve comme Rocq. C'est un travail précis, long et manuel. Des travaux
récents utilisent des LLM pour proposer des étapes de preuve, l'assistant de
preuve servant de juge infaillible : une preuve acceptée par Rocq est correcte,
quelle que soit la manière dont elle a été produite.

Ce projet pose une question simple et mesurable : **qu'apportent, chacune, les
deux briques que ces travaux combinent ?**

1. **la recherche de preuves similaires**, ajoutées au prompt (Rango, RocqStar) ;
2. **le retour d'erreur** : renvoyer au LLM le message exact de Rocq pour qu'il
   corrige sa preuve (« proof repair », ex. Baldur).

## Comment ça marche

```
 énoncé + définitions ──┐
                        ├──▶ LLM ──▶ preuve candidate ──▶ garde-fous ──▶ coqc + Print Assumptions
 preuves similaires ────┘     ▲                          (admit, Axiom…      │
 (corpus séparé)              │                           refusés)           │
                              └──────── erreur exacte de Rocq ◀── refusée ───┘
                                                                  acceptée ──▶ prouvé ✔
```

- **Benchmark** (`benchmarks/`) : 21 théorèmes, chacun avec une preuve de
  référence qui prouve qu'il est faisable (jamais montrée à l'agent).
  - `basics` (10) : arithmétique et listes, en échauffement ;
  - `memory_isolation` (11) : modèle mémoire jouet (`read`, `write`,
    `safe_read`, régions) et propriétés de sécurité, dont l'isolation : une
    écriture hors d'une région ne modifie pas la région.
- **Vérificateur** (`checker.py`) : Rocq est le seul juge. Trois garde-fous,
  car un LLM peut « tricher » sans le vouloir : refus de `admit`, `Admitted`,
  `Axiom`… avant compilation ; limite de temps ; et `Print Assumptions`, qui
  doit répondre « Closed under the global context » (aucun axiome caché).
- **Recherche d'exemples** (`retrieval.py`) : un corpus séparé de 10 lemmes
  sur **d'autres** structures (registres, `lookup`/`replace`…). Aucun énoncé du
  benchmark n'y figure (vérifié par un test).
- **Agent** (`agent.py`) : jusqu'à N tentatives ; chaque brique s'active ou non.

## Résultats

### Référence sans LLM

Une « fausse » IA qui propose toujours `intros; simpl; auto.` puis
`intros; lia.` : c'est le niveau qu'un agent LLM doit dépasser pour être utile.

| Configuration | Suite | Prouvés |
|---|---|---|
| `intros; simpl; auto.` | basics | 3/10 (30 %) |
| `intros; simpl; auto.` | memory_isolation | **0/11 (0 %)** |
| puis `intros; lia.` | basics | 4/10 (40 %) |
| puis `intros; lia.` | memory_isolation | **0/11 (0 %)** |

La suite `memory_isolation` résiste entièrement à l'automatisation naïve : il
faut des inductions et des études de cas propres aux définitions. C'est là que
l'apport d'un LLM se mesure.

### Avec un LLM — première passe (gpt-oss-120b via Groq, 14/10/2026)

3 tentatives maximum par théorème, température 0,2, recherche par forme.

| Configuration | basics | memory_isolation |
|---|---|---|
| Référence sans LLM | 3/10 | 0/11 |
| LLM seul (zero-shot) | 7/10 | 6/11 |
| LLM + retour d'erreur | **9/10** | **7/11** |
| LLM + exemples | 8/10 | 5/11 |
| LLM + exemples + retour d'erreur | 8/9 *(interrompu)* | *non lancé* |

**Ce qu'on peut en dire, avec prudence :**

- Le LLM fait nettement mieux que l'automatisation naïve, surtout sur
  l'isolation mémoire (0 → 6 ou 7 théorèmes sur 11).
- Le retour d'erreur de Rocq aide de façon cohérente sur les deux suites.
- Les exemples seuls n'aident pas sur l'isolation mémoire dans cette passe
  (5/11 contre 6/11 sans). Avec un seul essai par configuration et des écarts
  d'un théorème, **ce n'est pas distinguable du hasard** : il faut plusieurs
  passes avant de conclure.
- Trois théorèmes n'ont été prouvés dans **aucune** configuration :
  `write_read_other`, `write_outside_region_isolated` et
  `safe_read_after_write_other`. Ce sont précisément les propriétés
  d'**isolation** (une écriture en `i` ne change pas la case `j ≠ i`), qui
  demandent une double étude de cas sur `i` et `j` avec une hypothèse
  d'inégalité à faire descendre dans l'induction. C'est le point dur à
  analyser en priorité (lire les erreurs de Rocq dans le JSON).

**Pourquoi la passe est incomplète :** le niveau gratuit de Groq limite ce
modèle à 200 000 tokens par jour, et un modèle qui « raisonne » en consomme
beaucoup. Le script enregistre désormais après chaque théorème et reprend là
où il s'est arrêté (`--resume`).

### Un constat sur la recherche d'exemples

La méthode de référence de RocqStar compare les **mots** des énoncés. Sur ce
benchmark, elle rate un cas instructif : `read (write m i v) j = read m j` et
`lookup (replace l n v) p = lookup l p` ont exactement la même forme, et se
prouvent de la même façon, mais n'ont presque aucun mot en commun.

J'ai donc ajouté une recherche par **forme** : les variables deviennent `V` et
les fonctions du projet `F` avant comparaison. Sur 6 paires
« énoncé → lemme analogue » que j'ai annotées, la recherche par forme retrouve
le bon lemme dans ses 3 premiers résultats 6 fois sur 6, contre 5 fois sur 6
par les mots. **L'échantillon est minuscule et annoté par moi** : c'est une
piste, pas une conclusion. Les deux méthodes restent disponibles
(`--retriever shape|lexical`) pour les comparer sur les preuves réelles.

## Lancer le projet

```bash
sudo apt install coq            # Rocq/Coq 8.18 (Ubuntu 24.04)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python -m pytest -q             # 50 tests

# Référence sans LLM (aucune clé)
python scripts/evaluate.py --provider baseline --configs zero-shot,feedback

# Avec un LLM : copier .env.example en .env et renseigner la clé
python scripts/evaluate.py --provider groq
python scripts/evaluate.py --provider groq --suite memory_isolation --configs retrieval+feedback

# Quota épuisé ? Le script s'arrête proprement ; reprendre plus tard :
python scripts/evaluate.py --provider groq --resume results/groq_AAAAMMJJ-HHMMSS.json
```

**Économiser le quota gratuit :** dans `.env`, `GROQ_REASONING_EFFORT=low`
réduit fortement les tokens « de réflexion » de gpt-oss (à indiquer dans les
résultats, car cela change le modèle évalué). Les quotas Groq sont **par
modèle** : un autre modèle (ex. `--model qwen/qwen3.8-27b`) dispose de son
propre quota, et permet en plus une comparaison entre modèles.

## Limites assumées

- **Petit benchmark** (21 théorèmes, écrits pour le projet) : il sert à comparer
  des configurations entre elles, pas à se mesurer aux benchmarks publics
  (CoqStoq : ~197 000 théorèmes ; IMM-300 pour RocqStar).
- **Preuve entière, pas pas-à-pas** : le LLM propose la preuve complète, puis
  la corrige. Les agents de l'état de l'art interagissent tactique par
  tactique (via coq-lsp / pytanque). C'est l'extension naturelle suivante.
- **Corpus d'exemples volontairement proche** : certains lemmes du corpus ont la
  même forme que des théorèmes du benchmark, sur d'autres définitions. C'est le
  principe de la recherche d'exemples (Rango), mais cela peut surestimer son
  apport par rapport à un vrai projet, où l'analogue n'existe pas toujours.
- **Modèle mémoire jouet** : une liste d'entiers, loin de la mémoire d'un vrai
  programme. Les propriétés prouvées ont la forme de vraies propriétés
  d'isolation, pas leur complexité.
- Rocq 8.18 (paquet Ubuntu). Le langage est le même que Rocq 9.x ; seuls les
  chemins d'import (`From Coq` → `From Stdlib`) changeraient.

## Références

- Khramov, Kozyrev, Solovev, Podkopaev — *RocqStar: Leveraging Similarity-driven
  Retrieval and Agentic Systems for Rocq generation*, JetBrains Research,
  arXiv:2505.22846, 2025.
- Thompson et al. — *Rango: Adaptive Retrieval-Augmented Proving for Automated
  Software Verification*, arXiv:2412.14063, 2024.
- First, Rabe, Ringer, Brun — *Baldur: Whole-Proof Generation and Repair with
  Large Language Models*, ESEC/FSE 2023 (sur Isabelle/HOL).
- Pierce et al. — *Software Foundations, vol. 1 : Logical Foundations*.
