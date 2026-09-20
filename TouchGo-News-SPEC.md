# Touch-Go News MVP — SPEC.md

## 1. Objectif

Développer un MVP autonome de veille aéronautique pour alimenter la section **News** de Touch-Go.

Le système doit :

1. collecter automatiquement des actualités aéronautiques depuis plusieurs types de sources ;
2. conserver largement les contenus détectés ;
3. classer les contenus par thème ;
4. évaluer leur intérêt potentiel pour Touch-Go ;
5. permettre une revue humaine rapide ;
6. apprendre progressivement des décisions humaines afin d'améliorer le classement.

### Principe absolu

**Aucune publication automatique.**

Le système ne publie jamais directement sur Touch-Go.

Toute publication reste entièrement manuelle.

Si ce principe devait changer un jour, le processus complet devra être redéfini et validé séparément.

---

# 2. Philosophie générale du MVP

Le MVP doit privilégier le **rappel** plutôt que la précision.

Autrement dit :

> Il vaut mieux présenter trop d'informations au début que manquer une information importante qui deviendrait alors invisible.

Le système doit donc :

- collecter largement ;
- conserver tous les contenus collectés ;
- éviter les suppressions automatiques ;
- classer plutôt qu'éliminer ;
- permettre d'inspecter les contenus jugés peu pertinents ;
- s'améliorer progressivement grâce au feedback humain.

Une mauvaise priorité est acceptable au début.

Une news importante absente du système est un échec.

---

# 3. Population cible

Touch-Go est une petite communauté aéronautique professionnelle ou très avertie.

Le public n'est pas celui d'un média grand public.

Les informations pertinentes doivent donc privilégier :

- impact professionnel ;
- impact opérationnel ;
- évolution du secteur ;
- emploi ;
- défense / aviation militaire ;
- réglementation importante ;
- incidents et accidents significatifs ;
- événements aéronautiques importants.

La valeur du système ne réside pas dans la quantité de news mais dans leur sélection pour cette population spécifique.

---

# 4. Catégories éditoriales

Les catégories initiales sont :

```text
COMMERCIAL
EMPLOI
MILITAIRE
REGLEMENTATION
MEETING
ACCIDENT_INCIDENT
DIVERS
```

Un article peut avoir :

- une catégorie principale ;
- zéro ou plusieurs catégories secondaires.

Exemple :

```text
primary_category: militaire
secondary_categories:
  - accident_incident
```

---

# 5. Rôle spécifique de la catégorie DIVERS

`DIVERS` est une catégorie de sécurité.

Elle ne doit jamais être considérée comme une catégorie de faible valeur.

Elle sert à récupérer :

- les sujets qui ne correspondent à aucune catégorie actuelle ;
- les sujets dont la classification est incertaine ;
- les thèmes émergents qui n'avaient pas été prévus lors de la conception.

Règle fondamentale :

> Une news ne doit jamais être rejetée simplement parce qu'elle ne rentre dans aucune catégorie connue.

Si aucune catégorie n'est satisfaisante :

```text
category = DIVERS
```

Le système doit également pouvoir identifier à terme des groupes récurrents dans `DIVERS` et signaler :

> Ce thème revient fréquemment et pourrait justifier une nouvelle catégorie.

La décision de créer une nouvelle catégorie reste humaine.

---

# 6. Périmètre éditorial

## 6.1 Aviation commerciale

Filtrage relativement strict.

À conserver notamment :

- disparition ou faillite d'une compagnie significative ;
- fusion ou acquisition importante ;
- restructuration majeure ;
- changement important de flotte ;
- nouvel avion ;
- nouvelle variante majeure ;
- certification importante ;
- problème industriel sérieux ;
- changement stratégique important chez Airbus, Boeing, ATR, Embraer ou autre constructeur important ;
- rupture majeure de chaîne d'approvisionnement ;
- événement économique ayant un effet significatif sur le transport aérien.

À rejeter généralement :

- simple ouverture de ligne ;
- livraison individuelle d'un avion ;
- petite commande routinière ;
- communication corporate sans enjeu réel ;
- actualité commerciale mineure.

