# CLAUDE.md — Ninja Chess

Ce fichier sert de référence pour Claude (et tout développeur) travaillant sur ce projet. Il décrit l'architecture, le stack technique, les conventions et les décisions de conception.

---

## Vue d'ensemble du projet

**Ninja Chess** est un jeu d'échecs multijoueur en ligne et en temps réel. La principale particularité est que les deux joueurs peuvent bouger leurs pièces simultanément — il n'y a pas de tour par tour. Chaque pièce a un cooldown individuel après chaque mouvement.

Le projet est divisé en deux parties indépendantes :
- `server/` — serveur Python gérant la logique de jeu, les comptes, les rooms et la communication réseau
- `client/` — application Python compilée en `.exe` gérant l'affichage graphique et les interactions utilisateur

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

### Client (`client/`)

| Composant | Technologie | Raison |
|---|---|---|
| Affichage graphique | `arcade` | API moderne, animations 2D fluides, meilleure DX que pyglet brut |
| Communication réseau | `python-socketio[client]` | Cohérent avec le serveur, gère la reconnexion |
| Compilation | `PyInstaller` | Génération du `.exe` Windows |
| Stockage local | Fichier JSON (`credentials.json`) | Sauvegarde des identifiants pour "rester connecté" |

---

## Structure des dossiers

```
ninja-chess/
├── CLAUDE.md
├── README.md
├── client/
│   ├── assets/
│   │   └── sprites/          # Sprites PNG des pièces (ex: white_king.png, black_pawn.png)
│   ├── screens/              # Écrans du jeu (login, home, game, leaderboard, profile)
│   ├── components/           # Composants réutilisables (boutons, inputs, pièces)
│   ├── utils/
│   │   ├── socket_client.py  # Connexion et événements socketio
│   │   └── credentials.py    # Lecture/écriture du fichier JSON local
│   ├── main.py               # Point d'entrée du client
│   ├── requirements.txt
│   └── ninja-chess.spec      # Config PyInstaller
└── server/
    ├── app/
    │   ├── main.py           # Point d'entrée FastAPI + socketio
    │   ├── routers/          # Routes HTTP (auth, users, leaderboard)
    │   ├── events/           # Handlers socketio (rooms, game, moves)
    │   ├── models/           # Modèles SQLAlchemy (User, Game, Move)
    │   ├── schemas/          # Schémas Pydantic (requêtes/réponses)
    │   ├── logic/            # Logique pure d'échecs (validation des coups, cooldowns, elo)
    │   └── database.py       # Initialisation SQLAlchemy + session
    ├── alembic/              # Migrations de base de données
    ├── docker-compose.yml
    ├── Dockerfile
    ├── requirements.txt
    └── .env                  # Variables d'environnement (SECRET_KEY, DATABASE_URL, etc.)
```

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
| Pion | 1 s |
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

- Le premier joueur à gagner **4 manches** remporte la partie (format BO7).
- Avant chaque manche, chaque joueur reçoit **3 augments aléatoires**.
- Chaque augment proposé peut être **relancé une seule fois** (reroll individuel), puis le joueur sélectionne **1 augment final**.
- Une fois les sélections validées, la manche démarre avec les augments actifs.
- La condition de victoire d'une manche est la **capture du roi adverse**.
- Si une règle/augment introduit plusieurs rois, tous les rois requis doivent être capturés pour perdre.
- Chaque augment a une description claire de son effet et de sa durée (si activable).
- Les augments sont conçus pour être **équilibrés** et **interactifs**, favorisant des stratégies variées.
- les augments sont décits dans le fichier `client/Rumble_augments.txt` et peuvent être modifiés/ajoutés au fil du développement.
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
- Le score est affiché dans un losange composé de **4 carrés** (style cases d'échecs) qui se remplissent à chaque manche gagnée.
- Le remplissage des carrés utilise des teintes d'or plus ou moins foncées.
- Quand les 4 carrés sont remplis, la victoire de match est atteinte.
- L'échiquier Rumble utilise un code couleur distinct du mode Standard.

---

## Docker (serveur)

Le dossier `server/` contient un `docker-compose.yml` qui orchestre :
- Le conteneur `app` — le serveur FastAPI/socketio
- Le volume persistant pour la base SQLite

Exemple de `docker-compose.yml` :

```yaml
version: "3.9"

services:
  app:
    build: .
    container_name: ninja-chess-server
    restart: unless-stopped
    ports:
      - "8200:8200"
    volumes:
      - ./data:/app/data        # Persistance de la base SQLite
      - ./uploads:/app/uploads  # Avatars uploadés
    env_file:
      - .env
```

En production, Nginx sur `parzizou.fr` fait office de reverse proxy vers le port 8200 et gère le SSL/TLS. Les WebSockets passent par `wss://ninja-chess.parzizou.fr`.

---

## Conventions de code

- **Python 3.11+** sur serveur et client
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
- [ ] Authentification (register/login/JWT)
- [ ] "Rester connecté" (credentials.json local)
- [ ] Rooms : création, liste, rejoindre
- [ ] Mode Standard : échecs temps réel avec cooldowns
- [ ] Classement Elo (Standard)
- [ ] Profil joueur (stats, historique)
- [ ] Avatar personnalisé

### Prévues ultérieurement
- [ ] Mode Rumble (règles spéciales, power-ups)
- [ ] Classement Elo Rumble
- [ ] Personnalisation des touches (actions Rumble)
- [ ] Spectateur de parties en cours