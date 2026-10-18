# Plan d'implémentation : `tomtom-provider-mapnet`

## Vue d'ensemble

Intégration de TomTom comme provider corollaire dans MAPNET en deux phases :
- **Phase 0 — Geocoding** : hiérarchie d'erreurs, contrats de domaine, providers (TomTom + Nominatim), `GeocodingService`, endpoint `/api/v1/places/geocode`, scripts benchmark.
- **Phase 1 — Routing** : contrats domaine routing, `TomTomRoutingProvider`, `RoutingService`, paramètre `engine=tomtom`.

Les fichiers `overpass_client.py`, `osrm_client.py`, `valhalla_client.py` et le schéma PostGIS ne sont jamais modifiés.

---

## Tâches

- [~] 1. Créer la hiérarchie d'erreurs `ProviderError` dans les deux services
  - Créer `services/places/app/errors.py` avec les 7 classes : `ProviderError`, `ProviderAuthError`, `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderTemporaryUnavailable`, `ProviderNoResult`, `ProviderResponseError`.
  - Créer `services/routing/app/errors.py` avec la même hiérarchie (duplication volontaire pour isolation microservice).
  - Chaque classe hérite correctement de la précédente dans la hiérarchie.
  - _Requirements: 1.1, 1.2_

- [ ] 2. Créer les contrats de domaine geocoding (`GeoResult`, `Address`)
  - [~] 2.1 Créer `services/places/app/domain/__init__.py` (vide) et `services/places/app/domain/geo_result.py`
    - Implémenter `Address` (dataclass) : `display_name` obligatoire, `street`, `city`, `region`, `country`, `postcode` optionnels.
    - Implémenter `GeoResult` (dataclass) : `latitude`, `longitude`, `address: Address`, `provider: str`, `mapnet_confidence: float = 0.0`, `provider_confidence: Optional[float] = None`, `distance_m: Optional[float] = None`, `source_id: Optional[str] = None`, `raw: Optional[dict] = field(default=None, repr=False)`.
    - _Requirements: 2.1, 2.2_

  - [ ]* 2.2 Écrire les tests unitaires pour `geo_result.py`
    - Tester l'instanciation de `Address` avec champs obligatoires uniquement.
    - Tester l'instanciation de `GeoResult` avec valeurs par défaut.
    - Vérifier que `raw` a `repr=False` (non visible dans `repr()`).
    - _Requirements: 2.1, 2.2_

- [ ] 3. Créer les contrats de domaine routing (`Route`, `Step`, `ProviderMeta`)
  - [~] 3.1 Créer `services/routing/app/domain/__init__.py` (vide) et `services/routing/app/domain/route.py`
    - Implémenter `ProviderMeta` (dataclass) : `provider: str`, `fallback_used: bool = False`, `fallback_provider: Optional[str] = None`, `traffic: bool = False`, `data_freshness: str = "static"`.
    - Implémenter `Step` (dataclass) : `instruction: str`, `maneuver: str`, `modifier: str`, `location: List[float]`, `distance: float`, `duration: float`, `name: str = ""`.
    - Implémenter `Route` (dataclass) : `distance: float`, `duration: float`, `geometry: dict`, `steps: List[Step] = field(default_factory=list)`, `provider_meta: Optional[ProviderMeta] = None`, `badges: dict = field(default_factory=dict)`.
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 3.2 Écrire les tests unitaires pour `route.py`
    - Tester l'instanciation de `ProviderMeta`, `Step`, `Route` avec valeurs par défaut.
    - Vérifier que `Route.steps` et `Route.badges` ne partagent pas de référence entre instances (default_factory).
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 4. Créer les interfaces abstraites `GeocodingProvider` et `RoutingProvider`
  - [~] 4.1 Créer `services/places/app/providers/__init__.py` (vide) et `services/places/app/providers/base.py`
    - Définir `GeocodingProvider(ABC)` avec attribut de classe `name: str` et méthodes abstraites `geocode(query, limit, lat, lon) -> List[GeoResult]` et `reverse_geocode(lat, lon) -> Optional[GeoResult]`.
    - _Requirements: 3.1_

  - [~] 4.2 Créer `services/routing/app/providers/__init__.py` (vide) et `services/routing/app/providers/base.py`
    - Définir `RoutingProvider(ABC)` avec attribut de classe `name: str` et méthodes abstraites `route(from_lat, from_lon, to_lat, to_lon, costing) -> Route` et `available() -> bool`.
    - _Requirements: 7.1_