Une commande ou un événement normalement banal peut toutefois être retenu si son ampleur modifie réellement le marché.

---

# 6.2 Emploi

Cette catégorie doit être surveillée assez largement.

À conserver notamment :

- campagnes importantes de recrutement ;
- campagnes pilotes ;
- campagnes PNC ;
- recrutement maintenance ;
- gels d'embauche ;
- licenciements ;
- réduction d'effectifs ;
- pénurie de pilotes ;
- pénurie de personnel technique ;
- changement significatif de conditions de recrutement ;
- évolution importante des sélections ;
- tendances du marché de l'emploi aéronautique ;
- signaux annonçant une reprise ou une contraction du recrutement.

Priorité géographique :

```text
France : élevée
Europe : élevée
reste du monde : moyenne
```

Une information étrangère peut néanmoins être hautement pertinente si elle concerne une grande compagnie ou une tendance structurante.

---

# 6.3 Aviation militaire

Cette catégorie doit être surveillée **largement**.

C'est l'une des catégories les plus importantes pour Touch-Go.

À conserver notamment :

- nouveaux appareils ;
- programmes ;
- prototypes ;
- évolutions de flotte ;
- modernisations ;
- armements ;
- drones ;
- essais ;
- exercices ;
- opérations ;
- doctrine ;
- organisation des forces ;
- commandes ;
- exportations ;
- production ;
- difficultés industrielles ;
- évolutions capacitaires ;
- accidents militaires ;
- nouveaux capteurs ;
- guerre électronique ;
- systèmes de mission ;
- programmes futurs.

Couverture :

```text
MONDE ENTIER
```

Le système ne doit pas être centré uniquement sur les sources occidentales.

Les sources russes et chinoises doivent être incluses.

---

# 6.4 Sources militaires ukrainiennes et israéliennes

Les sources militaires ou étatiques ukrainiennes et israéliennes ne doivent pas être surveillées directement dans le pool initial.

Cela signifie uniquement :

```text
pas d'ingestion directe
```

Une information concernant l'Ukraine ou Israël peut parfaitement entrer dans le système si elle provient d'autres sources :

- Reuters ;
- Janes ;
- FlightGlobal ;
- Aviation Week ;
- PPRuNe ;
- sources russes ;
- sources chinoises ;
- médias professionnels ;
- autres observateurs.

---

# 6.5 Réglementation

Filtrage strict.

Ne conserver que les changements ayant un impact réel.

Exemples :

- licences ;
- médical ;
- âge des pilotes ;
- FTL ;
- temps de vol ;
- temps de service ;
- formation ;
- règles d'exploitation ;
- espace aérien ;
- certification ;
- navigation ;
- obligations opérationnelles ;
- changements réglementaires significatifs affectant les compagnies ou équipages.

À rejeter généralement :

- mise à jour administrative mineure ;
- modification technique sans conséquence réelle ;
- consultation routinière ;
- modification de détail d'un AMC ou GM sans impact pratique significatif.

---

# 6.6 Meetings / événements aéronautiques

À conserver :

- grands meetings ;
- grands salons ;
- manifestations aériennes importantes ;
- grands événements militaires ;
- grands événements français ;
- grands événements européens proches ;
- événements internationaux exceptionnels.

Cette catégorie pourra ultérieurement alimenter un agenda.

---

# 6.7 Accidents et incidents

Le seuil dépend fortement de la zone géographique.

## France

```text
mineur : généralement faible
moyen : à remonter
important : priorité élevée
majeur : priorité absolue
```

## Étranger

```text
mineur : généralement faible
moyen : à examiner
important : priorité élevée
majeur : priorité absolue
```

Le système doit être plus permissif pour la France.

Les accidents militaires peuvent également recevoir la catégorie secondaire `MILITAIRE`.

---

# 7. Types de sources

Les sources doivent être séparées en quatre familles.

## A. Sources officielles / primaires

Exemples :

- BEA
- EASA
- DGAC
- EUROCONTROL
- Airbus
- Boeing
- ATR
- Embraer
- Ministère des Armées
- DGA
- forces aériennes
- constructeurs militaires
- UAC
- Rostec
- AVIC
- administrations nationales

