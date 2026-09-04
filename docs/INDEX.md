# MapNet Documentation Index

**Généré :** 30 juillet 2026  
**Version :** V2 (MVP Planning)

---

## 📋 Documents disponibles

### Pour les décideurs (non-technique)

**→ [`executive-summary.md`](executive-summary.md)** (11 KB, ~15 min lecture)
- Situation actuelle vs. Objectifs KPI
- 6 problèmes critiques identifiés
- Plan MVP 8 semaines (4 phases)
- Checklist déploiement + budget
- Risques & mitigations

**Pertinent pour :** Managers, Product Owners, Stakeholders

---

### Pour les architectes / Leads techniques

**→ [`diagnostic-problemes.md`](diagnostic-problemes.md)** (10 KB, ~20 min lecture)
- Deep dive : 6 problèmes techniques
- Audit du code source (mobile + backend)
- Calcul du taux sync réel (25%)
- Analyse causes racines
- Recommendations prioritaires

**Pertinent pour :** Tech leads, Architects, Senior devs

**→ [`mvp-feuille-route.md`](mvp-feuille-route.md)** (26 KB, ~1h lecture)
- Plan MVP détaillé (code + fichiers)
- 4 phases : Sync → Agents → Quartiers → Capteurs
- Changements par couche (mobile/serveur)
- Dépendances (packages Flutter/Python)
- Gantt + checklist acceptation
- Budget ressources

**Pertinent pour :** Tech leads, Sprint planners

---

### Pour les développeurs

**→ [`application-mobile.md`](application-mobile.md)** (13 KB, ~30 min lecture)
- Architecture Flutter/Dart complète
- Stack technologique justifié
- Services : GPS, Sync, Persistence
- Flux utilisateur complet
- Limitations & améliorations futures

**Pertinent pour :** Mobile devs Flutter/Dart

**→ [`carte-serveur.md`](carte-serveur.md)** (17 KB, ~35 min lecture)
- Architecture DDD Python backend
- 9 endpoints HTTP (REST API)
- Couches : Présentation, Application, Domaine, Infrastructure
- State machine captures (7 états)
- Quality pipeline (sensor fusion)
- Event bus (audit complet)

**Pertinent pour :** Backend devs Python, DDD enthusiasts

---

## 🎯 Chemins de lecture recommandés

### 📊 "Je veux comprendre le projet en 30 min"
1. `executive-summary.md` (5 min)
2. `diagnostic-problemes.md` Section "Résumé exécutif" (5 min)
3. `application-mobile.md` Section "Vue d'ensemble" (10 min)
4. `carte-serveur.md` Section "Vue d'ensemble" (10 min)

### 🛠 "Je dois implémenter le MVP"
1. `mvp-feuille-route.md` (50 min)
2. `diagnostic-problemes.md` (20 min)
3. Pour chaque phase :
   - Mobile → `application-mobile.md` (sections pertinentes)
   - Backend → `carte-serveur.md` (sections pertinentes)

### 🏗 "Je dois architector la solution"
1. `diagnostic-problemes.md` (20 min)
2. `mvp-feuille-route.md` (60 min)
3. `application-mobile.md` + `carte-serveur.md` (60 min)

### 🔍 "Je dois vérifier les détails techniques"
- Mobile : `application-mobile.md` (sections "Services", "Données")
- Backend : `carte-serveur.md` (sections "Domaine", "Infrastructure")
- Sync : `diagnostic-problemes.md` + `mvp-feuille-route.md` Phase 1

---

## 📊 Résumé des KPIs

| Métrique | Actuel | Cible MVP | Documents |
|----------|--------|-----------|-----------|
| Taux sync | 25% | >75% | Executive, Diagnostic, MVP Phase 1 |
| Agent visibility | 0% | 100% | Diagnostic, MVP Phase 2 |
| Quartiers indexés | 0% | 75% | Diagnostic, MVP Phase 3 |
| Capteurs réels | 0% | 100% | Diagnostic, MVP Phase 4 |
| État sync UI | 50% | 100% | MVP Phase 4 |

