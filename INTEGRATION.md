# MAPNET — Guide d'intégration microservice

> Ce document décrit MAPNET **en tant que microservice consommable** par
> d'autres projets (livraison, VTC/hub, immobilier, gestion de flotte…).
> Pour le déploiement de MAPNET lui-même, voir `DEPLOYMENT.md`.
> Pour la cartographie exacte des ports, voir `PORTS.md` (source de vérité).

## 1. Ce que MAPNET est, et ce qu'il n'est pas

MAPNET est une **plateforme géospatiale** : collecte de traces GPS terrain,
construction d'un graphe routier, calcul d'itinéraire, et suivi de position
d'agents. Il est déjà découpé en microservices indépendants (Go + Python),
orchestrés par un gateway.

**Ce n'est pas** un système de gestion de commandes, de facturation, ni un
CRM. MAPNET répond à « où » et « comment y aller » ; le métier reste chez le
consommateur.

## 2. Architecture réelle (vérifiée dans le dépôt)

```
                        ┌──────────────────────┐
   APK mobile  ────────►│  backend DDD  :8088  │  entrée unique mobile
                        │  Python stdlib       │
                        └───────┬──────────────┘
                                │
   client web  ────────► ┌──────▼────────┐
                         │ gateway :8080 │  Go — routage d'API
                         └───┬───┬───┬───┘
              ┌──────────────┘   │   └──────────────┐
              ▼                  ▼                  ▼
    ┌──────────────────┐ ┌──────────────┐ ┌──────────────────┐
    │ gps-collect :8095│ │ routing :8093│ │ map-engine :8096 │
    │ Go               │ │ FastAPI/OSRM │ │ Go               │
    └────────┬─────────┘ └──────────────┘ └────────┬─────────┘
             │                                     │
             ▼                                     ▼
    ┌──────────────────┐              ┌────────────────────────┐
    │ Kafka      :9092 │              │ Postgres/PostGIS :5432 │
    │ quamtechs.mapnet │              │ quamtechs_db           │
    │ .gps.raw         │              │ mapnet_edges,          │
    └──────────────────┘              │ gpx_traces,            │
                                      │ agent_positions        │
                                      └────────────────────────┘
```

Services présents dans `services/` : `api-gateway` (Kong), `auth`,
`ccaa-compliance`, `gateway`, `gps-collect`, `map-engine`, `mobile-client`,
`places`, `routing`, `web-frontend`.

Le backend suit un découpage DDD (`backend/domain/` contient `entities.py`,
`events.py`, `quality.py`, `schema.py`, `state_machine.py`), ce qui rend les
frontières de contexte explicites — utile pour l'intégration.

## 3. API à consommer

Les endpoints ci-dessous sont ceux documentés dans `PORTS.md`. **Vérifier
`/health` avant toute intégration** : les services évoluent.

### Itinéraire — `routing` (`:8093`)

```
POST /api/v1/routing/navigate
GET  /route
GET  /nearest
GET  /health
```

### Position et collecte — `gps-collect` (`:8095`)

```
POST /api/v1/collecte/gpx/upload      # upload d'une trace GPX
POST /api/v1/collecte/position        # ping de position d'un agent
GET  /api/v1/positions                # positions courantes
```

### Graphe et synchronisation — `map-engine` (`:8096`)

```
GET /api/v1/map/edges.geojson         # arêtes du graphe en GeoJSON
GET /api/v1/sync/manifest             # manifeste pour cache offline
GET /health
```

### Façade unifiée — `backend DDD` (`:8088`)

```
POST /api/captures
POST /api/routing/navigate
GET  /api/position
GET  /api/agents
```

### Via le gateway (`:8080`)

```
/api/gps/*    → 8095
/api/map/*    → 8096
/api/route/*  → 8093
```

**Recommandation d'intégration :** consommer le **gateway `:8080`** ou le
**backend `:8088`**, jamais les services internes directement. Cela préserve
la liberté de refactorer derrière.

## 4. Scénarios d'intégration par domaine

### 4.1 Livraison / logistique dernier kilomètre

| Besoin | Service MAPNET | Endpoint |
|---|---|---|
| Calculer la tournée | `routing` | `POST /api/v1/routing/navigate` |
| Suivre le livreur en direct | `gps-collect` | `POST /api/v1/collecte/position` |
| Afficher la flotte sur une carte | `backend DDD` | `GET /api/agents` |
| Carte utilisable hors-réseau | `map-engine` | `GET /api/v1/sync/manifest` |

Le point fort ici est le couple **Kafka + cache offline** : les positions
transitent par `quamtechs.mapnet.gps.raw`, donc un consommateur métier
(facturation à la distance, preuve de livraison, alerte de retard) s'abonne au
topic **sans coupler son code à MAPNET**. C'est le mode d'intégration à
privilégier pour la livraison.