- [ ] 5. Implémenter `TomTomGeocodingProvider`
  - [~] 5.1 Créer `services/places/app/providers/tomtom.py`
    - Lire `TOMTOM_API_KEY` depuis `os.environ` à l'instanciation ; lever `ProviderAuthError` si absente ou vide.
    - Créer un `httpx.Client` unique à l'instanciation ; exposer `close()` et le protocol context manager.
    - Paramètres configurables : `timeout: float = 10.0`, `max_retries: int = 2`.
    - Implémenter `geocode()` : encoder le query avec `urllib.parse.quote(query, safe="")`, appeler `https://api.tomtom.com/search/2/search/{encoded}.json` avec `countrySet=CMR`, `language=fr-FR`, normaliser via `_to_geo_result()`.
    - Implémenter `reverse_geocode()` : appeler `https://api.tomtom.com/search/2/reverseGeocode/{lat},{lon}.json`, normaliser via `_to_geo_result_reverse()` avec parsing défensif du champ `position` (str `"lat,lon"` ET dict `{"lat":..,"lon":..}`), lever `ProviderResponseError` si non parsable.
    - Implémenter `_get()` avec logique retry : 401/403 → `ProviderAuthError` (pas de retry) ; 429 → `ProviderRateLimitError` (pas de retry) ; 5xx → retry jusqu'à `max_retries` puis `ProviderTemporaryUnavailable` ; timeout → retry jusqu'à `max_retries` puis `ProviderTimeoutError`.
    - Calcul `mapnet_confidence` : scores par `entityType` (`PointAddress=0.90`, `POI=0.80`, `MunicipalitySubdivision=0.65`, `AddressRange=0.70`, `Street=0.60`, `Municipality=0.55`, `Country=0.30`, défaut=0.50). Bonus `+0.05` si rue+ville renseignés et `+0.05` si pays CM/CMR, plafonné à 1.0. **EXCEPTION : le type `Country` retourne toujours 0.30 sans aucun bonus** (garantit Property 7 : Country confidence = 0.30 exactement).
    - `provider_confidence` = `float(item["score"])` exactement (valeur brute TomTom).
    - `raw` non exposé : jamais inclus dans les dicts de réponse sérialisés vers HTTP.
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.3, 2.4, 2.5, 2.6, 2.7, 3.2, 3.3, 3.5, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12_

  - [ ]* 5.2 Écrire le test de propriété — Property 1 : Auth errors are never retried
    - **Property 1 : Auth errors are never retried**
    - Pour tout status HTTP dans {401, 403}, le client HTTP doit avoir été appelé exactement une fois (pas de retry), et `ProviderAuthError` doit être levée.
    - **Validates: Requirements 1.3**

  - [ ]* 5.3 Écrire le test de propriété — Property 2 : 5xx errors exhaust retries before raising
    - **Property 2 : 5xx errors exhaust retries before raising**
    - Pour tout status 5xx et tout `max_retries = n ≥ 0`, le provider doit effectuer exactement `n + 1` appels HTTP avant de lever `ProviderTemporaryUnavailable`.
    - **Validates: Requirements 1.5**

  - [ ]* 5.4 Écrire le test de propriété — Property 3 : Timeout errors exhaust retries before raising
    - **Property 3 : Timeout errors exhaust retries before raising**
    - Pour tout `max_retries = n ≥ 0`, si chaque appel HTTP lève `TimeoutException`, le provider doit effectuer exactement `n + 1` appels avant de lever `ProviderTimeoutError`.
    - **Validates: Requirements 1.6**

  - [ ]* 5.5 Écrire le test de propriété — Property 4 : Malformed position raises ProviderResponseError
    - **Property 4 : Malformed position raises ProviderResponseError**
    - Pour toute réponse reverse geocode avec un champ `position` non parsable (None, chaîne vide, chaîne malformée, mauvais type, clés dict manquantes), lever `ProviderResponseError` et ne jamais retourner `(0.0, 0.0)` silencieusement.
    - **Validates: Requirements 1.7, 3.9**

  - [ ]* 5.6 Écrire le test de propriété — Property 5 : mapnet_confidence is independent of provider_confidence
    - **Property 5 : mapnet_confidence is independent of provider_confidence**
    - Modifier `score` dans la réponse TomTom en gardant `entityType` et `address` constants doit produire le même `mapnet_confidence`.
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 5.7 Écrire le test de propriété — Property 6 : PointAddress confidence is always ≥ 0.85
    - **Property 6 : PointAddress confidence is always ≥ 0.85**
    - Pour tout item TomTom avec `entityType = "PointAddress"`, `GeoResult.mapnet_confidence` doit être ≥ 0.85.
    - **Validates: Requirements 2.5**

  - [ ]* 5.8 Écrire le test de propriété — Property 7 : Country confidence is always ≤ 0.35
    - **Property 7 : Country confidence is always ≤ 0.35**
    - Pour tout item TomTom avec `entityType = "Country"`, `GeoResult.mapnet_confidence` doit être ≤ 0.35.
    - **Validates: Requirements 2.6**

  - [ ]* 5.9 Écrire le test de propriété — Property 9 : Cameroon bias is always applied
    - **Property 9 : Cameroon bias is always applied**
    - Pour tout appel à `geocode()` avec n'importe quelle requête, les paramètres HTTP doivent toujours inclure `countrySet=CMR` et `language=fr-FR`.
    - **Validates: Requirements 3.10**

  - [ ]* 5.10 Écrire le test de propriété — Property 10 : URL encoding of geocode queries
    - **Property 10 : URL encoding of geocode queries**
    - Pour toute chaîne de requête, le chemin URL doit contenir `urllib.parse.quote(query, safe="")` (RFC 3986).
    - **Validates: Requirements 3.7**

  - [ ]* 5.11 Écrire le test de propriété — Property 11 : Reverse geocode position parsing is format-agnostic
    - **Property 11 : Reverse geocode position parsing is format-agnostic**
    - Pour toute paire `(lat, lon)` valide, une réponse avec `position` comme chaîne `"lat,lon"` et une réponse avec `position` comme dict `{"lat": lat, "lon": lon}` doivent produire des `GeoResult` avec des `latitude` et `longitude` identiques.
    - **Validates: Requirements 3.8**

  - [ ]* 5.12 Écrire le test de propriété — Property 12 : provider_confidence equals raw score exactly
    - **Property 12 : provider_confidence equals raw score exactly**
    - Pour tout item TomTom contenant un champ `score` de valeur `s`, `GeoResult.provider_confidence` doit être égal à `float(s)` exactement.
    - **Validates: Requirements 2.4**

  - [ ]* 5.13 Écrire le test de propriété — Property 8 : raw field never appears in API response
    - **Property 8 : raw field never appears in API response**
    - Pour tout `GeoResult` avec un champ `raw` non-None, la sérialisation vers le dict de réponse HTTP ne doit pas inclure de clé `"raw"` à aucun niveau d'imbrication.
    - **Validates: Requirements 2.7**

