# Requirements Document

## Introduction

Cette feature introduit TomTom comme provider géographique corollaire dans MAPNET, un système de cartographie centré sur le Cameroun. Elle couvre deux phases distinctes :

- **Phase 0 — Geocoding** : ajout de `TomTomGeocodingProvider` et `NominatimProvider` derrière une abstraction commune `GeocodingProvider`, contrats de domaine MAPNET (`GeoResult`, `Address`), endpoint `/api/v1/places/geocode`, et benchmark symétrique TomTom/Nominatim sur corpus Cameroun.
- **Phase 1 — Routing** : ajout de `TomTomRoutingProvider` comme troisième moteur de routage (`engine=tomtom`) derrière l'abstraction `RoutingProvider`, avec contrats de domaine MAPNET (`Route`, `Step`, `ProviderMeta`).

Dans les deux phases, TomTom est un **provider corollaire** — il coexiste avec les providers OSM existants (Overpass, OSRM, Valhalla) sans les remplacer. Les clients existants ne constatent aucun changement de comportement. Les fichiers `overpass_client.py`, `osrm_client.py`, `valhalla_client.py` et le schéma PostGIS restent inchangés.

---

## Glossaire

- **GeocodingProvider** : interface abstraite (`ABC`) commune à tous les providers de géocodage MAPNET.
- **RoutingProvider** : interface abstraite (`ABC`) commune à tous les providers de routage MAPNET.
- **GeoResult** : structure de données normalisée MAPNET représentant un résultat géographique (coordonnées + adresse + métadonnées provider).
- **Address** : structure de données MAPNET représentant une adresse normalisée, indépendante du provider.
- **Route** : structure de données normalisée MAPNET représentant un itinéraire (distance, durée, géométrie, étapes).
- **Step** : une étape de navigation dans une Route (instruction, manœuvre, localisation, distance, durée).
- **ProviderMeta** : métadonnées sur le provider utilisé pour calculer une Route (provider, trafic, fraîcheur des données, fallback).
- **TomTomGeocodingProvider** : implémentation de `GeocodingProvider` utilisant l'API TomTom Search v2.
- **NominatimProvider** : implémentation de `GeocodingProvider` utilisant l'API Nominatim/OpenStreetMap. En Phase 0, ce provider est introduit exclusivement pour le benchmark symétrique TomTom/Nominatim. Il n'est pas utilisé par `provider=auto` dans cette phase.
- **TomTomRoutingProvider** : implémentation de `RoutingProvider` utilisant l'API TomTom Routing v1.
- **GeocodingService** : orchestrateur des `GeocodingProvider` dans `services/places`.
- **RoutingService** : orchestrateur des `RoutingProvider` dans `services/routing`.
- **ProviderError** : hiérarchie d'exceptions MAPNET représentant les erreurs d'un provider géographique.
- **mapnet_confidence** : score de confiance calculé par MAPNET (0.0–1.0), heuristique non calibrée, propre à MAPNET et non comparable entre providers.
- **provider_confidence** : score brut retourné par le provider (ex. score TomTom), non comparable entre providers distincts.
- **Benchmark Cameroun** : procédure de mesure symétrique TomTom/Nominatim sur un corpus structuré d'environ 250 requêtes géographiques camerounaises.
- **Corpus Cameroun** : fichier JSON structuré par axes expérimentaux (géographique, linguistique, toponymique, type de requête) avec ground truth.
- **TOMTOM_API_KEY** : variable d'environnement contenant la clé d'API TomTom, injectée dans le conteneur.
- **Services/places** : microservice FastAPI gérant les lieux, POI et le géocodage dans MAPNET.
- **Services/routing** : microservice FastAPI gérant le calcul d'itinéraires dans MAPNET.

---

## Requirements

### Requirement 1 — Hiérarchie d'erreurs provider

**User Story :** En tant que développeur MAPNET, je veux une hiérarchie d'exceptions standardisée pour tous les providers géographiques, afin que les erreurs soient classifiables, loggables et gérables de manière uniforme entre geocoding et routing.

