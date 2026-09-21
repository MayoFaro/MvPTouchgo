# Touch-Go News — Sprint 2 (Normalisation & déduplication) — Design

Statut : validé par l'utilisateur en conversation, prêt pour plan d'implémentation.

Référence fonctionnelle complète : [`SPEC.md`](../../../SPEC.md) (sections 28, 29, 30, 34).
Référence architecturale : [Sprint 1 — design](2026-09-20-touchgo-news-sprint1-collecte-design.md)
et son implémentation (`src/collectors/`, `src/db/`), déjà mergée sur `main`.

## 1. Contexte et portée

Le Sprint 1 stocke les items bruts tels que collectés : `canonical_url` est une copie de
`original_url`, aucun hash n'est calculé, et la seule protection anti-doublon est l'unicité
`(source_id, source_item_id)` (protège contre les ré-exécutions du scheduler sur la même source,
pas contre deux sources différentes rapportant le même événement).

Ce document couvre le **Sprint 2** tel que défini section 34 du spec : URL canonique réelle,
dates, langue, hash de contenu, et déduplication basique (section 29). La régression sémantique
avancée (embeddings, regroupement en `NEWS_EVENT`) reste hors scope — c'est l'« étape suivante »
explicitement mentionnée section 29, et le regroupement en événements est le Sprint 7.

## 2. Où ça s'exécute

Synchrone, dans le chemin d'insertion existant (`save_raw_items` dans `src/db/repository.py`) :
pour chaque `RawItem` sur le point d'être inséré, on calcule sa normalisation et on cherche un
doublon parmi les `NewsItem` déjà en base, avant de committer la ligne. Pas de nouveau type de job
planifié : la comparaison porte déjà sur toute la table, donc la détection cross-source (un même
événement rapporté par Airbus puis par Reuters, dans des runs de collecte différents) fonctionne
sans étape séparée. Cette approche a été retenue plutôt qu'une passe planifiée séparée pour rester
simple et ne pas introduire un nouvel état « normalisé / pas encore normalisé » à gérer au Sprint 2.

## 3. Modèle de données

Une colonne manque au schéma créé au Sprint 1 (anticipé par la revue finale de ce sprint) :

```text
NewsItem.content_hash: str | None   -- hash du texte normalisé (titre + corps)
```

`duplicate_of` existe déjà depuis le Sprint 1 et sert exactement à ça. Une migration Alembic
ajoute uniquement cette colonne, nullable, sans toucher aux données existantes.

**Pas de backfill** : les items déjà collectés au Sprint 1 gardent `canonical_url = original_url`
et `content_hash = NULL`. Seuls les nouveaux items collectés à partir du Sprint 2 sont normalisés
et dédupliqués. Un backfill est un choix délibérément écarté pour ce sprint — cohérent avec le
principe de ne jamais modifier rétroactivement des données déjà en base sans que ce soit un besoin
explicite, et ça évite d'alourdir le sprint avec un script de migration de données.

## 4. Normalisation

Pour chaque item, avant insertion :

- **URL canonique** (`canonical_url`) : force le schéma en `https`, met le host en minuscules,
  retire les paramètres de tracking connus (`utm_source`, `utm_medium`, `utm_campaign`, `utm_term`,
  `utm_content`, `fbclid`, `gclid`, `mc_cid`, `mc_eid`), retire le fragment (`#...`), retire un `/`
  final superflu sur le path.
- **Titre normalisé** (calcul interne, non stocké tel quel) : minuscules, ponctuation retirée,
  espaces multiples réduits à un seul. Sert de base au hash et à la comparaison par tokens.
- **`content_hash`** : SHA-256 (tronqué à 32 caractères hex) du titre normalisé concaténé au texte
  normalisé (même normalisation minuscule/ponctuation appliquée au texte).

## 5. Détection de doublon

Au moment d'insérer un nouvel item, recherche d'un `NewsItem` existant qui matche, dans cet ordre
(premier match gagne, pas de cumul de critères) :

1. `canonical_url` identique.
2. `content_hash` identique.
3. Recouvrement de tokens du titre normalisé ≥ 0.8 (indice de Jaccard sur l'ensemble des mots) **et**
   `published_at` (ou `detected_at` si `published_at` est absent) à moins de 48h l'un de l'autre.

Ces seuils (48h, 0.8) sont un point de départ délibérément strict pour démarrer avec un minimum de
faux positifs, ajustables plus tard si des doublons réels sont manqués en pratique — cohérent avec
la philosophie recall-first du MVP (mieux vaut manquer un doublon que fusionner à tort deux news
différentes).

## 6. Comportement en cas de match

Conforme au principe absolu « ne jamais rien supprimer automatiquement » (SPEC.md section 2) :
l'item est **toujours inséré**, jamais rejeté ni fusionné. Si un match est trouvé, son
`duplicate_of` est renseigné avec l'id du `NewsItem` correspondant le plus ancien du groupe
(première occurrence détectée = référence). `status`, `primary_category` et tous les champs de
classification/scoring restent inchangés — un item marqué doublon reste pleinement visible et
consultable via `GET /items`, conformément au principe de ne jamais rendre un contenu invisible.

## 7. Tests

- Tests unitaires pour la canonicalisation d'URL (cas simples, cas avec paramètres de tracking,
  casse, slash final) et pour le calcul du hash.
- Un test par critère de match (URL identique, hash identique, similarité + fenêtre de date) et un
  test confirmant qu'un item hors fenêtre de 48h ou sous le seuil de similarité n'est **pas**
  marqué doublon.
- Extension du test d'intégration du Sprint 1 : deux items quasi identiques provenant de sources
  différentes, insérés dans le même run de test, où le second obtient bien `duplicate_of` pointant
  vers le premier.

## 8. Hors scope Sprint 2

Regroupement sémantique par embeddings, notion d'`NEWS_EVENT` (Sprint 7), backfill des items
Sprint 1, ajustement dynamique des seuils de similarité, classification et scoring (Sprint 3-4).