- [~] 6. Checkpoint — tests providers/tomtom.py (places)
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implémenter `NominatimProvider`
  - [~] 7.1 Créer `services/places/app/providers/nominatim.py`
    - Ce provider est introduit pour le benchmark uniquement. Il n'est PAS enregistré dans `provider=auto` du GeocodingService en Phase 0.
    - Implémenter `NominatimProvider(GeocodingProvider)` avec `name = "nominatim"`.
    - `geocode()` : appeler `{NOMINATIM_URL}/search` avec `q`, `format=jsonv2`, `countrycodes=cm` ; URL de base configurable via `NOMINATIM_URL` (défaut `https://nominatim.openstreetmap.org`).
    - `reverse_geocode()` : appeler `{NOMINATIM_URL}/reverse` avec `lat`, `lon`, `format=jsonv2`.
    - Normaliser vers `GeoResult` avec `provider="nominatim"` et `mapnet_confidence` calculée selon les champs `type`/`class` Nominatim (heuristique distincte de TomTom).
    - Respecter les règles de politesse Nominatim : header `User-Agent` obligatoire, délai minimal entre requêtes.
    - Lever les sous-classes `ProviderError` appropriées (mêmes sémantiques que TomTom).
    - _Requirements: 3.4_

  - [ ]* 7.2 Écrire les tests unitaires pour `NominatimProvider`
    - Tester `geocode()` et `reverse_geocode()` avec des réponses mockées.
    - Tester la normalisation vers `GeoResult` (champs obligatoires renseignés, `provider="nominatim"`).
    - Tester que `User-Agent` est toujours présent dans les requêtes HTTP.
    - _Requirements: 3.4_