#### Acceptance Criteria

1. THE GeocodingService SHALL définir une classe de base `ProviderError` dont héritent `ProviderAuthError`, `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderTemporaryUnavailable`, `ProviderNoResult` et `ProviderResponseError`.
2. THE RoutingService SHALL posséder une hiérarchie `ProviderError` localement compatible avec celle du GeocodingService : mêmes noms de classes, même sémantique, même logique de retry. La duplication dans chaque service est la méthode retenue pour conserver l'isolation microservice.
3. WHEN le TomTomGeocodingProvider reçoit une réponse HTTP 401 ou 403, THE TomTomGeocodingProvider SHALL lever `ProviderAuthError` sans effectuer de retry.
4. WHEN le TomTomGeocodingProvider reçoit une réponse HTTP 429, THE TomTomGeocodingProvider SHALL lever `ProviderRateLimitError` sans effectuer de retry.
5. WHEN le TomTomGeocodingProvider reçoit une réponse HTTP 5xx, THE TomTomGeocodingProvider SHALL lever `ProviderTemporaryUnavailable` après épuisement du nombre de retries configuré.
6. WHEN le TomTomGeocodingProvider ne reçoit pas de réponse dans le délai configuré, THE TomTomGeocodingProvider SHALL lever `ProviderTimeoutError` après épuisement du nombre de retries configuré.
7. WHEN un provider retourne une structure de réponse dont le parsing échoue, THE GeocodingService SHALL lever `ProviderResponseError` plutôt que propager une exception non classifiée.
8. IF le TomTomGeocodingProvider lève `ProviderAuthError` ou `ProviderRateLimitError`, THEN THE GeocodingService SHALL logger l'erreur au niveau ERROR sans exposer le détail HTTP dans la réponse FastAPI au client.

---

### Requirement 2 — Contrats de domaine geocoding (Phase 0)

**User Story :** En tant que développeur MAPNET, je veux des structures de données normalisées `GeoResult` et `Address` indépendantes de tout provider, afin que le reste de MAPNET manipule un contrat stable quel que soit le provider actif.

#### Acceptance Criteria

1. THE GeocodingService SHALL définir une structure `Address` contenant les champs : `display_name` (obligatoire), `street`, `city`, `region`, `country`, `postcode` (tous optionnels).
2. THE GeocodingService SHALL définir une structure `GeoResult` contenant les champs : `latitude`, `longitude`, `address` (type `Address`), `provider` (nom du provider), `mapnet_confidence` (float 0.0–1.0), `provider_confidence` (optionnel), `distance_m` (optionnel), `source_id` (optionnel), `raw` (optionnel, non exposé dans les réponses API).
3. THE GeocodingService SHALL calculer `mapnet_confidence` selon les critères MAPNET, indépendamment du score brut du provider.
4. THE GeocodingService SHALL conserver `provider_confidence` comme valeur brute du provider, distincte et non comparée à `mapnet_confidence`.
5. WHEN le TomTomGeocodingProvider normalise un résultat de type `PointAddress`, THE TomTomGeocodingProvider SHALL produire un `GeoResult` avec un score de base `mapnet_confidence` égal à 0.90, avant application des bonus optionnels d'adresse et de pays.
6. WHEN le TomTomGeocodingProvider normalise un résultat de type `Country`, THE TomTomGeocodingProvider SHALL produire un `GeoResult` avec `mapnet_confidence` égal à 0.30, sans application d'aucun bonus. Les bonus d'adresse et de pays ne s'appliquent pas au type `Country`.
7. THE GeocodingService SHALL ne jamais exposer le champ `raw` d'un `GeoResult` dans une réponse HTTP retournée au client.

---

### Requirement 3 — GeocodingProvider : interface et implémentations (Phase 0)

**User Story :** En tant que développeur MAPNET, je veux une interface abstraite `GeocodingProvider` avec des implémentations TomTom et Nominatim, afin que les providers soient interchangeables derrière le même contrat.

