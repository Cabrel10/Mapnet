# Récupérer MapNet V2 localement

**Date :** 30 juillet 2026  
**Branch :** `genspark_ai_developer` (avec audit V2 + MVP)  
**Repo :** https://github.com/Cabrel10/Mapnet

---

## 🚀 3 façons de récupérer la version

### Option 1 : Git clone (recommandé)

**Première fois :**

```bash
# Cloner le repo
git clone https://github.com/Cabrel10/Mapnet.git
cd Mapnet

# Vérifier branche actuelle
git branch -a

# Checkout la branche V2 audit si pas déjà dedans
git checkout genspark_ai_developer
```

**Output attendu :**
```
Cloning into 'Mapnet'...
remote: Enumerating objects: X, done.
remote: Compressing objects: 100% (X/X), done.
remote: Receiving objects: 100% (X/X), done.
Receiving deltas: 100%, done.

Branch 'genspark_ai_developer' set up to track remote branch 'genspark_ai_developer' from 'origin'.
Switched to a new branch 'genspark_ai_developer'
```

**Déjà cloné ? Mettre à jour :**

```bash
cd Mapnet
git fetch origin
git checkout genspark_ai_developer
git pull origin genspark_ai_developer
```

### Option 2 : ZIP direct (snapshot)

```bash
# Télécharger ZIP de la branche
curl -L https://github.com/Cabrel10/Mapnet/archive/genspark_ai_developer.zip \
  -o Mapnet-v2.zip

# Extraire
unzip Mapnet-v2.zip

# Naviguer
cd Mapnet-genspark_ai_developer
```

**Alternative Windows :**
- URL : https://github.com/Cabrel10/Mapnet/archive/genspark_ai_developer.zip
- Clic droit → Extraire

### Option 3 : GitHub Desktop

1. Ouvrir GitHub Desktop
2. File → Clone Repository
3. URL : `https://github.com/Cabrel10/Mapnet.git`
4. Clone
5. Checkout branche `genspark_ai_developer`

---

## 📂 Vérifier l'installation

Après clone, vérifiez que les fichiers V2 sont présents :

```bash
# Vérifier les docs audit
ls -la docs/

# Output attendu :
# -rw-r--r--  INDEX.md
# -rw-r--r--  diagnostic-problemes.md
# -rw-r--r--  mvp-feuille-route.md
# -rw-r--r--  executive-summary.md
# -rw-r--r--  application-mobile.md
# -rw-r--r--  carte-serveur.md

# Vérifier README mis à jour
cat README.md | head -20

# Output attendu : "MapNet — Cartographie collaborative..."
```

---

## 🏗️ Structure locale après clone

```
Mapnet/
├── docs/                          ✅ Audit V2 (6 fichiers .md)
├── mobile/                        ✓ App Flutter
├── backend/                       ✓ Backend Python
├── docker-compose.yml
├── README.md                      ✅ Mis à jour (MVP plan)
└── .git/
```

---

## 📖 Démarrer après clone

### 1. Lire la documentation (30 min)

```bash
# Point d'entrée unique
cat docs/INDEX.md

# Ou selon votre rôle :

# Décideur :
cat docs/executive-summary.md

# Tech lead :
cat docs/diagnostic-problemes.md
cat docs/mvp-feuille-route.md

# Dev mobile :
cat docs/application-mobile.md
cat docs/mvp-feuille-route.md | grep -A 100 "Phase 1"

# Dev backend :
cat docs/carte-serveur.md
cat docs/mvp-feuille-route.md | grep -A 100 "server.py"
```

### 2. Setup mobile (Flutter)

```bash
cd Mapnet/mobile

# Installer dépendances
flutter pub get

# Vérifier setup
flutter doctor

# Run sur émulateur/device
flutter run
```

### 3. Setup backend (Python)