- [ ] 8. Implémenter `GeocodingService`
  - [~] 8.1 Créer `services/places/app/geocoder.py`
    - Implémenter `GeocodingService.__init__(tomtom, nominatim, local_search: Callable)` — `local_search` est le callable PostGIS injecté depuis `main.py` (typiquement `search_places`). Pas de dépendance inverse GeocodingService → main.py.
    - Implémenter `geocode(query, provider, lat, lon) -> dict` avec la logique de sélection :
      - `provider="tomtom"` : TomTom uniquement. HTTP 502 si `ProviderError`. HTTP 502 si TomTom non instancié avec message générique.
      - `provider="local"` : appeler `self._local_search(q=query, lat=lat, lon=lon)`.
      - `provider="auto"` : TomTom si disponible, fallback PostGIS sur `ProviderError` (`fallback_used: true`). Sur `ProviderNoResult` avec `provider="auto"`, basculer vers PostGIS sans erreur HTTP.
    - Retourner toujours `{"status", "provider", "fallback_used", "results"}`.
    - Logger les erreurs TomTom au niveau ERROR sans exposer le détail HTTP dans la réponse.
    - _Requirements: 1.8, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 9.6_

  - [ ]* 8.2 Écrire le test de propriété — Property 18 : provider=auto TomTom fallback propagates correctly
    - **Property 18 : provider=auto TomTom fallback propagates correctly**
    - Pour toute sous-classe `ProviderError` levée par `TomTomGeocodingProvider` avec `provider="auto"`, l'endpoint doit retourner `"provider": "local"` et `"fallback_used": true` sans lever d'erreur HTTP.
    - **Validates: Requirements 4.5**

- [ ] 9. Modifier `services/places/app/main.py` — ajout minimal de `/api/v1/places/geocode`
  - [ ] 9.1 Ajouter l'initialisation optionnelle des providers et le nouvel endpoint dans `main.py`
    - Ajouter les imports : `TomTomGeocodingProvider`, `NominatimProvider`, `GeocodingService`, `ProviderAuthError`.
    - Ajouter les variables globales `_tomtom_geocoder` et `_nominatim_provider` initialisées à `None`.
    - Ajouter `_init_providers()` : instancier `TomTomGeocodingProvider()` avec try/except `ProviderAuthError` (log INFO si absente) ; instancier `NominatimProvider()`.
    - Ajouter l'event handler `@app.on_event("startup")` qui appelle `_init_providers()`.
    - Ajouter l'endpoint `GET /api/v1/places/geocode` avec paramètres `q`, `lat`, `lon`, `provider="auto"` ; déléguer à `GeocodingService(_tomtom_geocoder, _nominatim_provider, local_search=search_places)`.
    - Vérifier avant modification si `main.py` utilise déjà un handler `@app.on_event("startup")` ou un lifespan. Si oui, intégrer `_init_providers()` dans le mécanisme existant.
    - Ne modifier aucune des signatures ou réponses des endpoints existants.
    - _Requirements: 4.1, 4.8, 4.9, 9.1, 9.7_

  - [ ]* 9.2 Écrire le test de propriété — Property 21 : Existing endpoint response schemas are preserved
    - **Property 21 : Existing endpoint response schemas are preserved**
    - Pour chaque endpoint parmi `/search`, `/nearby`, `/nearest-district`, `/by-category`, `/building-at`, `/status`, `/categories`, `/layer-counts`, la réponse JSON doit contenir les mêmes clés de premier niveau qu'avant l'intégration TomTom.
    - **Validates: Requirements 9.7, 4.9**

