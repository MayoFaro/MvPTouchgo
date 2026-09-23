# Touch-Go News — LLM local via Ollama — Design

Statut : validé par l'utilisateur en conversation, prêt pour plan d'implémentation.

Référence architecturale : [Sprint 3 — design](2026-09-21-touchgo-news-sprint3-classification-design.md)
et [Sprint 4 — design](2026-09-21-touchgo-news-sprint4-scoring-design.md), dont ce document
remplace le fournisseur LLM sans toucher à l'architecture (job par batch, client partagé,
isolation d'erreur, retries) qu'ils ont établie.

## 1. Contexte et portée

Les Sprints 3 et 4 utilisent l'API Anthropic (modèle Claude Haiku) pour la classification et le
scoring, via le tool-use forcé (`tool_choice`) pour extraire des réponses structurées. Ce choix
implique un coût par appel. L'utilisateur ne souhaite pas payer pour cette API et demande un LLM
local à la place.

Ce document couvre le remplacement complet du fournisseur LLM par un modèle tournant en local via
Ollama, sur la machine de développement (GPU NVIDIA 8 Go VRAM, 15 Go RAM, 20 cœurs CPU — vérifié en
conversation). Remplacement simple, pas de couche multi-provider (décision actée en conversation :
YAGNI, pas de complexité pour un besoin hypothétique de revenir à Anthropic).

Aucun changement de périmètre fonctionnel : les mêmes deux tâches (classifier, scorer), les mêmes
prompts système (contenu inchangé à l'exception d'un point, voir section 3), les mêmes schémas de
sortie structurée, la même architecture de job par batch avec isolation d'erreur (Sprints 3/4).
Seul ce qui se trouve *derrière* `classify_item`/`score_item` change.

## 2. Runtime et modèle

**Runtime : Ollama.** Le plus simple à installer/maintenir, expose une API compatible avec le
pattern tool-use déjà utilisé, tourne comme un service en arrière-plan — adapté à un scheduler qui
déclenche des batches toutes les quelques minutes. Alternatives écartées : llama.cpp (plus de
contrôle mais configuration manuelle, support du tool-calling moins standardisé selon les
builds) ; LM Studio (orienté usage desktop interactif, moins adapté à un service background
fiable).

**Modèle : `qwen2.5:7b-instruct`.** ~4,7 Go en quantization Q4, tient confortablement dans les 8 Go
de VRAM disponibles avec de la marge. Choisi pour son bon suivi d'instructions et son support
tool-calling dans Ollama, avec de bonnes performances multilingues — les prompts de ce projet sont
entièrement en français et demandent un jugement éditorial nuancé (7 catégories, 4 scores
indépendants). `llama3.1:8b` reste une alternative de taille/qualité proche si `qwen2.5:7b-instruct`
s'avère insuffisant à l'usage ; un modèle 13-14B a été écarté pour l'instant (tient plus juste dans
8 Go VRAM, quantization plus agressive ou débordement CPU nécessaire — à reconsidérer seulement si
la qualité des deux options 7-8B s'avère insuffisante).

