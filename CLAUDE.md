# CLAUDE.md — Ninja Chess

Ce fichier sert de référence pour Claude (et tout développeur) travaillant sur ce projet. Il décrit l'architecture, le stack technique, les conventions et les décisions de conception.

---

## Vue d'ensemble du projet

**Ninja Chess** est un jeu d'échecs multijoueur en ligne et en temps réel. La principale particularité est que les deux joueurs peuvent bouger leurs pièces simultanément — il n'y a pas de tour par tour. Chaque pièce a un cooldown individuel après chaque mouvement.

Le jeu est une **application web** : il n'y a qu'un seul projet, `server/`, qui contient à la fois :
- le serveur Python (logique de jeu, comptes, rooms, communication réseau)
- le client navigateur (HTML/CSS/JS sans étape de build) servi en statique par ce même serveur (`server/static/`)

Un seul conteneur Docker, exposé sur le port 8200.

---

## Stack technique

### Serveur (`server/`)

| Composant | Technologie | Raison |
|---|---|---|
| Framework web | `FastAPI` | Gestion des routes HTTP (comptes, classement, profils) + support WebSocket natif |
| Temps réel | `python-socketio` + `uvicorn` | Gestion des rooms, événements nommés, reconnexion automatique côté client |
| Base de données | `SQLite` via `SQLAlchemy` | Suffisant pour l'échelle du projet, pas de dépendance externe |
| Migrations | `Alembic` | Gestion des évolutions de schéma |
| Conteneurisation | `Docker` + `docker-compose` | Déploiement reproductible |
| Auth | JWT (`python-jose`) + hash bcrypt (`passlib`) | Sécurité des comptes et de la session persistante |

**URL de production** : `https://ninja-chess.parzizou.fr`

Le serveur tourne derrière un reverse proxy (Nginx) gérant le SSL, les WebSockets (`wss://`) et le trafic HTTP.

### Client navigateur (`server/static/`)

| Composant | Technologie | Raison |
|---|---|---|
| Interface | HTML + CSS + JavaScript (modules ES natifs) | Pas de build, servi directement par FastAPI |
| Échiquier | `<canvas>` 2D | Animations, effets des augments, drag & drop (pointer events, tactile inclus) |
| Communication réseau | `socket.io-client` (copie dans `static/js/vendor/`) | Compatible avec `python-socketio` |
| Session "rester connecté" | `localStorage` (sinon `sessionStorage`) | JWT conservé côté navigateur |

---

## Structure des dossiers

```
ninja-chess/
├── CLAUDE.md
├── docker-compose.yml        # Orchestration (build ./server, port 8200)
├── docs/Rumble_augments.txt  # Description des augments
└── server/
    ├── app/
    │   ├── main.py           # FastAPI + socketio + service des fichiers statiques
    │   ├── routers/          # Routes HTTP (auth, users, leaderboard)
    │   ├── events/           # Handlers socketio (rooms, game, rumble)
    │   ├── models/           # Modèles SQLAlchemy (User, Game)
    │   ├── schemas/          # Schémas Pydantic (requêtes/réponses)
    │   ├── logic/            # Logique pure d'échecs, augments, elo
    │   └── database.py       # Initialisation SQLAlchemy + session
    ├── static/               # Client web
    │   ├── index.html
    │   ├── css/style.css
    │   ├── assets/           # sprites, sons, avatar par défaut
    │   └── js/
    │       ├── main.js, app.js        # démarrage + routeur d'écrans
    │       ├── api.js, socket.js      # REST (JWT) + Socket.IO partagé
    │       ├── board.js, chess.js     # canvas de l'échiquier + génération des coups (surlignage / IA)
    │       ├── sounds.js, assets.js, util.js
    │       ├── vendor/socket.io.min.js
    │       └── screens/               # login, home, rooms, waiting, game, ai_*, augment_select, rumble_game, leaderboard, profile
    ├── Dockerfile
    ├── requirements.txt
    └── .env                  # Variables d'environnement (SECRET_KEY, DATABASE_URL, etc.)
```