#### Acceptance Criteria

1. THE GeocodingService SHALL définir une interface `GeocodingProvider` avec les méthodes abstraites `geocode(query, limit, lat, lon) -> List[GeoResult]` et `reverse_geocode(lat, lon) -> Optional[GeoResult]`.
2. THE TomTomGeocodingProvider SHALL implémenter `GeocodingProvider` et appeler l'endpoint TomTom Search v2 fuzzy search pour la méthode `geocode`.
3. THE TomTomGeocodingProvider SHALL implémenter `GeocodingProvider` et appeler l'endpoint TomTom Search v2 reverseGeocode pour la méthode `reverse_geocode`.
4. THE NominatimProvider SHALL implémenter `GeocodingProvider` avec les mêmes signatures de méthodes que le TomTomGeocodingProvider.
5. WHEN le TomTomGeocodingProvider est instancié, THE TomTomGeocodingProvider SHALL lire la clé d'API depuis la variable d'environnement `TOMTOM_API_KEY`.
6. IF la variable d'environnement `TOMTOM_API_KEY` est absente ou vide au moment de l'instanciation du TomTomGeocodingProvider, THEN THE TomTomGeocodingProvider SHALL lever `ProviderAuthError` immédiatement.
7. THE TomTomGeocodingProvider SHALL encoder la requête de géocodage avec `urllib.parse.quote` (RFC 3986) avant insertion dans le chemin URL.
8. WHEN le TomTomGeocodingProvider effectue un reverse geocoding, THE TomTomGeocodingProvider SHALL parser le champ `position` de la réponse en acceptant les deux formes : chaîne `"lat,lon"` et dictionnaire `{"lat": ..., "lon": ...}`.
9. IF le champ `position` d'une réponse TomTom reverse geocoding ne peut pas être parsé, THEN THE TomTomGeocodingProvider SHALL lever `ProviderResponseError` plutôt que retourner des coordonnées `0.0, 0.0`.
10. THE TomTomGeocodingProvider SHALL biaiser les requêtes de géocodage vers le Cameroun en passant `countrySet=CMR` et `language=fr-FR` dans les paramètres de l'API TomTom.
11. THE TomTomGeocodingProvider SHALL créer un client HTTP réutilisable à l'instanciation et le réutiliser pour toutes les requêtes, avec exposition d'une méthode `close()` et support du protocol context manager.
12. WHEN le TomTomGeocodingProvider effectue une requête HTTP, THE TomTomGeocodingProvider SHALL appliquer un timeout configurable (valeur par défaut 10.0 secondes) et un nombre de retries configurable (valeur par défaut 2) pour les erreurs retriables.

---

### Requirement 4 — Endpoint `/api/v1/places/geocode` (Phase 0)

**User Story :** En tant que client de l'API MAPNET, je veux un endpoint de géocodage unifié avec sélection de provider, afin d'obtenir des résultats géographiques enrichis tout en conservant un fallback PostGIS fiable.

#### Acceptance Criteria

