# Touch-Go News — Sprint 3 (Classification) — Design

Statut : validé par l'utilisateur en conversation, prêt pour plan d'implémentation.

Référence fonctionnelle complète : [`SPEC.md`](../../../SPEC.md) (sections 4, 5, 6, 18, 30, 34).
Référence architecturale : [Sprint 1 — design](2026-09-20-touchgo-news-sprint1-collecte-design.md),
[Sprint 2 — design](2026-09-21-touchgo-news-sprint2-normalisation-dedup-design.md), et leur
implémentation (`src/collectors/`, `src/db/`, `src/normalization/`), déjà mergées sur `main`.

## 1. Contexte et portée

Après le Sprint 2, chaque item stocké a une URL canonique, un hash de contenu, et un éventuel lien
de doublon — mais `primary_category`, `secondary_categories` et `classification_confidence`
restent `NULL` pour tout le monde. Ce document couvre le **Sprint 3** tel que défini section 34 du
spec : assigner les sept catégories éditoriales (section 4), gérer la catégorie de sécurité
`DIVERS` (section 5), les catégories secondaires, et un score de confiance. Le scoring
multi-dimensionnel (intérêt Touch-Go, importance, urgence, priorité A/B/C — section 11) est
explicitement le Sprint 4, hors scope ici.

## 2. Où et comment ça s'exécute

Un nouveau job APScheduler, découplé de la collecte, tourne à intervalle configurable (défaut :
toutes les 3 minutes). À chaque passage, `classify_pending_items` sélectionne jusqu'à
`classification_batch_size` items (défaut : 20) où `primary_category IS NULL`, les classe un par
un via l'API Claude, et met à jour chaque ligne en place. Ce découplage respecte explicitement le
principe de séparation collecte/classification (SPEC.md section 30) : un appel LLM lent ou en
erreur ne peut jamais ralentir ou bloquer un cycle de collecte, et permet de recalculer la
classification plus tard sans recollecter (section 31).

## 3. Client LLM

`classify_item(title: str, text: str) -> ClassificationResult` est la seule interface que le job de
classification connaît — l'implémentation concrète (API Claude aujourd'hui) est un détail
substituable. Ce sprint utilise l'API Anthropic, modèle Claude Haiku 4.5, choisi pour son faible
coût à volume potentiellement élevé (6 sources × polling fréquent). Une bascule future vers un LLM
local (ex. Ollama) resterait un changement contenu à ce seul module, sans toucher au job de
classification, au prompt, ni au reste du pipeline — décision explicitement reportée après ce
sprint (blocage matériel actuel : conflit entre deux versions du driver NVIDIA sur la machine de
développement, non résolu à ce jour).

Authentification via `ANTHROPIC_API_KEY`, lu depuis l'environnement (`.env`), jamais commité.

## 4. Sortie structurée

Utilisation du *tool use* de l'API Claude pour forcer une réponse structurée :

```text
primary_category: enum des 7 valeurs (COMMERCIAL, EMPLOI, MILITAIRE, REGLEMENTATION, MEETING,
                   ACCIDENT_INCIDENT, DIVERS)
secondary_categories: liste (0 ou plus) du même enum
classification_confidence: float, 0.0 à 1.0
reasoning: texte court expliquant le choix
```

`reasoning` est stocké dans `NewsItem.model_reason` (colonne existante depuis le Sprint 1) pour
audit humain a posteriori.

## 5. Contenu du prompt

Le prompt encode :

- les sept catégories et leurs critères détaillés (sections 6.1 à 6.7 du spec) : filtrage strict
  pour Commercial et Réglementation, surveillance large pour Emploi, couverture mondiale et large
  pour Militaire, seuil dépendant de la zone géographique pour Accidents/Incidents ;
- la règle absolue de la section 5 : si aucune catégorie ne convient clairement, `DIVERS` — jamais
  de rejet, jamais d'absence de catégorie faute de correspondance ;
- qu'une catégorie secondaire est possible (ex. un accident militaire reçoit `ACCIDENT_INCIDENT` en
  primaire et `MILITAIRE` en secondaire, ou l'inverse selon le contenu — section 6.7).

## 6. Gestion d'erreur et retries

Par item, jusqu'à 2 tentatives en cas d'erreur transitoire (timeout, erreur 5xx), avec un court
backoff. Isolation d'erreur par item dans le job — comme le runner de collecte du Sprint 1 : un
item en échec n'empêche jamais les autres d'être classés dans le même passage. Si les tentatives
échouent, l'item reste `primary_category = NULL` et sera retenté automatiquement au prochain
passage du job. Aucune valeur par défaut forcée (pas de `DIVERS` automatique en cas d'échec
technique) — cohérent avec « aucune suppression/aucune perte de contenu » (section 2) et la
possibilité de recalcul (section 31). L'item reste visible via `GET /items` même sans catégorie.

## 7. Configuration

Nouveaux champs dans `Settings` (`src/config.py`) : `anthropic_api_key: str`,
`classification_batch_size: int = 20`, `classification_interval_minutes: int = 3`. Aucune
migration de schéma nécessaire — `primary_category`, `secondary_categories`,
`classification_confidence`, `model_reason` existent déjà (schéma complet créé au Sprint 1).

## 8. Tests

Le client LLM est mocké dans tous les tests (aucun appel réseau réel) — un stub renvoyant une
`ClassificationResult` fixe, injectable comme les collecteurs le sont déjà (pattern
`http_client` optionnel du Sprint 1). Tests unitaires pour : le parsing de la réponse structurée,
le repli sur une catégorie invalide éventuellement renvoyée par le LLM, la sélection des items
`NULL` par le job, l'isolation d'erreur par item, et les retries sur erreur transitoire.

## 9. Hors scope Sprint 3

Scoring multi-dimensionnel (intérêt, importance, urgence, priorité A/B/C — Sprint 4), apprentissage
adaptatif à partir du feedback humain (Sprint 6), regroupement en événements (Sprint 7), interface
admin (Sprint 5), bascule vers un LLM local (décision reportée, voir section 3).
