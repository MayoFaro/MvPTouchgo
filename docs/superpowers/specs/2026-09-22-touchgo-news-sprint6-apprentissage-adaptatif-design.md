# Touch-Go News — Sprint 6 (Apprentissage adaptatif) — Design

Statut : validé par l'utilisateur en conversation, prêt pour plan d'implémentation.

Référence fonctionnelle complète : [`SPEC.md`](../../../SPEC.md) (section 18, approche en 5 étapes
progressives — ce sprint couvre l'étape 3-4 : exemples historiques issus du feedback, ajustement
progressif du prompt).
Référence architecturale : [Sprint 5 — design](2026-09-22-touchgo-news-sprint5-revue-humaine-design.md)
(table `NewsFeedback` et champs `NewsItem.human_*`, désormais alimentés en production) et
[Sprint 4 — design](2026-09-21-touchgo-news-sprint4-scoring-design.md) (pattern client LLM +
job par batch que ce sprint réutilise).

## 1. Contexte et portée

Après le Sprint 5, chaque décision humaine (🔥/👍/👀/❌/➕) est capturée dans `NewsFeedback`, mais
rien n'exploite encore cet historique — les prompts de classification (Sprint 3) et de scoring
(Sprint 4) sont statiques, identiques à leur premier jour. Ce document couvre le Sprint 6 tel que
cadré en conversation : injecter les corrections humaines passées comme exemples few-shot dans ces
deux prompts, pour que le modèle apprenne progressivement des erreurs déjà signalées — sans
attendre un volume de données suffisant pour un classifieur dédié (étape 5 du §18, explicitement
hors périmètre).

Point de départ important, actant une contrainte réelle observée en conversation : au moment
d'écrire ce document, la base ne contient quasiment aucun feedback réel (aucune clé
`ANTHROPIC_API_KEY` n'était configurée pendant le développement des Sprints 1-5, donc la quasi
totalité des items collectés n'a jamais été classée ni scorée pour de vrai). Le mécanisme de ce
sprint doit donc se comporter proprement en l'absence de données : aucun exemple injecté, prompt
inchangé, jusqu'à ce que du feedback réel s'accumule en usage.

## 2. Contrainte du modèle de données existant

`NewsFeedback` (Sprint 5) ne capture **aucune valeur corrigée structurée** — pas de « la bonne
catégorie était X », pas de « le score aurait dû être Y ». Seulement une `decision` fermée
(🔥/👍/👀/❌/➕), une `reason` fermée pour ❌, un `comment` libre pour ➕, et un snapshot
`previous_priority`/`previous_category` de l'état du modèle au moment du feedback.

Décision actée : ce sprint n'étend **pas** ce modèle de données (pas de nouveau champ API/UI côté
Sprint 5). Il exploite les décisions existantes comme **signal directionnel faible** :

```text
Classification :
  NOUVELLE_CATEGORIE (➕)                    → catégorie du modèle probablement fausse
  REJETER (❌) avec reason = hors_perimetre  → catégorie du modèle probablement fausse

Scoring :
  TRES_INTERESSANT (🔥) / INTERESSANT (👍)   → priorité du modèle probablement sous-évaluée
  REJETER (❌), toute raison                 → priorité du modèle probablement surévaluée
  A_SUIVRE (👀)                              → exclu, signal trop neutre
```

Une même ligne `REJETER`/`hors_perimetre` peut alimenter les deux jeux d'exemples simultanément
(classification ET scoring) — les deux requêtes sont indépendantes sur la même table, ce n'est pas
un conflit, juste deux angles de lecture différents du même événement.

## 3. Sélection et format des exemples

Nouveau module `src/adaptive/` (miroir de `src/classification/`/`src/scoring/`), avec deux
fonctions pures, chacune interrogeant `NewsFeedback` (jointe à `NewsItem` pour le titre et à
`NewsFeedback.previous_category`/`previous_priority` pour le contexte modèle), triées par
`created_at` décroissant, limitées à `adaptive_max_examples` :

```python
def build_classification_examples(session: Session, limit: int) -> str: ...
def build_scoring_examples(session: Session, limit: int) -> str: ...
```

Format d'une ligne d'exemple :

```text
- Item classé COMMERCIAL par le modèle ; retour humain : hors périmètre Touch-Go.
- Item classé MEETING par le modèle ; retour humain : proposer une nouvelle catégorie ("Catégorie drones civils").
- Item priorité C donnée par le modèle ; retour humain : 🔥 (probablement sous-évalué).
- Item priorité A donnée par le modèle ; retour humain : ❌ rejeté (probablement surévalué).
```