Ces sources servent souvent de confirmation primaire.

---

## B. Presse professionnelle fiable

Exemples :

- FlightGlobal
- Aviation Week
- Janes
- Reuters
- Air & Cosmos
- Defense News
- Opex360

---

## C. Médias / radars rapides

Exemples :

- AeroTime
- Air Journal
- The War Zone
- The Aviationist
- autres médias spécialisés rapides

Ils peuvent détecter des sujets tôt, mais nécessitent parfois confirmation.

---

## D. Sources communautaires / signaux faibles

Très importantes.

Exemples :

- PPRuNe
- Aeronet
- Airliners.net forums
- Secret Projects Forum
- forums spécialisés
- éventuellement Reddit
- éventuellement Telegram

Ces sources peuvent révéler :

- recrutement ;
- changement de roster ;
- mouvements internes ;
- rumeurs industrielles crédibles ;
- incidents ;
- évolution d'une compagnie ;
- programmes militaires ;
- signaux faibles.

Règle fondamentale :

> Faible fiabilité ne signifie pas faible intérêt.

Une information PPRuNe peut être :

```text
importance potentielle: 9/10
intérêt Touch-Go: 10/10
fiabilité: 3/10
```

Elle doit donc remonter fortement avec un statut :

```text
A CONFIRMER
```

---

# 8. Sources initiales proposées

Pool initial :

## Général / industrie

- FlightGlobal
- Aviation Week
- Reuters
- Air & Cosmos
- Aerobuzz
- Air Journal
- AeroTime

## Constructeurs

- Airbus
- Boeing
- ATR
- Embraer
- Safran

## Emploi / communautés

- PPRuNe
- Aeronet

## Sécurité

- BEA
- Aviation Herald
- NTSB
- AAIB

## Réglementation

- EASA
- DGAC
- EUROCONTROL

## Militaire France

- Opex360
- Air & Cosmos
- Ministère des Armées
- Armée de l'Air et de l'Espace
- DGA

## Militaire international

- Janes
- Defense News
- The War Zone
- The Aviationist
- FlightGlobal Defence
- Aviation Week Defence

## Russie

- TASS
- Interfax
- UAC
- Rostec
- BMPD
- sources Telegram spécialisées à qualifier ultérieurement

## Chine

- PLA Daily / China Military
- Xinhua
- AVIC
- observateurs spécialisés à qualifier ultérieurement

## Forums / communautés

- PPRuNe
- Aeronet
- Airliners.net forums
- Secret Projects Forum

---

# 9. Importance particulière de PPRuNe et Aeronet

Ces deux forums sont des capteurs importants.

## PPRuNe

Sections potentiellement pertinentes :

- Rumours & News
- Terms and Endearment
- Accidents and Close Calls
- Military Aviation
- Tech Log

## Aeronet

Particulièrement utile pour :

- emploi ;
- recrutements ;
- sélections ;
- compagnies françaises ;
- compagnies européennes ;
- marché pilote ;
- informations professionnelles françaises.

Les forums ne doivent pas être considérés comme sources de validation définitive.

Ils servent à détecter les signaux.

---

# 10. Collecte des forums

Ne pas considérer chaque message comme une news indépendante.

Créer plutôt un objet de type thread :

```text
thread_id
title
url
created_at
last_activity
number_of_new_posts
relevant_extracts
detected_entities
detected_topics
```

Le système doit pouvoir détecter :

- apparition d'un nouveau thread ;
- reprise soudaine d'un ancien thread ;
- augmentation rapide du nombre de réponses ;
- apparition d'une information nouvelle dans un fil ancien.

---

# 11. Modèle d'évaluation

Ne jamais utiliser un score unique.

Chaque contenu doit recevoir au minimum quatre dimensions indépendantes :

```text
touchgo_interest
event_importance
source_confidence
urgency
```

Chaque score :

```text
0 à 10
```

Exemple :

```text
touchgo_interest: 9
event_importance: 8
source_confidence: 3
urgency: 8
```

Une faible fiabilité ne doit jamais empêcher une information potentiellement très intéressante de remonter.