**Prérequis opérationnel** (étape manuelle, pas du code) : installer Ollama, lancer le service
(`ollama serve`, ou démarrage automatique selon l'installation), puis `ollama pull
qwen2.5:7b-instruct` avant de lancer le pipeline.

## 3. Format des tools et fiabilité de l'appel

Anthropic force l'appel de l'outil via `tool_choice={"type": "tool", "name": "..."}` — le modèle
*doit* répondre avec cet outil. Ollama expose un format différent, calqué sur OpenAI
(`{"type": "function", "function": {"name", "description", "parameters"}}`), et ne garantit pas la
même contrainte forte selon les modèles — un modèle local peut en théorie répondre en texte libre
au lieu d'appeler l'outil.

`CLASSIFY_TOOL` (`src/classification/prompt.py`) et `SCORE_TOOL` (`src/scoring/prompt.py`) sont
reconvertis au format `{"type": "function", "function": {...}}` — mêmes propriétés et `required`,
seule l'enveloppe change.

Sur la fiabilité : `parse_classification_response`/`parse_scoring_response` traitent déjà toute
réponse invalide comme une erreur qui déclenche le retry existant (`MAX_ATTEMPTS = 2` dans
`client.py`) — si le modèle local répond sans appeler l'outil, c'est simplement un nouveau cas de
« réponse invalide », absorbé par l'isolation d'erreur déjà en place depuis les Sprints 3/4 (item
non traité, retenté au batch suivant, jamais de valeur forcée). `MAX_ATTEMPTS`/
`RETRY_DELAY_SECONDS` restent inchangés pour l'instant, à ajuster seulement si l'usage réel montre
que 2 tentatives sont insuffisantes avec ce modèle.

## 4. Client et job : ce qui change concrètement

Même architecture qu'aujourd'hui (client partagé par batch, signature `classify_item(title, text,
examples="", client=None)` / `score_item(title, text, source_type, examples="", client=None)`
inchangée pour les appelants — `job.py`, `src/adaptive/`, les tests d'intégration), seule
l'implémentation interne bascule :

- **`job.py`** (classification et scoring) : `anthropic.AsyncAnthropic(api_key=...)` devient un
  client Ollama construit une fois par batch (`ollama.AsyncClient(host=settings.ollama_host)`),
  réutilisé pour chaque item du batch — même principe de partage qu'aujourd'hui, SDK différent.
- **`client.py`** (classification et scoring) : l'appel
  `active_client.messages.create(system=..., tools=[...], tool_choice={...}, messages=[...])`
  devient `active_client.chat(model=settings.ollama_model, messages=[...], tools=[...])`, où le
  prompt système est le premier message de la liste (`{"role": "system", "content": SYSTEM_PROMPT}`)
  plutôt qu'un paramètre séparé ; pas de `tool_choice` forcé (section 3) ; pas de `max_tokens`
  requis par l'API Ollama.
- **`parse_classification_response`/`parse_scoring_response`** sont réécrites pour lire la forme de
  réponse d'Ollama (`response.message.tool_calls`) au lieu de celle d'Anthropic
  (`response.content`), en conservant exactement la même logique de validation (catégorie valide
  parmi `CATEGORIES`, scores dans `0..10`, priorité valide parmi `PRIORITIES`, etc.) et la même
  levée de `ValueError` en cas de réponse invalide — aucun changement côté `job.py`, qui consomme
  ces fonctions sans connaître leur implémentation interne.
- La constante `MODEL = "claude-haiku-4-5-20251001"` de chaque `client.py` est remplacée par la
  lecture de `settings.ollama_model`.

Rien ne change dans `src/adaptive/`, `src/api/`, `src/review/`, `src/scheduler.py`, ou tout autre
sprint déjà livré — l'interface `classify_item`/`score_item` reste la même façade stable, seul ce
qu'il y a derrière elle change.

## 5. Configuration

`pyproject.toml` : `anthropic>=0.40` remplacé par `ollama` (version exacte fixée à
l'implémentation, dernière version stable disponible).

`src/config.py` : `anthropic_api_key: str = ""` supprimé, remplacé par
`ollama_host: str = "http://localhost:11434"` et `ollama_model: str = "qwen2.5:7b-instruct"`.

`.env.example` : ligne `ANTHROPIC_API_KEY=` supprimée, remplacée par
`OLLAMA_HOST=http://localhost:11434` et `OLLAMA_MODEL=qwen2.5:7b-instruct`.

Aucun changement de schéma DB, aucun changement aux réglages de batch/intervalle/retry existants
(`classification_*`, `scoring_*`, `adaptive_*`) — uniquement le point de configuration du
fournisseur LLM change.

## 6. Tests et vérification manuelle

Même principe que tous les sprints précédents : **aucun appel réseau réel dans les tests
automatisés**, jamais de serveur Ollama réel sollicité par la suite de tests. Les fakes
`_FakeAnthropicClient`/`_FakeMessages`/`_FakeToolUseBlock`/`_FakeResponse` (dans
`tests/classification/test_client.py` et `tests/scoring/test_client.py`) sont remplacés par leurs
équivalents mimant la forme de réponse d'Ollama (un `_FakeOllamaClient` avec une méthode `.chat()`
asynchrone, trackant `calls`/`last_kwargs` comme aujourd'hui, avec injection de `fail_times`/
`exception` pour les tests de retry). Un nouveau test couvre explicitement un cas propre à Ollama :
le modèle répond sans appeler l'outil (`tool_calls` vide ou absent) — doit être traité comme un
échec de parsing, retry inclus, exactement comme n'importe quelle autre réponse invalide.

Au-delà des tests automatisés : contrairement à Claude, la fiabilité réelle d'un modèle local 7B
sur ce prompt éditorial en français est une inconnue réelle. Étape de **vérification manuelle
renforcée**, au-delà du simple « ça tourne » des sprints précédents : lancer le pipeline contre le
vrai service Ollama et le vrai modèle sur un échantillon réel d'items déjà collectés, et comparer à
l'œil le jugement du modèle local à ce qui serait attendu — avant de considérer le remplacement
validé en pratique. Cette étape n'est pas un critère bloquant pour merger le code (les tests
automatisés avec fakes restent la porte de qualité du code), mais une étape explicite à ne pas
sauter avant de faire confiance au système au quotidien.

## 7. Hors scope

Couche d'abstraction multi-provider permettant de switcher Anthropic ↔ Ollama (écarté section 1,
YAGNI) ; changement de `MAX_ATTEMPTS`/`RETRY_DELAY_SECONDS` sans preuve que c'est nécessaire avec
ce modèle (section 3) ; gestion spéciale du cas « Ollama indisponible » ou « modèle non
téléchargé » — absorbés par l'isolation d'erreur existante, un item non traité reste non traité et
sera retenté au batch suivant, sans traitement différencié par cause d'échec ; changement au
mécanisme d'exemples adaptatifs du Sprint 6 (déjà agnostique du fournisseur LLM, aucune adaptation
nécessaire) ; automatisation de l'installation d'Ollama ou du téléchargement du modèle (étape
manuelle documentée, pas scriptée) ; benchmark formel comparant qualité Claude Haiku vs
qwen2.5:7b-instruct (la vérification manuelle de la section 6 est qualitative, pas un protocole de
mesure).
