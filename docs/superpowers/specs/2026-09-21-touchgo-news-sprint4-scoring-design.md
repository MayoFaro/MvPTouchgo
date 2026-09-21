# Touch-Go News — Sprint 4 (Scoring) — Design

Statut : validé par l'utilisateur en conversation, prêt pour plan d'implémentation.

Référence fonctionnelle complète : [`SPEC.md`](../../../SPEC.md) (sections 7, 11, 12, 30, 31, 34).
Référence architecturale : [Sprint 3 — design](2026-09-21-touchgo-news-sprint3-classification-design.md)
et son implémentation (`src/classification/`), déjà mergée sur `main` — ce sprint en reproduit
délibérément l'architecture, y compris les corrections apportées après revue (client LLM partagé
par batch, isolation de la comptabilité d'échec, cap de tentatives).

## 1. Contexte et portée

Après le Sprint 3, chaque item classé a une `primary_category` mais `touchgo_interest`,
`event_importance`, `source_confidence`, `urgency` et `priority` restent `NULL` pour tout le monde
— ces cinq colonnes existent sur `NewsItem` depuis le schéma initial du Sprint 1, inutilisées
jusqu'ici. Ce document couvre le **Sprint 4** tel que défini section 34 du spec : attribuer quatre
scores indépendants (section 11) et en dériver une priorité A/B/C (section 12). Aucune suppression
de contenu, quelle que soit la priorité — section 12.

## 2. Où et comment ça s'exécute

Un nouveau job APScheduler, découplé de la classification, tourne à intervalle configurable
(défaut : toutes les 3 minutes). À chaque passage, `score_pending_items` sélectionne jusqu'à
`scoring_batch_size` items (défaut : 20) où `primary_category IS NOT NULL AND touchgo_interest IS
NULL`, les score un par un via l'API Claude, et met à jour chaque ligne en place.

Ce découplage suit le pipeline explicite de la section 30 (`collector → raw item → normalized item
→ classifier → scorer`) et sa justification section 31 : pouvoir recalculer les scores sans
reclasser (par exemple si le prompt de scoring est amélioré plus tard, sans vouloir retoucher
`primary_category` sur tout l'historique). Un item non encore classé (`primary_category IS NULL`)
n'est jamais sélectionné par ce job — le scoring dépend d'une classification réussie au préalable.
Un item classé `DIVERS` est scoré comme tout autre item, sans traitement spécial.

## 3. Client LLM

`score_item(title: str, text: str, source_type: str) -> ScoringResult` est la seule interface que
le job de scoring connaît, sur le modèle de `classify_item` du Sprint 3. Même modèle (Claude Haiku
4.5), même authentification (`ANTHROPIC_API_KEY`).

Différence notable avec le client de classification : `score_item` reçoit en plus `source_type`
(la famille de la source — `official`/`press`/`media`/`community`, déjà stockée sur `NewsSource`)
pour que le LLM dispose du contexte nécessaire à juger `source_confidence` (voir section 5).

## 4. Sortie structurée

Utilisation du *tool use* de l'API Claude, comme au Sprint 3 :

```text
touchgo_interest:     entier 0 à 10
event_importance:     entier 0 à 10
source_confidence:    entier 0 à 10
urgency:              entier 0 à 10
priority:             enum A / B / C
reasoning:            texte court expliquant les scores
```

`priority` est une sortie directe du LLM plutôt qu'une formule calculée en code à partir des
quatre scores : la section 7 donne un exemple où une fiabilité de 3/10 ne doit *jamais* faire
redescendre un item à fort intérêt (touchgo_interest 10/10, event_importance 9/10) — un jugement
contextuel que le modèle peut porter, mais qu'une formule à seuils fixes figerait sans données
réelles pour la calibrer.

`reasoning` est stocké dans `model_metadata["scoring_reasoning"]` — pas dans `NewsItem.model_reason`,
qui reste la trace de la classification du Sprint 3 uniquement. Cette séparation évite toute
ambiguïté de format (pas de concaténation à définir) et tout risque de croissance non bornée si un
item est un jour rescoré (§31) : `scoring_reasoning` est simplement remplacé, pas accumulé, au même
titre que `scoring_errors` vit déjà dans `model_metadata` séparément de `classification_errors`.

## 5. Contenu du prompt

Le prompt encode :

- les quatre dimensions et leur échelle 0–10 (section 11), avec la consigne de ne jamais utiliser
  un score unique et de toujours les traiter indépendamment ;
- la règle de la section 7 : une fiabilité de source faible ne doit jamais éclipser un intérêt ou
  une importance réels — illustrée par l'exemple concret du spec (post PPRuNe, communautaire :
  importance 9, intérêt 10, fiabilité 3, priorité A malgré la fiabilité faible) ;