---

# 12. Priorités

Après évaluation :

```text
A = forte probabilité d'intérêt
B = intérêt possible / à examiner
C = intérêt probablement faible mais contenu conservé
```

Aucune priorité n'entraîne de suppression.

Tous les éléments restent consultables.

---

# 13. Statuts de vérification

Prévoir au minimum :

```text
UNVERIFIED
SINGLE_SOURCE
INDEPENDENTLY_CONFIRMED
PRIMARY_SOURCE_CONFIRMED
DISPUTED
```

Les contenus issus de forums commencent généralement comme :

```text
UNVERIFIED
```

---

# 14. Sources étatiques et communication de guerre

Une source officielle russe ou chinoise peut être une source primaire sur :

- une annonce industrielle ;
- une commande ;
- une entrée en service ;
- un essai ;
- une déclaration officielle.

En revanche, les affirmations concernant :

- pertes ennemies ;
- efficacité opérationnelle ;
- destructions ;
- résultats d'une opération ;
- revendications de combat ;

doivent rester attribuées à leur source et ne jamais être transformées automatiquement en fait établi.

Même logique pour toute communication d'un acteur directement impliqué dans un conflit.

---

# 15. Déduplication

La même news peut apparaître dans plusieurs sources.

Exemple :

```text
Airbus
Reuters
FlightGlobal
Air & Cosmos
PPRuNe
```

Le système ne doit pas présenter cinq événements totalement distincts.

Il doit progressivement construire une notion d'`EVENT`.

Exemple :

```text
EVENT #452

Titre conceptuel:
Airbus lance une nouvelle variante X

Sources:
- Airbus
- Reuters
- FlightGlobal
- Air & Cosmos
- PPRuNe

Source primaire:
Airbus

Confirmation indépendante:
Reuters

Analyse:
FlightGlobal

Discussion communautaire:
PPRuNe
```

---

# 16. Modèle de données conceptuel

## NEWS_SOURCE

```text
id
name
url
source_type
language
confirmation_level
detection_value
active
config
```

## NEWS_ITEM

```text
id

source_id
source_item_id
canonical_url
original_url

original_title
original_text
language
author
published_at
detected_at

primary_category
secondary_categories[]
classification_confidence

country
region
entities

touchgo_interest
event_importance
source_confidence
urgency

priority
verification_status

duplicate_of
event_id

status

model_reason
model_metadata

human_decision
human_reason
human_comment
reviewed_at
reviewer_id
```

## NEWS_EVENT

```text
id
title
category
first_seen_at
last_seen_at
importance
verification_status
summary_metadata
```

## NEWS_FEEDBACK

```text
id
news_item_id
decision
reason
comment
previous_priority
previous_category
created_at
reviewer_id
```

---

# 17. Feedback humain

Actions rapides :

```text
🔥 Très intéressant
👍 Intéressant
👀 À suivre
❌ Rejeter
```

Si rejet :

```text
trop mineur
pas pertinent Touch-Go
trop commercial
trop local
signal trop faible
doublon
information douteuse
hors périmètre
autre
```

Action particulière :

```text
➕ Mériterait une nouvelle catégorie
```

---

# 18. Apprentissage adaptatif

Le système doit utiliser les décisions humaines pour améliorer progressivement :

- classement ;
- catégories ;
- priorité ;
- poids des sources ;
- poids géographiques ;
- importance de certaines entités ;
- importance de certains thèmes.

Au début, pas besoin de machine learning dédié.

Approche recommandée :

1. règles explicites ;
2. classification LLM ;
3. exemples historiques issus du feedback ;
4. ajustement progressif du prompt ;
5. éventuellement classifieur dédié lorsque suffisamment de données sont disponibles.

---

# 19. Faux négatifs

C'est la métrique la plus importante au début.

Il faut périodiquement examiner un échantillon des contenus classés `C`.

Question :

> Y avait-il parmi eux une information qui aurait dû être en A ou B ?

Si oui :

- enregistrer cette correction ;
- identifier pourquoi ;
- modifier le filtre.

---

# 20. Interface MVP

L'interface doit rester minimale.