1. THE Services/places SHALL exposer un endpoint GET `/api/v1/places/geocode` acceptant les paramètres : `q` (requis), `lat` (optionnel), `lon` (optionnel), `provider` (optionnel, valeurs : `auto`, `tomtom`, `local`, valeur par défaut `auto`).
2. WHEN le paramètre `provider=tomtom` est fourni et que le TomTomGeocodingProvider est disponible et répond sans erreur, THE Services/places SHALL retourner les résultats TomTom normalisés sans fallback.
3. WHEN le paramètre `provider=local` est fourni, THE Services/places SHALL retourner les résultats de la recherche PostGIS existante sans appeler TomTom.
4. WHEN le paramètre `provider=auto` est fourni et que le TomTomGeocodingProvider est disponible et répond sans erreur, THE Services/places SHALL retourner les résultats TomTom avec `"provider": "tomtom"` et `"fallback_used": false`.
5. WHEN le paramètre `provider=auto` est fourni et que le TomTomGeocodingProvider lève `ProviderError`, THE Services/places SHALL basculer sur la recherche PostGIS et retourner `"provider": "local"` et `"fallback_used": true`.
6. WHEN le paramètre `provider=tomtom` est fourni et que le TomTomGeocodingProvider lève `ProviderError`, THE Services/places SHALL retourner HTTP 502 sans basculer sur PostGIS.
6b. WHEN le paramètre `provider=tomtom` est fourni et que le TomTomGeocodingProvider n'a pas été instancié (clé absente au démarrage), THE Services/places SHALL retourner HTTP 502 avec le message `"TomTom geocoding non disponible"`.
7. THE Services/places SHALL retourner une réponse JSON incluant les champs `status`, `provider`, `fallback_used` et `results` pour toute requête au endpoint `/api/v1/places/geocode`.
8. THE Services/places SHALL initialiser le TomTomGeocodingProvider de manière optionnelle au démarrage : si `TOMTOM_API_KEY` est absente, THE Services/places SHALL continuer à démarrer normalement et ignorer TomTom.
9. THE Services/places SHALL ne pas modifier les signatures, comportements ou réponses des endpoints existants (`/search`, `/nearby`, `/nearest-district`, `/by-category`, `/building-at`, `/status`, `/categories`, `/layer-counts`).

---

### Requirement 5 — Benchmark symétrique Cameroun (Phase 0)

**User Story :** En tant qu'architecte MAPNET, je veux un benchmark reproductible et symétrique comparant TomTom et Nominatim sur des requêtes camerounaises réelles, afin de prendre une décision d'intégration fondée sur des mesures objectives.

#### Acceptance Criteria