Déploiement : `docker compose up -d --build` depuis la racine.
Lancement local : `cd server && uvicorn app.main:combined_app --port 8200`, puis ouvrir http://localhost:8200.
Remise à zéro de la base : arrêter le conteneur et supprimer `server/data/ninja_chess.db`.

---

## Architecture réseau

### Communication client ↔ serveur

Deux canaux coexistent :

1. **HTTP REST** (via FastAPI) — pour les opérations non temps-réel :
   - `POST /auth/register` — création de compte
   - `POST /auth/login` — connexion, retourne un JWT
   - `GET /leaderboard` — classement global
   - `GET /users/{username}/profile` — profil et statistiques
   - `POST /users/avatar` — upload d'image de profil

2. **WebSocket / Socket.IO** — pour tout ce qui est temps réel :
   - Connexion à une room, lancement de partie
   - Envoi et réception des mouvements de pièces
   - Mise à jour des cooldowns
   - Fin de partie (capture du roi)

### Événements Socket.IO (nommage)

Conventions : `snake_case`, préfixe selon le contexte.

**Client → Serveur**
- `room:create` — créer une room
- `room:join` — rejoindre une room existante
- `room:leave` — quitter une room
- `game:move` — envoyer un mouvement `{ piece_id, from, to }`

**Serveur → Client**
- `room:list` — liste des rooms disponibles
- `room:ready` — la room est pleine, la partie commence
- `game:state` — état complet du plateau (envoyé au début)
- `game:move_ack` — confirmation/rejet d'un mouvement
- `game:opponent_move` — mouvement de l'adversaire à appliquer
- `game:cooldown` — mise à jour du cooldown d'une pièce
- `game:over` — fin de partie avec résultat

---

## Logique de jeu

### Cooldowns des pièces (en secondes)

| Pièce | Cooldown |
|---|---|
| Pion | 1,5 s |
| Cavalier | 3 s |
| Fou | 3 s |
| Tour | 4 s |
| Dame | 5 s |
| Roi | 3 s |

Le serveur est **autoritaire** : c'est lui qui valide chaque mouvement et qui gère les cooldowns. Le client affiche les cooldowns localement pour le feedback visuel, mais le serveur rejette tout mouvement envoyé pendant le cooldown.

### Validation des coups

La logique de validation est isolée dans `server/app/logic/` et ne dépend d'aucune bibliothèque externe — uniquement de la logique d'échecs pure. Cela permet de la tester unitairement sans démarrer le serveur complet.

### Calcul Elo

Formule standard Elo (K=32). Deux scores distincts : un pour le mode Standard, un pour le mode Rumble. Score initial à la création d'un compte : **1000**.

### Mode Rumble (spécification de référence)

Le mode Rumble oppose 2 joueurs sur plusieurs manches.

- Le premier joueur à gagner **3 manches** remporte la partie (format BO5).
  > Valeur de référence : `ROUNDS_TO_WIN` dans `server/app/logic/rumble.py`. La
  > spécification d'origine prévoyait un BO7 (4 manches) ; le code et l'UI sont
  > aujourd'hui alignés sur un BO5. Passer en BO7 demande de changer
  > `ROUNDS_TO_WIN` **et** le nombre de pips dans `renderScore` / `scorePips`
  > (`server/static/js/screens/rumble_game.js` et `augment_select.js`).
- Avant chaque manche, chaque joueur reçoit **3 augments aléatoires**.
- Chaque augment proposé peut être **relancé une seule fois** (reroll individuel), puis le joueur sélectionne **1 augment final**.
- Une fois les sélections validées, la manche démarre avec les augments actifs.
- La condition de victoire d'une manche est la **capture du roi adverse**.
- Si une règle/augment introduit plusieurs rois, tous les rois requis doivent être capturés pour perdre.
- Chaque augment a une description claire de son effet et de sa durée (si activable).
- Les augments sont conçus pour être **équilibrés** et **interactifs**, favorisant des stratégies variées.
- les augments sont décits dans le fichier `docs/Rumble_augments.txt` et peuvent être modifiés/ajoutés au fil du développement.
- Les augments sont actives pour toutes les manches et donc se cumulent, car on en choisi un à chaque manche, mais on en perd jamais.
- Il est cependant impossible de pouvoir choisir 2 fois le même augment, une fois qu'on a choisi un augment, il n'est plus disponible dans les propositions d'augments pour les manches suivantes.
- Certaines augments sont incompatibles entre elles, par exemple : "transition" et "sexo-permutation" ne peuvent pas être actives en même temps, si un joueur a déjà l'une de ces augments, l'autre ne lui sera jamais proposée.
#### Augments activables