## Filtres

```text
Toutes
A
B
C

Commercial
Emploi
Militaire
Réglementation
Meeting
Accident/Incident
Divers

24 h
3 jours
7 jours
```

## Carte d'une news

Exemple :

```text
[A] [MILITAIRE]                  il y a 37 min

Russie teste une nouvelle version de ...

Source: BMPD
Langue: russe

Intérêt Touch-Go: 9
Importance: 7
Fiabilité: 4
Urgence: 7

Statut: A CONFIRMER

[🔥] [👍] [👀] [❌] [Ouvrir]
```

---

# 21. Vues fonctionnelles proposées

Trois vues principales :

## À voir

Contenus les plus intéressants.

## À surveiller

Signaux faibles, forums, rumeurs, sujets en développement.

## Faible priorité

Contenus probablement faibles mais conservés.

---

# 22. Pipeline cible v0.1

```text
SOURCES
   ↓
COLLECTE
   ↓
NORMALISATION
   ↓
DEDUPLICATION
   ↓
EXTRACTION D'ENTITES
   ↓
CLASSIFICATION
   ↓
EVALUATION
   ↓
PRIORITE A/B/C
   ↓
REVUE HUMAINE
   ↓
FEEDBACK
```

---

# 23. Ce que le MVP v0.1 NE FAIT PAS

Pas encore :

- publication automatique ;
- publication manuelle intégrée à Touch-Go ;
- génération finale de post ;
- traduction finale prête à publier ;
- résumé éditorial final ;
- commentaire éditorial ;
- publication forum ;
- apprentissage ML dédié.

Le but du MVP est uniquement :

> détecter correctement les bonnes informations.

---

# 24. MVP v0.2 ultérieur

Lorsque la sélection sera fiable :

Ajouter une fonction :

```text
Générer un brouillon
```

Le brouillon pourra contenir :

- titre français ;
- synthèse courte ;
- traduction des éléments essentiels ;
- faits principaux ;
- contexte ;
- sources ;
- liens ;
- avertissements éventuels ;
- statut de vérification.

Toujours sans publication automatique.

---

# 25. Architecture de développement recommandée

Développer le système comme un service indépendant dans VS Code.

Structure suggérée :

```text
touchgo-news/
│
├── README.md
├── SPEC.md
├── .env.example
├── requirements.txt
│
├── config/
│   ├── sources.yaml
│   └── editorial_rules.yaml
│
├── src/
│   ├── collectors/
│   ├── normalizers/
│   ├── dedup/
│   ├── classifiers/
│   ├── scoring/
│   ├── entities/
│   ├── feedback/
│   ├── db/
│   └── api/
│
├── web/
│   └── admin/
│
├── tests/
│
└── data/
```

---

# 26. Stack technique recommandée pour le prototype

Sauf contrainte imposée par Touch-Go :

```text
Python 3.12+
FastAPI
SQLAlchemy
PostgreSQL
Pydantic
httpx
BeautifulSoup
feedparser
Playwright uniquement lorsque nécessaire
YAML pour la configuration
```

Frontend MVP :

```text
HTML simple / Jinja
ou
petite interface React si Touch-Go utilise déjà React
```

Préférence MVP :

> rester simple tant que le système de veille n'est pas validé.

---

# 27. Règles de collecte

Priorité :

1. RSS ;
2. API publique ;
3. HTML statique ;
4. scraping ;
5. navigateur automatisé uniquement en dernier recours.

Chaque collecteur doit être indépendant.

Interface logique recommandée :

```python
class Collector:
    source_id: str

    async def fetch(self) -> list[RawItem]:
        ...
```

---

# 28. Normalisation

Pour chaque item :

- URL canonique ;
- titre propre ;
- date ;
- langue ;
- texte ou extrait ;
- source ;
- identifiant source ;
- hash contenu.

---

# 29. Déduplication v0.1

Commencer simplement :

- URL canonique ;
- titre normalisé ;
- similarité titre ;
- hash texte ;
- date proche.

Ne pas chercher immédiatement une déduplication parfaite.

Étape suivante :

- embeddings ;
- regroupement sémantique ;
- notion d'événement.