1. THE GeocodingService SHALL fournir un script `scripts/benchmark_geocoding.py` qui exécute le benchmark de manière symétrique : les deux providers reçoivent exactement les mêmes requêtes dans le même ordre.
2. THE GeocodingService SHALL fournir un fichier corpus `scripts/corpus_cameroun.json` contenant environ 250 requêtes structurées par axes : géographique (`urbain_yaounde`, `urbain_douala`, `secondaire`, `rural`), linguistique (`francophone`, `anglophone`), toponymique (`nom_officiel`, `variante_ortho`, `nom_local`) et type de requête (`poi`, `adresse_formelle`, `adresse_informelle`, `reverse`).
3. THE GeocodingService SHALL associer à chaque entrée du corpus les champs : `query`, `tags` (liste des axes), `ground_truth` (coordonnées vérifiées ou `null`), `manual_evaluation` (résultat d'évaluation manuelle ou `null`).
4. WHEN le benchmark traite une requête avec `ground_truth` non nul, THE GeocodingService SHALL calculer `distance_gt_m` par formule haversine et déduire `lat_ok` selon la tolérance définie dans le champ `ground_truth_tolerance_m` de l'entrée corpus. Si ce champ est absent, la tolérance par défaut est : 100 m pour les requêtes tagguées `urbain_*`, 250 m pour les requêtes tagguées `secondaire`, 500 m pour les requêtes tagguées `rural`.
5. THE GeocodingService SHALL mesurer et enregistrer les métriques suivantes pour chaque requête et chaque provider : `result_found`, `top1_lat_ok` (premier résultat dans la tolérance), `top5_lat_ok` (au moins un des 5 premiers dans la tolérance avec son rang), `address_complete`, `city_correct`, `response_time_ms`, `mapnet_confidence`, `error`, `http_status`.
6. THE GeocodingService SHALL produire un fichier de résultats JSON détaillé et afficher un résumé console par provider avec les métriques `result_found (%)`, `top1_lat_ok (%)`, `top5_lat_ok (%)`, `address_complete (%)`, latence moyenne, `latency_p50_ms`, `latency_p95_ms`, `http_429_count`, `http_5xx_count`, `timeout_count`.
7. THE GeocodingService SHALL préserver le champ `manual_evaluation` depuis le corpus vers les résultats, sans l'écraser, pour permettre l'évaluation post-benchmark des requêtes sans ground truth automatique.
8. WHEN le benchmark est exécuté, THE GeocodingService SHALL ne jamais comparer `mapnet_confidence` entre TomTom et Nominatim comme critère de décision, la comparaison étant réservée aux métriques `result_found`, `lat_ok` et `address_complete`.

---

### Requirement 6 — Contrats de domaine routing (Phase 1)

**User Story :** En tant que développeur MAPNET, je veux des structures de données normalisées `Route`, `Step` et `ProviderMeta` indépendantes de tout moteur de routage, afin que le reste de MAPNET manipule un contrat stable quel que soit le moteur actif.

#### Acceptance Criteria

1. THE RoutingService SHALL définir une structure `ProviderMeta` contenant les champs : `provider` (nom du moteur), `fallback_used` (bool, défaut false), `fallback_provider` (optionnel), `traffic` (bool, défaut false), `data_freshness` (chaîne : `"static"` ou `"realtime"`, défaut `"static"`).
2. THE RoutingService SHALL définir une structure `Step` contenant les champs : `instruction`, `maneuver`, `modifier`, `location` (liste `[lon, lat]`), `distance` (mètres), `duration` (secondes), `name` (chaîne, défaut vide).
3. THE RoutingService SHALL définir une structure `Route` contenant les champs : `distance` (mètres), `duration` (secondes), `geometry` (GeoJSON LineString), `steps` (liste de `Step`), `provider_meta` (optionnel), `badges` (dictionnaire, défaut vide).
4. THE RoutingService SHALL ne jamais normaliser les réponses TomTom vers le format OSRM ; la normalisation cible est exclusivement le contrat `Route` MAPNET.
5. WHEN le TomTomRoutingProvider produit une Route suite à un appel où `traffic=true` a été demandé à l'API TomTom, THE TomTomRoutingProvider SHALL renseigner `provider_meta.traffic = True` et `provider_meta.data_freshness = "realtime"` pour indiquer que le trafic a été demandé. Ces champs reflètent le paramètre de requête, pas une garantie que des données trafic temps réel étaient disponibles pour le tronçon calculé.

---

### Requirement 7 — RoutingProvider : interface et TomTomRoutingProvider (Phase 1)

**User Story :** En tant que développeur MAPNET, je veux une interface abstraite `RoutingProvider` avec une implémentation TomTom, afin que le moteur TomTom coexiste avec Valhalla et OSRM derrière le même contrat.

#### Acceptance Criteria

1. THE RoutingService SHALL définir une interface `RoutingProvider` avec les méthodes abstraites `route(from_lat, from_lon, to_lat, to_lon, costing) -> Route` et `available() -> bool`.
2. THE TomTomRoutingProvider SHALL implémenter `RoutingProvider` et appeler l'endpoint TomTom Routing v1 `calculateRoute` pour la méthode `route`.
3. WHEN le TomTomRoutingProvider est instancié avec `TOMTOM_API_KEY` absente ou vide, THE TomTomRoutingProvider SHALL retourner `available() = False` sans lever d'exception à l'instanciation.
4. THE TomTomRoutingProvider SHALL mapper les profils de costing MAPNET (`auto`, `car`, `motorcycle`, `bicycle`, `pedestrian`, `foot`) vers les modes TomTom correspondants (`car`, `motorcycle`, `bicycle`, `pedestrian`).
5. THE TomTomRoutingProvider SHALL construire la géométrie GeoJSON LineString de la Route MAPNET depuis les points des legs TomTom, avec des coordonnées au format `[longitude, latitude]` (ordre GeoJSON).
6. THE TomTomRoutingProvider SHALL construire les Steps de la Route MAPNET depuis les instructions de guidage TomTom (`guidance.instructions`).
7. WHEN le TomTomRoutingProvider reçoit une réponse TomTom sans routes, THE TomTomRoutingProvider SHALL lever `ProviderNoResult`.
8. WHEN le TomTomRoutingProvider reçoit une réponse HTTP 401 ou 403, THE TomTomRoutingProvider SHALL lever `ProviderAuthError` sans retry.
9. WHEN le TomTomRoutingProvider reçoit une réponse HTTP 429, THE TomTomRoutingProvider SHALL lever `ProviderRateLimitError` sans retry.
10. WHEN le TomTomRoutingProvider reçoit une réponse HTTP 5xx, THE TomTomRoutingProvider SHALL lever `ProviderTemporaryUnavailable`.
11. WHEN le TomTomRoutingProvider ne reçoit pas de réponse dans le délai configuré, THE TomTomRoutingProvider SHALL lever `ProviderTimeoutError`.

---

### Requirement 8 — Intégration engine=tomtom dans services/routing (Phase 1)

**User Story :** En tant que client de l'API MAPNET, je veux pouvoir sélectionner le moteur TomTom pour le calcul d'itinéraires via le paramètre `engine=tomtom`, afin d'obtenir un itinéraire intégrant le trafic temps réel.

#### Acceptance Criteria

1. THE Services/routing SHALL accepter `engine=tomtom` comme valeur valide du paramètre `engine` dans les endpoints de calcul d'itinéraire existants.
2. WHEN le paramètre `engine=tomtom` est fourni et que le TomTomRoutingProvider est disponible, THE Services/routing SHALL retourner l'itinéraire TomTom avec les champs `"engine": "tomtom"`, `"traffic": true` et `"data_freshness": "realtime"`.
3. WHEN le paramètre `engine=tomtom` est fourni et que le TomTomRoutingProvider lève `ProviderError`, THE Services/routing SHALL retourner HTTP 502 sans basculer sur Valhalla ou OSRM.
4. WHEN le paramètre `engine=auto` est fourni et que le TomTomRoutingProvider n'est pas disponible, THE Services/routing SHALL conserver le comportement existant (Valhalla puis OSRM en fallback) sans modification.
5. THE Services/routing SHALL ne pas modifier les comportements existants des paramètres `engine=valhalla` et `engine=osrm`.
6. THE Services/routing SHALL ne pas modifier les fichiers `osrm_client.py` et `valhalla_client.py`.
7. THE Services/routing SHALL initialiser le TomTomRoutingProvider de manière optionnelle : si `TOMTOM_API_KEY` est absente, THE Services/routing SHALL continuer à démarrer normalement avec les moteurs existants uniquement.

---

### Requirement 9 — Isolation et non-régression des providers existants

**User Story :** En tant qu'opérateur MAPNET, je veux garantir que l'ajout des providers TomTom n'affecte pas le fonctionnement des providers OSM existants, afin que le système reste opérationnel même sans clé TomTom.

#### Acceptance Criteria

1. THE Services/places SHALL fonctionner normalement sur tous les endpoints existants lorsque `TOMTOM_API_KEY` est absente de l'environnement.
2. THE Services/routing SHALL fonctionner normalement sur tous les endpoints existants lorsque `TOMTOM_API_KEY` est absente de l'environnement.
3. THE GeocodingService SHALL ne pas modifier le fichier `overpass_client.py`.
4. THE RoutingService SHALL ne pas modifier les fichiers `osrm_client.py` et `valhalla_client.py`.
5. THE GeocodingService SHALL ne pas modifier le schéma PostGIS (aucun `ALTER TABLE`, `CREATE TABLE`, `DROP TABLE`).
6. WHEN le TomTomGeocodingProvider est disponible mais retourne `ProviderNoResult` dans un contexte `provider=auto`, THE Services/places SHALL basculer sur la recherche PostGIS et retourner un résultat sans erreur HTTP.
7. THE Services/places SHALL ne pas modifier les signatures ni les contrats de réponse des endpoints `/search`, `/nearby`, `/nearest-district`, `/by-category`, `/building-at`, `/status`, `/categories` et `/layer-counts`.
