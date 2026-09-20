# Touch-Go News — Sprint 1 (Collecte) — Design

Statut : validé par l'utilisateur en conversation, prêt pour plan d'implémentation.

Référence fonctionnelle complète : [`TouchGo-News-SPEC.md`](../../../TouchGo-News-SPEC.md) (sections 25-27, 34).

## 1. Contexte et portée

`MvPTouchgo` est un repo neuf et dédié au service `touchgo-news` décrit dans le spec — aucun autre
codebase Touch-Go n'existe dans ce dépôt. Ce document couvre uniquement le **Sprint 1** tel que
défini section 34 du spec : mettre en place le repo, la configuration des sources, la base de
données, les premiers collecteurs, et le stockage brut. Les sprints suivants (normalisation,
classification, scoring, interface admin, boucle adaptative, événements) feront chacun l'objet
de leur propre cycle brainstorming → design → plan.

Hébergement : machine locale / dev pour l'instant, pas de cible de déploiement figée. Le design
reste néanmoins portable (Docker Compose) pour ne pas fermer d'options.

## 2. Architecture et stack

Repo structuré à la racine (pas de sous-dossier `touchgo-news/` intermédiaire, puisque le repo lui
est entièrement dédié) :

```
MvPTouchgo/
├── SPEC.md                    (renommé depuis TouchGo-News-SPEC.md)
├── README.md
├── .env.example
├── pyproject.toml
├── docker-compose.yml         (Postgres)
├── alembic/
├── config/
│   └── sources.yaml
├── src/
│   ├── collectors/
│   ├── db/
│   └── api/
├── tests/
└── data/
```

Stack (conforme section 26 du spec) : Python 3.12+, FastAPI, SQLAlchemy, Pydantic, httpx,
feedparser, BeautifulSoup, PostgreSQL via Docker Compose, APScheduler intégré au process FastAPI.

## 3. Modèle de données

Les tables `NEWS_SOURCE`, `NEWS_ITEM`, `NEWS_EVENT`, `NEWS_FEEDBACK` sont créées dans leur forme
finale (schéma complet, section 16 du spec) via une première migration Alembic, plutôt que par
ajouts incrémentaux sprint par sprint — le schéma cible est déjà entièrement spécifié, donc autant
éviter des migrations structurantes répétées.

Au Sprint 1, seules les colonnes de stockage brut de `NEWS_ITEM` sont réellement remplies :
`source_id`, `source_item_id`, `canonical_url`, `original_url`, `original_title`, `original_text`,
`language`, `author`, `published_at`, `detected_at`, `status` (= `NEW`). Les colonnes de
classification, scoring, priorité, vérification restent `NULL` jusqu'aux sprints correspondants,
conformément au principe de séparation collecte/classification (section 30).

`NEWS_EVENT` et `NEWS_FEEDBACK` sont créées vides, utilisées à partir des sprints 6-7.

Unicité minimale au Sprint 1 : `(source_id, source_item_id)` pour éviter les doublons triviaux
produits par des exécutions répétées du scheduler sur la même source. La déduplication sémantique
complète est hors scope (Sprint 2, section 29).

## 4. Collecteurs

Interface commune (section 27 du spec) :

```python
class Collector:
    source_id: str
    async def fetch(self) -> list[RawItem]: ...
```

Deux implémentations au Sprint 1 :

- **`RSSCollector`** générique, piloté par `config/sources.yaml` (URL du flux, langue, type de
  source) — couvre la majorité du pool initial.
- **`ForumThreadCollector`** (PPRuNe uniquement) — prototype du modèle *thread* de la section 10 :
  détection de nouveaux threads / reprise d'activité, pas un scraping message par message. Les
  autres forums (Aeronet, Secret Projects...) suivront aux sprints ultérieurs une fois ce modèle
  validé.

Priorité de collecte conforme section 27 : RSS > API publique > HTML statique > scraping >
navigateur automatisé (non utilisé au Sprint 1).

### Sources initiales (8-10, section 34)

| Source | Type prévu | Collecteur |
|---|---|---|
| FlightGlobal | RSS | RSSCollector |
| Airbus (newsroom) | RSS à confirmer | RSSCollector |
| BEA | RSS | RSSCollector |
| EASA | RSS | RSSCollector |
| Opex360 | RSS (WordPress) | RSSCollector |
| Aviation Herald | RSS | RSSCollector |
| PPRuNe (Military Aviation, Rumours & News) | forum | ForumThreadCollector |
| Aeronet | RSS à confirmer | RSSCollector |
| BMPD (Russie) | RSS (LiveJournal) | RSSCollector |
| Source chinoise (AVIC / Xinhua à confirmer) | RSS à confirmer | RSSCollector |

La disponibilité réelle des flux RSS pour certaines sources (Airbus, Aeronet, source chinoise)
sera vérifiée pendant l'implémentation ; un fallback scraping HTML statique est prévu si
nécessaire, sans changer l'interface `Collector`.

## 5. Ordonnancement

APScheduler intégré au process FastAPI, un job par source, intervalle configurable par source
dans `sources.yaml` (un flux RSS peut être interrogé plus fréquemment qu'un forum).

## 6. Robustesse

Chaque collecteur est isolé : un échec sur une source (timeout, HTML cassé, flux indisponible)
est loggé et n'interrompt pas les autres collecteurs. Pas de retry sophistiqué au Sprint 1 ; le
statut de la dernière exécution est visible sur `NEWS_SOURCE` (ex. `last_run_status`,
`last_run_at`).

## 7. API

Surface minimale au Sprint 1 : `GET /health`, et `GET /items` (lecture brute, pour vérifier
visuellement ce qui a été collecté). Pas d'interface admin avant le Sprint 5.

## 8. Tests

- Tests unitaires par collecteur, avec mock des réponses HTTP/RSS.
- Test d'intégration du pipeline collecte → stockage, sur une base Postgres de test (conteneur
  dédié ou éphémère).

## 9. Hors scope Sprint 1

Normalisation avancée, déduplication sémantique, classification, scoring, interface admin,
feedback humain, apprentissage adaptatif, regroupement d'événements — tous prévus aux sprints
suivants (2 à 7, section 34 du spec). Aucune publication, automatique ou manuelle, n'est jamais
dans le scope de ce service (principe absolu, section 1 du spec).