---

# 30. Collecte et classification doivent être séparées

Important :

Le collecteur ne décide pas si une news est intéressante.

Il se contente de collecter.

Pipeline :

```text
collector
→ raw item
→ normalized item
→ classifier
→ scorer
```

Cela permet de recalculer les scores sans recollecter toutes les sources.

---

# 31. Historique

Tous les contenus doivent rester stockés.

Cela permet :

- recalcul des scores ;
- audit ;
- analyse des erreurs ;
- entraînement futur ;
- comparaison des versions du filtre ;
- compréhension des faux négatifs.

---

# 32. Métriques MVP

Mesures principales :

```text
nombre total collecté
nombre A
nombre B
nombre C

nombre retenu humainement
nombre rejeté

taux d'acceptation des A
taux d'acceptation des B
taux d'erreur dans C

nombre de faux négatifs détectés
nombre de news importantes absentes
```

La métrique la plus importante :

```text
news importantes absentes = 0
```

---

# 33. Test initial

Test sur 72 heures réelles.

Question principale :

> Tout ce que l'éditeur aurait voulu voir est-il présent dans le système ?

Résultats possibles :

## Cas 1

News absente de la base.

Cause probable :

- source manquante ;
- collecteur défaillant ;
- source non surveillée ;
- scraping incomplet.

## Cas 2

News présente mais en C.

Cause :

- problème de classement.

Acceptable au début.

## Cas 3

News présente en DIVERS.

Le système a fonctionné.

## Cas 4

News présente en A ou B.

Résultat attendu.

---

# 34. Plan de développement

## Sprint 1 — Collecte

Objectif :

- repo ;
- configuration sources ;
- base ;
- premiers collecteurs ;
- stockage brut.

Commencer avec environ 8 à 10 sources différentes :

- FlightGlobal
- Airbus
- BEA
- EASA
- Opex360
- PPRuNe
- Aeronet
- Aviation Herald
- source russe
- source chinoise

But :

valider plusieurs types de sources.

---

## Sprint 2 — Normalisation et déduplication

Ajouter :

- URL canonique ;
- dates ;
- langue ;
- hash ;
- déduplication basique.

---

## Sprint 3 — Classification

Ajouter :

- sept catégories ;
- catégorie DIVERS ;
- catégories secondaires ;
- score de confiance.

---

## Sprint 4 — Scoring

Ajouter :

- intérêt Touch-Go ;
- importance ;
- fiabilité ;
- urgence ;
- A/B/C.

---

## Sprint 5 — Interface admin

Ajouter :

- liste ;
- filtres ;
- cartes news ;
- feedback humain.

---

## Sprint 6 — Boucle adaptative

Ajouter :

- stockage feedback ;
- injection des exemples précédents dans le classifieur ;
- audit périodique des C ;
- détection de nouvelles catégories potentielles.

---

## Sprint 7 — Événements

Ajouter :

- regroupement d'articles ;
- sources multiples ;
- confirmation ;
- historique de l'événement.

---

# 35. Critères d'acceptation du MVP

Le MVP est considéré comme fonctionnel si :

1. plusieurs sources différentes sont collectées correctement ;
2. aucune publication automatique n'existe ;
3. tous les contenus sont conservés ;
4. chaque contenu reçoit une catégorie ou `DIVERS` ;
5. chaque contenu reçoit A/B/C ;
6. la source et le niveau de vérification sont visibles ;
7. l'utilisateur peut marquer un item :
   - très intéressant ;
   - intéressant ;
   - à suivre ;
   - rejeté ;
8. le motif de rejet est conservé ;
9. les contenus C restent accessibles ;
10. on peut vérifier les faux négatifs ;
11. le système peut évoluer sans modifier le code pour chaque source ou catégorie.

---

# 36. Principe directeur

Le système doit être conçu autour de cette idée :

> Ne pas décider automatiquement ce que Touch-Go doit publier.

Il doit uniquement aider l'humain à répondre plus vite à la question :

> Parmi tout ce qui vient de sortir dans l'aéronautique, qu'est-ce qui mérite que je m'y intéresse ?
