# Déploiement MapNet V2 sur GitHub

**Date :** 30 juillet 2026  
**Statut :** ✅ Complété  
**Branch :** `genspark_ai_developer`  
**Repo :** https://github.com/Cabrel10/Mapnet

---

## 📌 Ce qui a été poussé

### Commits GitHub

**3 commits :**

1. **`d28cbf2`** — Audit complet + plan MVP
   ```
   feat: MapNet V2 audit complet + plan MVP 8 semaines
   - 6 problèmes critiques identifiés (sync 25%, agents 0%, etc.)
   - MVP 4 phases (8 semaines, 120h)
   - 6 documents détaillés (2740 lignes)
   ```

2. **`87f7c3a`** — Instructions clonage local
   ```
   docs: Ajouter QUICK-START.md - Instructions clonage + setup local
   - 3 façons de cloner (Git, ZIP, GitHub Desktop)
   - Troubleshooting complet
   - Checklist installation
   ```

3. **`a588205`** — README mis à jour
   ```
   docs: README.md - Ajouter lien QUICK-START.md
   - Référence QUICK-START guide
   - Sections restructurées
   ```

### 📂 Fichiers créés/modifiés

**Créés (8 fichiers) :**
- ✅ `docs/INDEX.md` (8 KB) — Navigation guidée
- ✅ `docs/executive-summary.md` (12 KB) — Pour décideurs
- ✅ `docs/diagnostic-problemes.md` (12 KB) — Audit technique
- ✅ `docs/mvp-feuille-route.md` (28 KB) — Plan MVP détaillé
- ✅ `docs/application-mobile.md` (16 KB) — Architecture mobile
- ✅ `docs/carte-serveur.md` (20 KB) — Architecture backend
- ✅ `docs/QUICK-START.md` (8 KB) — Instructions clonage
- ✅ `README.md` (rewrite complet)

**Modifiés :**
- `backend/data/captures_snapshot.json` (non poussé, test data)

---

## 🔗 Comment récupérer la version localement

### Méthode rapide (Git)

```bash
# Clone le repo
git clone https://github.com/Cabrel10/Mapnet.git
cd Mapnet

# Vérifier branche
git branch -a

# Checkout branche V2 audit
git checkout genspark_ai_developer

# Vérifier fichiers docs/
ls docs/

# Output attendu :
# INDEX.md
# application-mobile.md
# carte-serveur.md
# diagnostic-problemes.md
# executive-summary.md
# mvp-feuille-route.md
# QUICK-START.md
# lettre-ccaa.md
```

### Méthode ZIP (snapshot)

```bash
# Télécharger ZIP de la branche
curl -L https://github.com/Cabrel10/Mapnet/archive/genspark_ai_developer.zip \
  -o Mapnet-v2.zip

# Extraire
unzip Mapnet-v2.zip
cd Mapnet-genspark_ai_developer

# Ou via navigateur :
# https://github.com/Cabrel10/Mapnet/archive/genspark_ai_developer.zip
```

### Mise à jour locale (déjà cloné)

```bash
cd Mapnet
git fetch origin
git pull origin genspark_ai_developer
```

---

## 📖 Structure des documents

### Point d'entrée
- **`docs/INDEX.md`** → Navigation par rôle
- **`README.md`** → Vue d'ensemble + liens

### Pour décideurs (15-30 min)
1. `README.md` sections KPI + Plan MVP
2. `docs/executive-summary.md` complet
3. `docs/QUICK-START.md` section "Récupérer"

### Pour tech (1-2 heures)
1. `docs/INDEX.md` → chemins recommandés
2. `docs/diagnostic-problemes.md` (6 problèmes + causes)
3. `docs/mvp-feuille-route.md` (phases détaillées + code)
4. `docs/application-mobile.md` (architecture mobile)
5. `docs/carte-serveur.md` (architecture backend)

### Pour devs (variable par phase)
- Mobile : `docs/application-mobile.md` + `mvp-feuille-route.md` sections mobile
- Backend : `docs/carte-serveur.md` + `mvp-feuille-route.md` sections backend
- QA : `docs/mvp-feuille-route.md` sections "Checklist acceptation"

---

## ✅ Vérifications complétées

### GitHub
- ✅ Commits poussés sur `genspark_ai_developer`
- ✅ Fichiers apparaissent dans le navigateur GitHub
- ✅ README affiche correctement sur la page du repo

### Documentation
- ✅ 6 docs audit + plan MVP (2740 lignes)
- ✅ INDEX.md navigation fonctionnelle
- ✅ QUICK-START.md troubleshooting complet
- ✅ Tous les liens inter-docs valides

### Local
- ✅ Fichiers .md bien créés (ls -la docs/)
- ✅ Git status clean après push
- ✅ Branch genspark_ai_developer à jour

---

## 🧭 Comment naviguer les docs

### Si vous êtes **décideur/PM** (30 min)
```
README.md
  ↓
docs/executive-summary.md
  ↓
Plan MVP (ci-dessous)
```