- [ ] 10. Checkpoint — Phase 0 complète
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implémenter `TomTomRoutingProvider`
  - [ ] 11.1 Créer `services/routing/app/providers/tomtom.py`
    - Lire `TOMTOM_API_KEY` à l'instanciation ; si absente : `self._api_key = ""`, pas d'exception.
    - `available()` retourne `bool(self._api_key)`.
    - Mapping costing : `{"auto": "car", "car": "car", "motorcycle": "motorcycle", "bicycle": "bicycle", "pedestrian": "pedestrian", "foot": "pedestrian"}`.
    - `route()` : appeler `https://api.tomtom.com/routing/1/calculateRoute/{from_lat},{from_lon}:{to_lat},{to_lon}/json` avec `travelMode`, `traffic=true`, `language=fr-FR`, `instructionsType=text`, `routeRepresentation=polyline`.
    - Normaliser via `_normalize()` :
      - Géométrie : parcourir `routes[0].legs[].points[]`, construire `[[lon, lat], ...]` (ordre GeoJSON, jamais `[lat, lon]`).
      - Steps : parcourir `routes[0].guidance.instructions[]`, construire `Step` par instruction.
      - `ProviderMeta` : `provider="tomtom"`, `traffic=True`, `data_freshness="realtime"`.
      - Si `routes` vide : lever `ProviderNoResult`.
    - Gestion HTTP identique au provider geocoding (401/403 → `ProviderAuthError` sans retry ; 429 → `ProviderRateLimitError` sans retry ; 5xx → `ProviderTemporaryUnavailable` ; timeout → `ProviderTimeoutError`).
    - Ne jamais normaliser vers le format OSRM.
    - _Requirements: 6.4, 6.5, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11_

  - [ ]* 11.2 Écrire le test de propriété — Property 13 : TomTom routing metadata is always realtime
    - **Property 13 : TomTom routing metadata is always realtime**
    - Pour tout appel réussi à `TomTomRoutingProvider.route()` avec n'importe quelle origine/destination et costing, `Route.provider_meta.traffic` doit être `True` et `Route.provider_meta.data_freshness` doit être `"realtime"`.
    - **Validates: Requirements 6.5**

  - [ ]* 11.3 Écrire le test de propriété — Property 14 : Costing map covers all MAPNET profiles
    - **Property 14 : Costing map covers all MAPNET profiles**
    - Pour tout costing dans `{"auto", "car", "motorcycle", "bicycle", "pedestrian", "foot"}`, la requête HTTP doit utiliser le `travelMode` attendu selon la table de mapping.
    - **Validates: Requirements 7.4**

  - [ ]* 11.4 Écrire le test de propriété — Property 15 : GeoJSON coordinate order is [lon, lat]
    - **Property 15 : GeoJSON coordinate order is [lon, lat]**
    - Pour toute réponse TomTom avec des points de leg ayant des champs `latitude` et `longitude`, les coordonnées dans `Route.geometry.coordinates` doivent être dans l'ordre `[longitude, latitude]` (convention GeoJSON).
    - **Validates: Requirements 7.5**

  - [ ]* 11.5 Écrire le test de propriété — Property 16 : Step count matches instruction count
    - **Property 16 : Step count matches instruction count**
    - Pour toute réponse TomTom avec une liste `guidance.instructions` de longueur N, `Route.steps` doit avoir exactement N entrées.
    - **Validates: Requirements 7.6**