---

## 🔄 Structure MVP

```
Phase 1 (Semaines 1-2)
├─ Retry exponentiel
├─ Network detection réelle
└─ Idempotence serveur
    → Taux sync 25% → 75%+

Phase 2 (Semaines 2-3)
├─ Device tracking
├─ Heartbeat broadcast
└─ GeoJSON agents+captures
    → Agent visibility 0% → 100%

Phase 3 (Semaines 3-4)
├─ Nominatim reverse-geocoding
├─ Neighborhood indexing
└─ Frontend filter
    → Quartiers 0% → 75%

Phase 4 (Semaines 4-8)
├─ Compass réel (flutter_compass)
├─ IMU réel (sensors_plus)
├─ Pedometer (pedometer)
└─ UI transparence sync
    → Capteurs 0% → 100%
    → UI 50% → 100%
```

---

## 📚 Fichiers source clés

### Mobile (Flutter/Dart)

Fichiers mentionnés dans MVP :
- `mobile/lib/config/app_config.dart` — Config réseau + backoff
- `mobile/lib/services/sync_service.dart` — Logique sync (modifier Phase 1)
- `mobile/lib/services/gps_service.dart` — GPS réel (✓ existe)
- `mobile/lib/database/local_store.dart` — Persistance (ajouter sync_retries Phase 1)
- `mobile/lib/models/capture.dart` — Modèle capture (✓ existe)
- `mobile/lib/main.dart` — UI principale (ajouter capteurs Phase 4)

### Backend (Python)

Fichiers mentionnés dans MVP :
- `backend/presentation/server.py` — HTTP handlers (modifier Phase 1, 2)
- `backend/presentation/container.py` — Composition root (ajouter Device Phase 2)
- `backend/domain/entities.py` — Capture aggregate (ajouter Device + Neighborhood Phase 2-3)
- `backend/infrastructure/memory_repo.py` — Repo in-memory (ajouter DeviceSession Phase 2)
- `backend/domain/quality.py` — Pipeline qualité (utilisé Phase 4)

---

## 🎓 Concepts clés

### DDD (Domain-Driven Design)
→ `carte-serveur.md` Section "Architecture générale" + "Couches DDD"

### Offline-First / DTN
→ `application-mobile.md` Section "Flux utilisateur complet" + "Justifications"

### State machine captures
→ `carte-serveur.md` Section "State Machine" + "Events"

### Quality pipeline
→ `carte-serveur.md` Section "Quality Pipeline"

### Retry exponential
→ `mvp-feuille-route.md` Phase 1 Section "1.1"

### Reverse-geocoding
→ `mvp-feuille-route.md` Phase 3 Section "3.1"

---

## ✅ Checklist de lecture

### Pour démarrer le MVP
- [ ] Lire `executive-summary.md` (15 min)
- [ ] Lire `mvp-feuille-route.md` (60 min)
- [ ] Assigner Phase 1 à dev #1
- [ ] Assigner Phase 2-3 à dev #2
- [ ] Lancer Phase 4 semaine 4

### Avant chaque phase
- [ ] Relire la section Phase du MVP
- [ ] Lire fichiers source pertinents
- [ ] Faire code review des changements proposés
- [ ] Setup tests selon checklist acceptation

### Après chaque phase
- [ ] Mesurer KPI (taux sync, device count, etc.)
- [ ] Valider vs. checklist acceptation
- [ ] Go/No-Go pour phase suivante

---

## 📞 Contacts & Questions

**Problèmes détectés ?**
→ Refer to `diagnostic-problemes.md`

**Besoin détails MVP ?**
→ Refer to `mvp-feuille-route.md` Phase N

**Question architecture mobile ?**
→ Refer to `application-mobile.md`

**Question architecture backend ?**
→ Refer to `carte-serveur.md`

**Decision non-tech ?**
→ Refer to `executive-summary.md`

---

**Généré automatiquement — Toutes les sections markdown sont auto-contenues et cross-linkées.**