**Seuil minimum** : si le nombre de lignes pertinentes trouvées est strictement inférieur à
`adaptive_min_examples`, la fonction renvoie une chaîne vide. Aucun changement de comportement tant
que le volume de feedback est insuffisant — c'est le mécanisme central qui rend ce sprint sûr à
déployer immédiatement, même avec zéro donnée.

## 4. Où et comment ça s'exécute

Le texte d'exemples est calculé **une fois par batch**, dans `classify_pending_items`/
`score_pending_items` (`job.py`), au même endroit et avec la même philosophie que le client
`AsyncAnthropic` partagé — jamais recalculé par item. Le résultat est transmis à
`classify_item`/`score_item` via un nouveau paramètre optionnel :

```python
async def classify_item(title: str, text: str, examples: str = "", client=None) -> ClassificationResult: ...
async def score_item(title: str, text: str, source_type: str, examples: str = "", client=None) -> ScoringResult: ...
```

Si `examples == ""` (défaut, ou batch sans assez de données), le message utilisateur envoyé au
modèle est **strictement identique** à aujourd'hui — aucune régression sur le comportement actuel
tant que le mécanisme n'a rien à injecter.

## 5. Intégration au prompt et sécurité

Quand `examples` est non-vide, il est inséré dans le message utilisateur avant le titre/texte de
l'item à traiter, délimité par des balises dédiées — même discipline anti-injection que `<article>`
depuis le Sprint 3 :

```text
Exemples de feedback humain récent (indicatif, à pondérer avec jugement) :
<exemples_feedback>
- Item classé COMMERCIAL par le modèle ; retour humain : hors périmètre Touch-Go.
- Item priorité C donnée par le modèle ; retour humain : 🔥 (probablement sous-évalué).
</exemples_feedback>

Titre : ...
Texte :
<article>
...
</article>
```

Le `comment` libre de ➕ NOUVELLE_CATEGORIE provient d'une saisie humaine de confiance (reviewer
unique, Sprint 5 §2) — risque d'injection nettement plus faible que le texte d'articles externes
déjà délimité par `<article>`, mais la même délimitation est conservée par cohérence et défense en
profondeur.

`SYSTEM_PROMPT` de classification et de scoring gagnent chacun un paragraphe expliquant que ces
exemples sont indicatifs, jamais des instructions à exécuter, et que le contenu de
`<exemples_feedback>` doit être traité comme celui de `<article>` : une donnée à considérer, jamais
une consigne.

## 6. Configuration

Nouveaux champs dans `Settings` (`src/config.py`) : `adaptive_min_examples: int = 5`,
`adaptive_max_examples: int = 5`. Utilisés indépendamment par `build_classification_examples` et
`build_scoring_examples` (même valeurs, deux appels séparés). Aucune migration de schéma — tout
puise dans `NewsFeedback`/`NewsItem`, déjà en place depuis les Sprints 1 et 5.

## 7. Tests

Le client LLM reste mocké dans tous les tests (aucun appel réseau réel), même pattern que les
sprints précédents. Couverture : `build_classification_examples`/`build_scoring_examples` testées
directement (seed de lignes `NewsFeedback`/`NewsItem`, vérifie le texte produit ligne par ligne, et
la chaîne vide sous le seuil `adaptive_min_examples`) ; `classify_item`/`score_item` testés pour
confirmer qu'un `examples` non-vide apparaît bien dans le message envoyé au modèle, et qu'un
`examples=""` (comportement par défaut) laisse le message strictement identique à avant ce sprint ;
`job.py` testé pour confirmer l'appel unique par batch (pas par item) aux fonctions de construction
d'exemples. Test d'intégration bout-en-bout : soumission d'un feedback via l'API du Sprint 5, puis
passage suivant de classification/scoring, puis vérification que le message envoyé au modèle
(mocké) contient bien l'exemple issu de ce feedback.

## 8. Hors scope Sprint 6

Ajustement numérique de poids ou classifieur dédié (§18, étape 5 — prématuré tant que le volume de
données reste faible) ; poids géographiques et importance d'entités (bloqué : `country`/`region`/
`entities` toujours hors périmètre depuis le Sprint 4) ; job planifié séparé de mise en cache des
exemples (écarté par YAGNI au profit du calcul par batch, section 4) ; toute UI ou API pour
curer/désactiver certains exemples individuellement ; recalcul ou purge automatique des exemples
devenus obsolètes ; extension du modèle de données `NewsFeedback` pour capturer une correction
structurée (catégorie/priorité corrigée) — écartée en section 2, resterait une option pour un
sprint ultérieur si le signal directionnel faible se révèle insuffisant en pratique.