- [ ] 12. Implémenter `RoutingService`
  - [ ] 12.1 Créer `services/routing/app/router.py`
    - Implémenter `RoutingService.__init__(tomtom: Optional[TomTomRoutingProvider])`.
    - Implémenter `route(from_lat, from_lon, to_lat, to_lon, engine, costing) -> dict` :
      - `engine="tomtom"` : lever `HTTPException(502)` si `_tomtom is None` ; sinon appeler `_tomtom.route()`, lever `HTTPException(502)` sur `ProviderError` sans fallback.
      - `engine="auto"` : si TomTom non disponible, conserver le comportement Valhalla→OSRM existant (ne pas appeler TomTom).
      - `engine="valhalla"` / `engine="osrm"` : déléguer à l'existant, comportement inchangé.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [ ]* 12.2 Écrire le test de propriété — Property 17 : engine=tomtom errors return HTTP 502 without fallback
    - **Property 17 : engine=tomtom errors return HTTP 502 without fallback**
    - Pour toute sous-classe `ProviderError` levée par `TomTomRoutingProvider` avec `engine="tomtom"`, l'endpoint doit retourner HTTP 502 et ne doit pas invoquer Valhalla ou OSRM.
    - **Validates: Requirements 8.3**

- [ ] 13. Modifier `services/routing/app/main.py` — ajout minimal de `engine=tomtom`
  - [ ] 13.1 Ajouter l'initialisation optionnelle du provider et le cas `engine=tomtom` dans `main.py`
    - Ajouter les imports : `TomTomRoutingProvider`, `RoutingService`, `ProviderError` depuis `errors`.
    - Ajouter la variable globale `_tomtom_router` initialisée à `None`.
    - Ajouter l'event handler `@app.on_event("startup")` : instancier `TomTomRoutingProvider()`, affecter à `_tomtom_router` uniquement si `p.available()`.
    - Dans `calculate_route()`, ajouter le bloc `if engine == "tomtom":` avant la logique Valhalla/OSRM existante : retourner `{"status": "ok", "engine": "tomtom", "traffic": True, "data_freshness": "realtime", "routes": [...]}` ou HTTP 502 sur `ProviderError` avec message générique (jamais `str(exc)` dans le corps HTTP — les détails restent dans les logs).
    - Si TomTomRoutingProvider non instancié (clé absente) : HTTP 502 avec `"TomTom routing non disponible"`.
    - Ne pas modifier les blocs `engine=auto/valhalla/osrm` existants. Ne pas modifier `osrm_client.py` ni `valhalla_client.py`.
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 9.2, 9.4_

- [ ] 14. Checkpoint — Phase 1 complète
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Créer le corpus benchmark Cameroun
  - [ ] 15.1 Créer `scripts/corpus_cameroun.json`
    - Créer un fichier JSON de ~250 entrées structurées par axes :
      - Géographique : `urbain_yaounde`, `urbain_douala`, `secondaire`, `rural`.
      - Linguistique : `francophone`, `anglophone`.
      - Toponymique : `nom_officiel`, `variante_ortho`, `nom_local`.
      - Type : `poi`, `adresse_formelle`, `adresse_informelle`, `reverse`.
    - Chaque entrée contient : `query`, `tags` (liste), `ground_truth` (`{"lat", "lon"}` ou `null`), `ground_truth_tolerance_m` (int ou `null`), `manual_evaluation` (objet ou `null`).
    - Tolérances par défaut si champ absent : `urbain_*` → 100 m, `secondaire` → 250 m, `rural` → 500 m.
    - _Requirements: 5.2, 5.3_

  - [ ]* 15.2 Écrire le test de propriété — Property 20 : Corpus entries have required fields
    - **Property 20 : Corpus entries have required fields**
    - Pour toute entrée dans `corpus_cameroun.json`, l'entrée doit contenir les clés `query`, `tags`, `ground_truth` et `manual_evaluation`.
    - **Validates: Requirements 5.3**

