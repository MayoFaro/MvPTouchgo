# Touch-Go News — Sprint 5 (Revue humaine) — Design

Statut : validé par l'utilisateur en conversation, prêt pour plan d'implémentation.

Référence fonctionnelle complète : [`SPEC.md`](../../../SPEC.md) (sections 12, 13, 16, 17, 20, 21).
Référence architecturale : [Sprint 4 — design](2026-09-21-touchgo-news-sprint4-scoring-design.md),
qui identifiait déjà ce sprint dans sa section « Hors scope » (« Interface admin consommant
priority/scores pour filtrer/afficher »).

## 1. Contexte et portée

Après le Sprint 4, chaque item classé porte quatre scores et une `priority` A/B/C, mais rien
n'expose encore ce travail à un humain, et aucune décision humaine n'est jamais enregistrée. Le
modèle de données prévu section 16 du spec est pourtant déjà entièrement en place depuis le schéma
initial du Sprint 1 : `NewsItem.human_decision/human_reason/human_comment/reviewed_at/reviewer_id`
et la table `NewsFeedback` existent, inutilisés jusqu'ici. Ce sprint couvre :

- deux endpoints API : soumission d'un feedback humain, et liste des items filtrable (priorité,
  catégorie, période) ;
- une page web minimale servie par FastAPI (filtres, cartes de news, boutons d'action) reproduisant
  section 20-21 du spec.

Explicitement **hors scope** (voir section 9) : boucle d'apprentissage adaptative à partir du
feedback (section 18, déjà identifiée comme Sprint 6 dans le design du Sprint 4), authentification,
statuts de vérification calculés automatiquement (`verification_status` est exposé en lecture mais
jamais écrit par ce sprint).

## 2. Reviewer et absence d'authentification

Un seul reviewer humain existe pour ce MVP — pas d'authentification, pas de saisie de nom côté
client. `Settings.default_reviewer_id: str` (nouveau champ config, `.env`) fournit la valeur
utilisée par défaut. `POST /items/{id}/feedback` accepte un `reviewer_id` optionnel dans son corps ;
si absent, le service utilise `get_settings().default_reviewer_id`. Le frontend n'envoie jamais ce
champ.

## 3. Endpoint de feedback

`POST /items/{id}/feedback`

```text
FeedbackIn:
  decision: "TRES_INTERESSANT" | "INTERESSANT" | "A_SUIVRE" | "REJETER" | "NOUVELLE_CATEGORIE"
  reason: str | None        # requis, et validé contre la liste fermée ci-dessous, ssi decision == REJETER
  comment: str | None       # requis ssi decision == NOUVELLE_CATEGORIE ; libre sinon
  reviewer_id: str | None   # optionnel, voir section 2
```

Mapping avec les actions rapides de la section 17 du spec :

```text
🔥  TRES_INTERESSANT
👍  INTERESSANT
👀  A_SUIVRE
❌  REJETER            (reason obligatoire)
➕  NOUVELLE_CATEGORIE  (comment obligatoire — décrit la catégorie suggérée)
```

Liste fermée de `reason` (section 17, uniquement quand `decision == REJETER`) : `trop_mineur`,
`pas_pertinent_touchgo`, `trop_commercial`, `trop_local`, `signal_trop_faible`, `doublon`,
`information_douteuse`, `hors_perimetre`, `autre`. Un `reason` fourni avec une décision autre que
`REJETER` est ignoré silencieusement (jamais persisté) — seul `comment` est libre quelle que soit
la décision.

Comportement (`src/review/service.py`, fonction `submit_feedback`) :

1. 404 si l'item n'existe pas.
2. Validation Pydantic de la combinaison decision/reason/comment (422 si invalide) — avant toute
   écriture en base.
3. Met à jour `NewsItem.human_decision`, `human_reason`, `human_comment`, `reviewed_at` (horodatage
   serveur), `reviewer_id` — **dernier état**, écrasé à chaque nouveau feedback sur le même item, au
   même titre que `touchgo_interest` représente l'état courant côté scoring.
4. Insère une nouvelle ligne dans `NewsFeedback` (`decision`, `reason`, `comment`,
   `previous_priority`, `previous_category` — snapshot de l'état de l'item *avant* l'écriture de
   l'étape 3 —, `reviewer_id`, `created_at`) : **historique complet, jamais écrasé**. Un reviewer
   peut changer d'avis sur un item déjà traité sans perdre la trace de ses décisions précédentes.
5. Réponse 200 : `NewsItemOut` mis à jour (pour que le frontend rafraîchisse la carte sans recharger
   la page).

## 4. Endpoint de liste et mapping des vues

`GET /items` gagne des query params optionnels, tous combinables :

```text
priority: "A" | "B" | "C"
category: une des 7 catégories éditoriales (section 4 du spec)
since:    "24h" | "3d" | "7d"     → filtre sur detected_at >= now - delta
view:     "a_voir" | "a_surveiller" | "faible_priorite"
```

Les trois vues fonctionnelles (section 21 du spec) sont un pur sucre syntaxique sur `priority`,
pas un mécanisme de filtrage séparé — le signal de fiabilité de source (« forums, rumeurs »,
mentionné section 21) est déjà absorbé par le LLM de scoring dans le calcul de `priority`
(section 7, Sprint 4) ; dupliquer ce critère dans la logique de vue recréerait la même décision
à deux endroits.

```text
view=a_voir            ⇔  priority=A   (« Contenus les plus intéressants »)
view=a_surveiller       ⇔  priority=B   (« Signaux faibles [...] sujets en développement »)
view=faible_priorite    ⇔  priority=C   (« Probablement faibles mais conservés »)
```

Si `view` et `priority` sont fournis simultanément, `priority` (explicite) l'emporte — `view` est
alors ignoré sur ce facet, pas d'erreur de conflit.

Un item dont `priority IS NULL` (pas encore scoré, ou scoring en échec permanent) n'apparaît dans
aucune des trois vues — comportement voulu : un item non encore scoré n'est pas encore triable, il
ne doit pas apparaître prématurément dans une vue avant que le Sprint 4 ait fait son travail. Il
reste néanmoins consultable via `GET /items` sans filtre de vue.

## 5. Champs exposés

`NewsItemOut` gagne : `verification_status` (déjà en base depuis le Sprint 1, jamais exposé),
`human_decision`, `human_reason`, `human_comment`, `reviewed_at`, `reviewer_id`. Ces cinq derniers
permettent au frontend de distinguer un item déjà traité d'un item encore à examiner.

## 6. Frontend

Servi par FastAPI lui-même — pas de build step, pas de stack JS à maintenir, même process de
déploiement que le reste de l'API.

- `GET /` (nouvelle route dans `src/api/main.py`) rend `templates/review.html` (Jinja2) :
  - barre de filtres (section 20 du spec) : priorité (Toutes/A/B/C), catégorie (7 + Toutes),
    période (24h/3j/7j) — chaque changement recharge la page via un nouveau query string, pas
    d'état client ;
  - trois onglets de vue (À voir / À surveiller / Faible priorité) en raccourci vers
    `?view=...` ;
  - une carte par item (section 20 du spec) : badges priorité/catégorie, horodatage relatif,
    titre, source/langue, les quatre scores, statut de vérification, cinq boutons d'action
    (🔥 👍 👀 ❌ ➕).
- `static/review.js` (vanilla, aucune dépendance) : gère uniquement les actions de feedback.
  Clic sur 🔥/👍/👀/➕ envoie directement `POST /items/{id}/feedback`. Clic sur ❌ affiche
  d'abord un `<select>` inline avec la liste de raisons avant l'envoi. Succès (200) : met à jour
  la carte en place. Échec (404/422/500) : message d'erreur inline sur la carte, sans casser le
  reste de la page.

## 7. Configuration

Nouveau champ dans `Settings` (`src/config.py`) : `default_reviewer_id: str` (voir section 2).
Aucune migration de schéma : toutes les colonnes utilisées par ce sprint (`human_*`,
`verification_status`, table `NewsFeedback`) existent déjà depuis le schéma initial du Sprint 1.

## 8. Tests

Backend : tests unitaires sur `submit_feedback` (mise à jour `NewsItem`, insertion `NewsFeedback`,
snapshot correct de `previous_priority`/`previous_category`, rejet des combinaisons
decision/reason/comment invalides) ; tests d'intégration sur les deux endpoints (`TestClient`, DB
réelle de test, même pattern que `tests/api/test_items.py`) ; tests du mapping `view` → `priority`
et de la combinaison de plusieurs filtres ; test qu'un item `priority IS NULL` n'apparaît dans
aucune vue. Aucun appel réseau réel nécessaire (pas de LLM impliqué dans ce sprint).

Frontend : pas de framework de test JS pour un script aussi minimal — vérification manuelle
documentée dans le plan d'implémentation (golden path : filtrer par chaque facet, cliquer chaque
bouton d'action y compris ❌ avec choix de raison, vérifier la mise à jour de la carte en place).

## 9. Hors scope Sprint 5

Boucle d'apprentissage adaptative à partir du feedback humain (section 18, Sprint 6 — ce sprint se
limite à *capturer* le feedback, jamais à l'utiliser pour ajuster classification/scoring/prompts) ;
authentification (reviewer unique, section 2) ; calcul automatique de `verification_status`
(section 13 — exposé en lecture, jamais écrit par ce sprint) ; échantillonnage périodique des faux
négatifs (section 19 — la vue « Faible priorité » rend les items C consultables et corrigibles via
le feedback existant, mais aucun mécanisme d'échantillonnage dédié n'est construit) ; regroupement
en événements (`NewsEvent`, section 22, non assigné à un sprint explicite) ; extraction d'entités
(`country`/`region`/`entities`, idem).