### 4.2 Hub / VTC / transport de personnes

| Besoin | Service | Endpoint |
|---|---|---|
| Chauffeur le plus proche | `routing` | `GET /nearest` |
| ETA passager | `routing` | `GET /route` |
| Position temps réel | `gps-collect` | `GET /api/v1/positions` |

Attention : MAPNET ne gère ni l'appariement offre/demande, ni le paiement, ni
la tarification. Il fournit la distance et le temps ; la stratégie de matching
reste à écrire côté consommateur.

### 4.3 Immobilier (cf. `Immo-Artz`, `aura-loc`)

| Besoin | Service | Endpoint |
|---|---|---|
| Géocoder un bien | `places` | voir `services/places/app` |
| Temps de trajet vers écoles/commerces | `routing` | `GET /route` |
| Carte d'un quartier | `map-engine` | `GET /api/v1/map/edges.geojson` |

Usage le plus pertinent : **calculer l'accessibilité** d'un bien (temps réel
vers points d'intérêt) plutôt que la distance à vol d'oiseau. C'est un
différenciateur direct pour une annonce.

### 4.4 Autres services

- **Gestion scolaire** : itinéraires de ramassage, zones de desserte.
- **DataCenter-Edge** : `map-engine` sert déjà un manifeste de synchro,
  compatible avec un déploiement edge / faible connectivité.

## 5. Compatibilités et contraintes à connaître avant d'intégrer

| Contrainte | Détail | Impact |
|---|---|---|
| **HTTPS obligatoire pour la géoloc** | l'API Geolocation du navigateur exige un contexte sécurisé | en HTTP, prévoir le fallback « position par clic » (déjà implémenté) |
| **Zone de données** | graphe seedé depuis OSM sur Yaoundé (`scripts/seed_edges_osm.sh`) | toute autre ville nécessite un re-seed avant intégration |
| **Postgres/PostGIS requis** | tables `mapnet_edges`, `gpx_traces`, `agent_positions` | PostGIS n'est pas optionnel |
| **Kafka requis pour le flux** | topic `quamtechs.mapnet.gps.raw` | sans Kafka, seul le mode requête/réponse fonctionne |
| **Polyglotte** | Go (gateway, gps-collect, map-engine) + Python (routing, places, backend) | pas de build unique : `docker-compose.yml` est le chemin normal |
| **Auth** | `services/auth` et `services/api-gateway` (Kong) existent | à valider avant toute exposition publique — ne pas présumer que c'est câblé |
| **Conformité** | `services/ccaa-compliance` présent | pertinent si contrainte réglementaire aviation/locale |

## 6. Deux modes d'intégration

### Mode A — Requête/réponse (le plus simple)

Le consommateur appelle le gateway en HTTP. Couplage temporel : si MAPNET est
indisponible, l'appel échoue. Convient à l'immobilier et aux calculs d'ETA
ponctuels.

```
POST http://<host>:8080/api/route/...
```

### Mode B — Événementiel via Kafka (recommandé pour la livraison)

Le consommateur s'abonne à `quamtechs.mapnet.gps.raw`. Découplage complet :
MAPNET peut redémarrer sans perdre les messages, et le métier traite à son
rythme. C'est le mode à choisir dès qu'il y a du suivi de flotte.

## 7. Checklist avant d'intégrer MAPNET dans un projet

- [ ] `docker-compose.yml` démarre l'ensemble sans erreur
- [ ] `/health` répond sur `:8093` et `:8096`
- [ ] PostGIS accessible, les trois tables existent et sont peuplées
- [ ] Graphe seedé pour **la** zone géographique du projet cible
- [ ] Kafka joignable si le mode B est retenu
- [ ] Politique d'auth décidée et **vérifiée** (ne pas supposer)
- [ ] HTTPS en place si la géoloc navigateur est utilisée
- [ ] Consommation via `:8080` ou `:8088`, jamais les services internes

## 8. État actuel et limites de ce document

Ce document est une **synthèse d'intégration** établie depuis l'arborescence
du dépôt et `PORTS.md`. Ce qui est vérifié : la présence des services, le
découpage DDD, la liste des ports et endpoints, les contraintes HTTPS/OSM
documentées.

Ce qui **n'est pas** vérifié et doit l'être avant une mise en production
partagée : le comportement réel sous charge, le contrat d'authentification
effectif, la stabilité des schémas d'API, et l'existence de tests de contrat
entre services. `tests/` existe à la racine et dans `services/*/tests` —
leur couverture n'a pas été évaluée ici.

Prochaine étape recommandée pour l'industrialisation : figer les schémas
d'API (OpenAPI par service), ajouter des tests de contrat, et versionner les
endpoints (`/api/v1/` est déjà utilisé par une partie des services, pas par
tous — cette incohérence mérite d'être résolue avant d'exposer MAPNET à
plusieurs projets consommateurs).