- [ ] 16. Créer le script de benchmark `benchmark_geocoding.py`
  - [ ] 16.1 Créer `scripts/benchmark_geocoding.py`
    - Exécuter le benchmark de manière symétrique : TomTom et Nominatim reçoivent exactement les mêmes requêtes dans le même ordre.
    - Métriques par requête et par provider : `result_found`, `top1_lat_ok`, `top5_lat_ok` (+ champ `top5_rank`), `address_complete`, `city_correct`, `response_time_ms`, `distance_gt_m`, `error`, `http_status`.
    - Calculer `distance_gt_m` par haversine ; utiliser `ground_truth_tolerance_m` de l'entrée corpus pour `top1_lat_ok`.
    - Protocole : warm-up de 5 requêtes, puis alternance TomTom q_i / Nominatim q_i pour réduire le biais temporel de latence.
    - Résumé console : `result_found (%)`, `top1_lat_ok (%)`, `top5_lat_ok (%)`, `address_complete (%)`, `latency_mean_ms`, `latency_p50_ms`, `latency_p95_ms`, `http_429_count`, `http_5xx_count`, `timeout_count` par provider.
    - Ne jamais comparer `mapnet_confidence` entre providers distincts comme critère de décision.
    - Préserver `manual_evaluation` depuis le corpus vers les résultats sans l'écraser.
    - _Requirements: 5.1, 5.4, 5.5, 5.6, 5.7, 5.8_

  - [ ]* 16.2 Écrire le test de propriété — Property 19 : Haversine distance and threshold are consistent
    - **Property 19 : Haversine distance and threshold are consistent**
    - Pour tout couple de coordonnées `(rlat, rlon)` et `(gtlat, gtlon)` et toute entrée corpus avec `ground_truth_tolerance_m = t`, `distance_gt_m` doit être la distance haversine entre les deux points, et `top1_lat_ok` doit être `distance_gt_m ≤ t`. Valider aussi les tolérances par défaut (100/250/500 m) quand `ground_truth_tolerance_m` est absent.
    - **Validates: Requirements 5.4**

- [ ] 17. Checkpoint final — Ensemble de la feature
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Les tâches marquées `*` sont optionnelles et peuvent être ignorées pour un MVP rapide.
- Chaque tâche référence les requirements spécifiques pour la traçabilité.
- Les checkpoints valident la progression incrémentale.
- Les tests de propriétés (Hypothesis) utilisent des mocks HTTP — aucun appel réseau réel.
- Les tests unitaires classiques valident les exemples spécifiques et les cas limites.
- La hiérarchie `ProviderError` est dupliquée volontairement dans les deux services (isolation microservice).

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1", "4.2"] },
    { "id": 2, "tasks": ["2.2", "3.2", "5.1"] },
    { "id": 3, "tasks": ["5.2", "5.3", "5.4", "5.5", "5.6", "5.7", "5.8", "5.9", "5.10", "5.11", "5.12", "5.13", "7.1"] },
    { "id": 4, "tasks": ["6", "7.2", "8.1"] },
    { "id": 5, "tasks": ["8.2", "9.1"] },
    { "id": 6, "tasks": ["9.2", "10"] },
    { "id": 7, "tasks": ["11.1"] },
    { "id": 8, "tasks": ["11.2", "11.3", "11.4", "11.5", "12.1"] },
    { "id": 9, "tasks": ["12.2", "13.1"] },
    { "id": 10, "tasks": ["14", "15.1"] },
    { "id": 11, "tasks": ["15.2", "16.1"] },
    { "id": 12, "tasks": ["16.2", "17"] }
  ]
}
```

Notes :
- Les checkpoints (tâches 6, 10, 14, 17) bloquent les vagues suivantes.
- Phase 0 se termine à la vague 6 (checkpoint 10).
- Phase 1 commence à la vague 7 (11.1) après validation Phase 0.
- Le benchmark (15.x, 16.x) peut être lancé en parallèle de Phase 1 dès la vague 10.