- le `source_type` de l'item comme signal de fiabilité de base (officiel > presse > média >
  communautaire), que le LLM pondère avec le contenu spécifique de l'item plutôt que d'appliquer
  une règle rigide ;
- les critères de priorité A/B/C de la section 12 (A = forte probabilité d'intérêt, B = à
  examiner, C = intérêt probablement faible mais conservé), en rappelant qu'aucune priorité
  n'entraîne de suppression et que tout reste consultable.

Même délimitation anti-injection que le Sprint 3 (contenu de l'item entre balises `<article>`,
consigne explicite de ne jamais le traiter comme une instruction) et même troncature à 4000
caractères.

## 6. Gestion d'erreur et retries

Reprend le pattern du Sprint 3, y compris les corrections apportées après la revue finale de ce
sprint (déjà en production sur `main`) :

- un seul client `AsyncAnthropic` construit par batch (jamais un par item), sauté entièrement si
  le batch est vide ;
- isolation d'erreur par item : `except Exception` large + `session.rollback()`, un item en échec
  n'interrompt jamais les autres dans le même passage ;
- compteur `scoring_attempts` (nouvelle colonne, miroir de `classification_attempts`), plafonné à
  `scoring_max_attempts` (défaut 5) — un item ayant épuisé ses tentatives sort silencieusement de
  la sélection future, sans jamais recevoir de score forcé ;
- journal des raisons d'échec dans `model_metadata["scoring_errors"]` (même colonne JSON que la
  classification, clé distincte de `classification_errors` pour ne pas l'écraser) ;
- la comptabilité d'échec (incrément + journal + commit) est elle-même protégée par son propre
  `try/except` avec rollback — une panne DB pendant l'enregistrement de l'échec ne doit pas, elle
  non plus, interrompre le reste du batch ;
- log d'avertissement quand un item atteint `scoring_max_attempts`.

Si les tentatives échouent, l'item reste sans score et sera retenté au prochain passage jusqu'au
plafond. Aucune valeur par défaut forcée.

## 7. Configuration

Nouveaux champs dans `Settings` (`src/config.py`) : `scoring_batch_size: int = 20`,
`scoring_interval_minutes: int = 3`, `scoring_max_attempts: int = 5`. Une seule migration de
schéma nécessaire : ajout de `scoring_attempts` (Integer, défaut 0, `NOT NULL`) sur `NewsItem` —
`touchgo_interest`, `event_importance`, `source_confidence`, `urgency` et `priority` existent déjà
depuis le Sprint 1.

Nouveaux champs exposés en lecture seule via `GET /items` (`NewsItemOut`) : `touchgo_interest`,
`event_importance`, `source_confidence`, `urgency`, `priority`.

## 8. Tests

Le client LLM est mocké dans tous les tests (aucun appel réseau réel), même pattern que le Sprint
3. Couverture : parsing de la réponse structurée, rejet d'une priorité invalide éventuellement
renvoyée par le LLM, sélection des items classés-mais-non-scorés par le job, isolation d'erreur par
item (y compris une erreur non liée au LLM, comme un échec de `session.commit()`), retries sur
erreur transitoire, exclusion d'un item ayant atteint `scoring_max_attempts` (testée de bout en
bout : plusieurs échecs réels puis vérification que l'item n'est plus jamais soumis), et
préservation des clés existantes de `model_metadata` (notamment `classification_errors` du Sprint
3, qui ne doit jamais être écrasé par un écrit ultérieur de `scoring_errors`).

Test d'intégration bout-en-bout : collecte → classification → scoring → visibilité via l'API.

## 9. Hors scope Sprint 4

Interface admin consommant `priority`/scores pour filtrer/afficher (Sprint 5), boucle
d'apprentissage adaptative à partir du feedback humain (Sprint 6), regroupement en événements
(Sprint 7), extraction d'entités (`country`/`region`/`entities` — mentionnée dans le pipeline
section 22 mais non assignée à un sprint explicite du plan section 34), statuts de vérification
(section 13, hors périmètre du Sprint 4).