- Certaines augments sont activables manuellement et peuvent nécessiter une cible.
- La **touche de déclenchement** est choisie au moment de la sélection de l'augment.
- Si une cible est requise, la cible est la case de l'échiquier pointée par la souris au moment de l'activation.

#### Interface utilisateur Rumble

- L'échiquier est affiché au centre.
- Une sidebar à gauche et une sidebar à droite affichent le profil de chaque joueur et la liste de ses augments actifs.
- Le score est affiché sous forme de **3 pips en losange** par joueur (style cases d'échecs) qui se remplissent à chaque manche gagnée.
- Le remplissage des pips utilise des teintes d'or plus ou moins foncées.
- Quand les 3 pips d'un joueur sont remplis, la victoire de match est atteinte.
- L'échiquier Rumble utilise un code couleur distinct du mode Standard.

---

## Docker (serveur)

Le `docker-compose.yml` à la racine du projet qui orchestre :
- Le conteneur `app` — le serveur FastAPI/socketio
- Le volume persistant pour la base SQLite

Exemple de `docker-compose.yml` :

```yaml
version: "3.9"

services:
  app:
    build: ./server
    container_name: ninja-chess-server
    restart: unless-stopped
    ports:
      - "8200:8200"
    volumes:
      - ./server/data:/app/data        # Persistance de la base SQLite
      - ./server/uploads:/app/uploads  # Avatars uploadés
    env_file:
      - ./server/.env
```

En production, Nginx sur `parzizou.fr` fait office de reverse proxy vers le port 8200 et gère le SSL/TLS. Les WebSockets passent par `wss://ninja-chess.parzizou.fr`.

---

## Conventions de code

- **Python 3.11+** côté serveur ; JavaScript ES modules (sans framework ni build) côté client
- Tout texte venant d'un utilisateur (pseudo, nom de room) est inséré dans le DOM via `textContent` uniquement (jamais `innerHTML`)
- Type hints partout (`from __future__ import annotations` si besoin)
- Formatage : `black` + `isort`
- Linting : `ruff`
- Tests serveur : `pytest` + `httpx` pour les routes HTTP, `pytest-asyncio` pour les handlers async
- Les fichiers de logique pure (échecs, elo) doivent être testés indépendamment du reste

---

## Variables d'environnement (`.env` serveur)

```
SECRET_KEY=<clé JWT aléatoire>
DATABASE_URL=sqlite:////app/data/ninja_chess.db
ALLOWED_ORIGINS=https://ninja-chess.parzizou.fr
```

---

## Fonctionnalités prévues

### Implémentées (MVP)
- [x] Authentification (register/login/JWT)
- [x] "Rester connecté" (credentials.json local)
- [x] Rooms : création, liste, rejoindre
- [x] Mode Standard : échecs temps réel avec cooldowns (roque, en passant, promotion, revanche)
- [x] Classement Elo (Standard)
- [x] Profil joueur (stats, historique)
- [x] Avatar personnalisé (sélecteur de fichier + upload + affichage)
- [x] Mode solo contre l'IA (local, 3 difficultés, sans impact Elo)

### Implémentées (Rumble)
- [x] Mode Rumble : 44 augments, manches BO5, sélection avec reroll individuel
- [x] Classement Elo Rumble
- [x] Personnalisation des touches (actions Rumble, choisies à la sélection de l'augment)
- [x] Effets temporisés résolus par une boucle de tick serveur (`rumble:effects`)

### Prévues ultérieurement
- [ ] Spectateur de parties en cours
- [ ] Affichage de l'avatar dans les sidebars Rumble et le classement
- [ ] Tests automatisés (`pytest`) pour la logique d'échecs, l'Elo et les augments