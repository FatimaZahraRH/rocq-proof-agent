# Rocq Proof Agent

**Un LLM propose des preuves formelles, Rocq les vérifie, l'erreur revient au LLM.**
Reproduction et évaluation, à petite échelle, d'approches récentes d'assistance
à la vérification formelle par IA, appliquées à des propriétés de **sécurité
mémoire** (accès hors bornes, isolation entre zones mémoire).

> **État actuel.** Le benchmark, le vérificateur, l'agent et l'évaluation sont
> fonctionnels et testés (45 tests). Le seul résultat mesuré à ce jour est la
> **référence sans LLM** (tableau ci-dessous). Les résultats avec un vrai LLM
> s'ajoutent en lançant `scripts/evaluate.py --provider groq`.

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

### Avec un LLM

*À compléter* : `python scripts/evaluate.py --provider groq` produit le tableau
des 4 configurations (zero-shot, feedback, retrieval, retrieval+feedback) dans
`results/`.

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
python -m pytest -q             # 45 tests

# Référence sans LLM (aucune clé)
python scripts/evaluate.py --provider baseline --configs zero-shot,feedback

# Avec un LLM : copier .env.example en .env et renseigner la clé
python scripts/evaluate.py --provider groq
python scripts/evaluate.py --provider groq --suite memory_isolation --configs retrieval+feedback
```

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