### Si vous êtes **tech lead** (2h)
```
docs/INDEX.md
  ↓
docs/diagnostic-problemes.md (20 min)
  ↓
docs/mvp-feuille-route.md (60 min)
  ↓
Assigner phases à équipe
```

### Si vous êtes **dev mobile** (2h)
```
docs/INDEX.md
  ↓
docs/application-mobile.md (30 min)
  ↓
docs/mvp-feuille-route.md Phase 1-4 (mobile sections)
  ↓
Commencer Phase 1 : app_config.dart + sync_service.dart
```

### Si vous êtes **dev backend** (2h)
```
docs/INDEX.md
  ↓
docs/carte-serveur.md (35 min)
  ↓
docs/mvp-feuille-route.md Phase 1-4 (backend sections)
  ↓
Commencer Phase 1 : server.py idempotence
```

---

## 📋 Plan MVP (référence)

### Phase 1 : Sync > 75% (Semaines 1-2)
**Fichiers :**
- `mobile/lib/config/app_config.dart` → backoff config
- `mobile/lib/services/sync_service.dart` → retry loop
- `mobile/lib/database/local_store.dart` → sync_retries table
- `backend/presentation/server.py` → idempotence

**Résultat :** Captures ne se perdent jamais (même 30s offline)

### Phase 2 : Agent visibility 100% (Semaines 2-3)
**Fichiers :**
- `backend/domain/entities.py` → Device aggregate
- `backend/infrastructure/memory_repo.py` → DeviceSessionRepository
- `mobile/lib/services/sync_service.dart` → heartbeat
- `backend/presentation/static/index.html` → agent markers

**Résultat :** Coordinateurs voient agents temps réel

### Phase 3 : Quartiers 75% (Semaines 3-4)
**Fichiers :**
- `backend/domain/geography.py` (créer) → NominatimCache
- `mobile/lib/services/location_service.dart` (créer)
- `backend/presentation/static/index.html` → filter

**Résultat :** Captures taggées quartier administratif

### Phase 4 : Capteurs 100% (Semaines 4-8)
**Fichiers :**
- `mobile/lib/services/compass_service.dart` (créer) → flutter_compass
- `mobile/lib/services/imu_service.dart` (créer) → sensors_plus
- `mobile/lib/services/pedometer_service.dart` (créer) → pedometer
- `mobile/lib/main.dart` → UI capteurs + sync log

**Résultat :** Données réelles + UI transparente

---

## 📊 Fichiers importants

| Fichier | Contenu | Pour qui |
|---------|---------|----------|
| `README.md` | Overview + liens docs | Tout le monde |
| `docs/INDEX.md` | Navigation guidée | Tout le monde |
| `docs/QUICK-START.md` | Clone + setup + troubleshooting | Devs |
| `docs/executive-summary.md` | Vision 15 min + KPI | Décideurs |
| `docs/diagnostic-problemes.md` | 6 problèmes + causes | Tech leads |
| `docs/mvp-feuille-route.md` | 4 phases détaillées + code | Devs |
| `docs/application-mobile.md` | Architecture Flutter | Dev mobile |
| `docs/carte-serveur.md` | Architecture DDD backend | Dev backend |

---

## 🔄 Mise à jour future

Pour ajouter changements au MVP :

```bash
# Faire changements locaux
# ex: docs/mvp-feuille-route.md

# Commit et push
git add docs/
git commit -m "docs: Mise à jour Phase X - description"
git push origin genspark_ai_developer
```

---

## 📞 Support

**Questions sur les docs ?**
- Voir `docs/INDEX.md` pour chemins recommandés
- Voir `docs/QUICK-START.md` troubleshooting

**Questions sur le MVP ?**
- Lire `docs/diagnostic-problemes.md` (6 problèmes)
- Lire `docs/mvp-feuille-route.md` (phases détaillées)

**Questions architecture ?**
- Mobile : `docs/application-mobile.md`
- Backend : `docs/carte-serveur.md`

---

## 📈 Prochaines étapes

1. ✅ **Poussé sur GitHub** (branche genspark_ai_developer)
2. ✅ **README mis à jour** (liens docs complets)
3. ✅ **QUICK-START.md** (instructions clonage)
4. 📋 **Équipe clone localement** (git checkout genspark_ai_developer)
5. 📋 **Équipe lit docs** (par rôle)
6. 📋 **Phase 1 débute** (semaine 1)

---

## 🎯 Résumé

**Livré :**
- ✅ 8 fichiers `.md` documentant audit V2 + MVP 8 semaines
- ✅ README.md complet avec KPIs + plan
- ✅ Instructions clonage local (3 méthodes)
- ✅ Troubleshooting complet
- ✅ Navigation guidée par rôle

**Récupération :**
```bash
git clone https://github.com/Cabrel10/Mapnet.git
cd Mapnet
git checkout genspark_ai_developer
```

**Accès docs :**
- GitHub : https://github.com/Cabrel10/Mapnet/tree/genspark_ai_developer/docs
- Local : `docs/` (après clone)

**Status :** 🟢 **Prêt pour implémentation MVP**

---

**Generated:** 30 juillet 2026  
**Version :** 2.0 MVP Planning  
**Branch :** genspark_ai_developer