```bash
cd Mapnet/backend

# Lancer serveur (zéro dépendance pip!)
python presentation/server.py

# Output attendu :
# [MapNet] DDD backend + Leaflet map serving on http://0.0.0.0:8080
# [MapNet] seeded 30 captures, 0 domain events
```

### 4. Accéder à la carte

- Ouvrir navigateur : `http://localhost:8080`
- Voir captures sur Leaflet + quartier Ouagadougou

---

## 🔄 Mettre à jour localement

Après clone, si des changements arrivent sur GitHub :

```bash
# Aller au repo
cd Mapnet

# Fetch les changements
git fetch origin

# Mettre à jour la branche locale
git pull origin genspark_ai_developer

# Vérifier changements
git log -3 --oneline
```

---

## 📋 Checklist installation

- [ ] Git clone réussi (`git clone ...`)
- [ ] Branch `genspark_ai_developer` vérifiée (`git branch`)
- [ ] Fichiers docs/ présents (6 `.md` audit V2)
- [ ] README.md mis à jour (contient "MVP")
- [ ] Flutter installé et fonctionne (`flutter doctor`)
- [ ] Backend Python démarrable (`python backend/presentation/server.py`)
- [ ] Carte Leaflet accessible (`http://localhost:8080`)

---

## ❓ Troubleshooting

### Git clone échoue avec "permission denied"

**Cause :** SSH key non configurée

**Fix :**
```bash
# Utiliser HTTPS au lieu SSH
git clone https://github.com/Cabrel10/Mapnet.git

# Ou configurer SSH key
ssh-keygen -t ed25519 -C "your-email@example.com"
cat ~/.ssh/id_ed25519.pub  # Copy to GitHub Settings
```

### Flutter pub get échoue

**Cause :** Dépendances incompatibles

**Fix :**
```bash
cd Mapnet/mobile
flutter clean
flutter pub get
```

### Backend Python "module not found"

**Cause :** Python path mal configuré

**Fix :**
```bash
cd Mapnet
python -c "import sys; print(sys.path)"
# Doit inclure le répertoire courant "."

python backend/presentation/server.py
# Si échoue, faire :
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python backend/presentation/server.py
```

### Ports déjà utilisés

**Port 8080 occupé (backend) :**
```bash
# Trouver le process
lsof -i :8080
# Ou sur Windows :
netstat -ano | findstr :8080

# Changer port
export MAPNET_PORT=8081
python backend/presentation/server.py
```

---

## 📊 Fichiers importants à consulter

Après clone, consultez :

| Rôle | Fichier | Durée |
|------|---------|-------|
| Tout le monde | `docs/INDEX.md` | 5 min |
| Décideur | `docs/executive-summary.md` | 15 min |
| Tech lead | `docs/diagnostic-problemes.md` | 20 min |
| Tech lead | `docs/mvp-feuille-route.md` | 60 min |
| Dev mobile | `docs/application-mobile.md` | 30 min |
| Dev backend | `docs/carte-serveur.md` | 35 min |
| Tout dev | `README.md` | 10 min |

---

## 🔗 Liens utiles

- **Repo GitHub :** https://github.com/Cabrel10/Mapnet
- **Branch V2 audit :** https://github.com/Cabrel10/Mapnet/tree/genspark_ai_developer
- **Issues :** https://github.com/Cabrel10/Mapnet/issues
- **Discussions :** https://github.com/Cabrel10/Mapnet/discussions

---

## ✅ Prochaines étapes

1. ✅ Clone repo (`git clone ...`)
2. ✅ Checkout branche (`git checkout genspark_ai_developer`)
3. ✅ Lire docs/ (INDEX.md → votre rôle)
4. ✅ Setup mobile + backend (suivant rôle)
5. 📋 Assigner phases MVP à équipe dev
6. 📋 Lancer Phase 1 (sync retry)

---

**Version :** 2.0 MVP Planning  
**Date :** 30 juillet 2026  
**Status :** 🟢 Prêt pour clonage local + implémentation
