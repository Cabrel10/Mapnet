#!/usr/bin/env python3
"""Génère le rapport MAPNET complet (.docx, 25+ pages, avec diagrammes)."""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DOCX = os.path.join(os.path.dirname(HERE), "RAPPORT_MAPNET_ARCHITECTURE.docx")

ACCENT = RGBColor(0x1F, 0x6F, 0xB2)
DARK = RGBColor(0x22, 0x22, 0x22)

doc = Document()

# ---- styles de base
st = doc.styles["Normal"]
st.font.name = "Calibri"
st.font.size = Pt(11)
st.paragraph_format.space_after = Pt(6)
st.paragraph_format.line_spacing = 1.15

for name, size, color in [("Heading 1", 18, ACCENT), ("Heading 2", 14, ACCENT), ("Heading 3", 12, DARK)]:
    s = doc.styles[name]
    s.font.name = "Calibri"
    s.font.size = Pt(size)
    s.font.color.rgb = color
    s.font.bold = True

# sections A4 avec marges
for section in doc.sections:
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.2)


def page_break():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def h1(t):
    doc.add_heading(t, level=1)


def h2(t):
    doc.add_heading(t, level=2)


def h3(t):
    doc.add_heading(t, level=3)


def p(text, bold=False, italic=False, size=None, align=None, color=None):
    para = doc.add_paragraph()
    run = para.add_run(text)
    run.bold = bold
    run.italic = italic
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color
    if align == "center":
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    elif align == "justify":
        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    return para


def bullets(items, style="List Bullet"):
    for it in items:
        doc.add_paragraph(it, style=style)


def numbered(items):
    for it in items:
        doc.add_paragraph(it, style="List Number")


def code_block(text):
    para = doc.add_paragraph()
    para.paragraph_format.left_indent = Cm(0.8)
    para.paragraph_format.space_before = Pt(4)
    para.paragraph_format.space_after = Pt(4)
    run = para.add_run(text)
    run.font.name = "Consolas"
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x1A)
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), "F2F4F7")
    para._p.get_or_add_pPr().append(shd)


def table(headers, rows, widths=None):
    t = doc.add_table(rows=1 + len(rows), cols=len(headers))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for j, htxt in enumerate(headers):
        cell = t.rows[0].cells[j]
        cell.text = ""
        run = cell.paragraphs[0].add_run(htxt)
        run.bold = True
        run.font.size = Pt(9.5)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = t.rows[i + 1].cells[j]
            cell.text = ""
            run = cell.paragraphs[0].add_run(str(val))
            run.font.size = Pt(9)
    doc.add_paragraph()
    return t


def figure(path, caption, width_cm=16.5):
    para = doc.add_paragraph()
    para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    para.add_run().add_picture(path, width=Cm(width_cm))
    cap = doc.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = cap.add_run(caption)
    r.italic = True
    r.font.size = Pt(9)
    r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


# ============================ PAGE DE GARDE ============================
for _ in range(4):
    doc.add_paragraph()
p("RAPPORT TECHNIQUE COMPLET", bold=True, size=16, align="center", color=ACCENT)
p("MAPNET", bold=True, size=42, align="center", color=ACCENT)
p("Plateforme de cartographie collaborative offline-first pour le terrain", size=14, align="center", italic=True)
doc.add_paragraph()
p("Architecture · Microservices · Mobile Android · Synchronisation temps réel", size=12, align="center")
for _ in range(3):
    doc.add_paragraph()
table(["Champ", "Valeur"], [
    ["Projet", "MAPNET — Quamtechs"],
    ["Version mobile", "2.1 (Terrain v1.1.1 / Navigation v1.3.1)"],
    ["Branche de référence", "genspark_ai_developer (194 fichiers)"],
    ["Dépôt", "github.com/Cabrel10/Mapnet"],
    ["Serveur de production", "VPS 169.58.67.16"],
    ["Zone de couverture", "Yaoundé, Cameroun (3.8480, 11.5021)"],
    ["Date du rapport", "7 septembre 2026"],
    ["Statut", "Opérationnel — backend, carte Leaflet et deux APK Android"],
])
doc.add_paragraph()
p("Document généré à partir du code réel du dépôt (branche genspark_ai_developer, commit 9fa03d0). "
  "Toutes les architectures, ports et endpoints cités sont vérifiés dans PORTS.md, INTEGRATION.md et le code source.",
  italic=True, size=9, align="center")
page_break()

# ============================ TABLE DES MATIÈRES ============================
h1("Table des matières")
toc = [
    ("1.", "Résumé exécutif"),
    ("2.", "Présentation du projet MAPNET"),
    ("3.", "Cas d'usage et acteurs"),
    ("4.", "Vue d'ensemble de l'architecture"),
    ("5.", "Architecture microservices détaillée"),
    ("6.", "Le backend DDD (Domain-Driven Design)"),
    ("7.", "Les applications mobiles Android (Flutter)"),
    ("8.", "Synchronisation offline-first"),
    ("9.", "Pipeline de données GPS et graphe routier"),
    ("10.", "Modèle de données et persistance"),
    ("11.", "API de référence (endpoints)"),
    ("12.", "Cartographie des ports et interfaces"),
    ("13.", "Déploiement et infrastructure"),
    ("14.", "Qualité des données et capteurs"),
    ("15.", "Sécurité et conformité CCAA"),
    ("16.", "Tests et validation"),
    ("17.", "Statistiques du code"),
    ("18.", "Intégration MAPNET comme microservice"),
    ("19.", "Diagnostic et problèmes connus"),
    ("20.", "Feuille de route MVP"),
    ("21.", "Opérations : sauvegarde, monitoring, mise à jour"),
    ("22.", "Guide de démarrage rapide"),
    ("23.", "Glossaire"),
    ("24.", "Annexes"),
    ("25.", "Conclusion"),
]
for num, title in toc:
    para = doc.add_paragraph()
    r1 = para.add_run(f"{num} ")
    r1.bold = True
    r1.font.color.rgb = ACCENT
    para.add_run(title)
doc.add_paragraph()
p("Figures : Fig. 1 Architecture globale · Fig. 2 Séquence de synchronisation · Fig. 3 Machine à états · "
  "Fig. 4 Statistiques du code · Fig. 5 Pipeline GPS · Fig. 6 Topologie de déploiement.", italic=True, size=9)
page_break()

# ============================ 1. RÉSUMÉ EXÉCUTIF ============================
h1("1. Résumé exécutif")
p("MAPNET est une plateforme géospatiale complète développée pour la cartographie collaborative du terrain "
  "au Cameroun, centrée initialement sur la ville de Yaoundé. Elle répond à un problème concret : les données "
  "cartographiques des quartiers, routes secondaires et points d'intérêt (POI) de Yaoundé sont incomplètes ou "
  "obsolètes dans les bases publiques, et les conditions de terrain (connectivité intermittente, GPS imprécis "
  "en zone dense) rendent les solutions classiques inopérantes.", align="justify")
p("La solution repose sur trois piliers :", bold=True)
numbered([
    "Deux applications Android natives (Flutter) — MapNet Terrain pour la capture GPS/capteurs et MapNet "
    "Navigation pour la consultation cartographique et les itinéraires guidés en français — conçues "
    "offline-first : elles fonctionnent sans réseau et synchronisent dès que la connectivité revient.",
    "Un backend en architecture Domain-Driven Design (Python stdlib, port 8088) qui applique une machine à "
    "états rigoureuse sur les captures, garantit l'idempotence par capture_id et journalise chaque transition "
    "par event sourcing.",
    "Une constellation de microservices (Go, FastAPI) orchestrés par un gateway : gps-collect (8095), "
    "routing via OSRM (8093), map-engine (8096), places, auth, ccaa-compliance — adossés à Kafka (9092) et "
    "PostgreSQL/PostGIS (5432).",
])
h2("1.1 Indicateurs clés")
table(["Indicateur", "Valeur", "Source"], [
    ["Lignes de code (hors node_modules)", "≈ 16 100", "Comptage réel du dépôt"],
    ["Fichiers source Dart (mobile)", "30 fichiers / 5 396 lignes", "mobile/lib"],
    ["Fichiers Python (backend)", "41 fichiers / 4 250 lignes", "backend/"],
    ["Services Go", "13 fichiers / 1 829 lignes", "services/"],
    ["Microservices déployés", "7 (gateway, gps-collect, routing, map-engine, places, auth, ccaa)", "services/, PORTS.md"],
    ["APK distribués", "2 applications, versions 1.1.1 et 1.3.1", "apk_dist/"],
    ["Taux de synchronisation mesuré (audit V2)", "25 % avant correctifs", "docs/diagnostic-problemes.md"],
    ["Couverture tests backend", "test_mapnet_backend.py + test_integration.py", "tests/"],
])
h2("1.2 Points forts")
bullets([
    "Offline-first réel : retry exponentiel persistant (5 essais), dead-letter queue, historique consultable.",
    "Aucune donnée synthétique à l'exécution : les chemins de seed mobile et backend ont été supprimés ; "
    "les scores de qualité ne sont calculés que sur les mesures physiques disponibles.",
    "Capteurs terrain réels : boussole, accéléromètre, gyroscope, pédomètre — les données absentes sont "
    "affichées comme « indisponibles » plutôt que simulées.",
    "Reverse-geocoding des quartiers via Nominatim avec cache disque, et filtre Leaflet dynamique côté web.",
])
page_break()

# ============================ 2. PRÉSENTATION ============================
h1("2. Présentation du projet MAPNET")
h2("2.1 Vision")
p("MapNet est une application mobile Android couplée à un serveur backend pour la cartographie collaborative "
  "en temps réel sur le terrain. Des agents équipés de smartphones parcourent les quartiers de Yaoundé ; "
  "leurs traces GPS, enrichies des données des capteurs inertiels (IMU), alimentent une base géospatiale "
  "centrale. Les coordinateurs visualisent en temps réel les positions des agents et les captures sur une "
  "carte web Leaflet.", align="justify")
h2("2.2 Problématique terrain")
p("La cartographie de terrain dans un contexte comme Yaoundé pose quatre défis majeurs :", align="justify")
numbered([
    "Connectivité intermittente — les zones à cartographier sont précisément celles où le réseau est faible. "
    "Toute solution qui exige une connexion permanente échoue. D'où le choix offline-first avec DTN "
    "(Delay-Tolerant Networking) : PUSH/PULL automatique dès que le réseau revient.",
    "Précision GPS dégradée — en zone urbaine dense ou sous couvert végétal, le GPS seul dérive. MAPNET "
    "fusionne GPS + IMU (fusion capteurs) et applique un « GPS precision gating » : les points sous le seuil "
    "de précision sont rejetés avant d'entrer dans le pipeline.",
    "Absence de référentiel des quartiers — MAPNET intègre un reverse-geocoding Nominatim avec cache disque "
    "pour indexer chaque capture sur le quartier administratif correspondant.",
    "Durabilité des données — chaque capture est identifiée par un capture_id idempotent : une retransmission "
    "après coupure réseau ne crée jamais de doublon.",
])
h2("2.3 Périmètre")
table(["Dans le périmètre", "Hors périmètre"], [
    ["Collecte de traces GPS terrain", "Gestion de commandes / facturation"],
    ["Construction d'un graphe routier", "CRM"],
    ["Calcul d'itinéraires (OSRM)", "Logique métier des consommateurs"],
    ["Suivi de position d'agents en temps réel", "Tchat / messagerie"],
    ["Indexation des quartiers (reverse-geocoding)", "Paiement"],
])
p("MAPNET répond aux questions « où » et « comment y aller ». Le métier (livraison, VTC, immobilier…) "
  "reste chez le consommateur du microservice — voir chapitre 18.", italic=True)
page_break()

# ============================ 3. CAS D'USAGE ============================
h1("3. Cas d'usage et acteurs")
h2("3.1 Acteurs")
table(["Acteur", "Rôle", "Outil"], [
    ["Agent terrain", "Parcourt les quartiers, capture routes et POI", "MapNet Terrain (APK)"],
    ["Coordinateur", "Supervise agents et captures en temps réel", "Carte web Leaflet (:8088)"],
    ["Utilisateur final", "Consulte la carte, recherche, itinéraires", "MapNet Navigation (APK)"],
    ["Intégrateur", "Consomme l'API MAPNET depuis un autre système", "Gateway :8080"],
    ["Administrateur", "Déploie, sauvegarde, surveille les services", "SSH VPS, scripts deploy/"],
])
h2("3.2 Scénario nominal — capture terrain")
numbered([
    "L'agent ouvre MapNet Terrain et démarre une session de capture (état DRAFT → RECORDING).",
    "L'application enregistre GPS + IMU en continu, même sans réseau, dans la base SQLite locale.",
    "La session terminée (COMPLETED), l'application pousse la capture vers le backend (capture_id unique).",
    "Le backend valide la capture (état, qualité GPS, horodatage monotonique), émet un DomainEvent et persiste.",
    "Le coordinateur voit apparaître la capture sur la carte Leaflet, avec le quartier résolu par Nominatim.",
    "En cas de coupure réseau : retry exponentiel (×5) puis dead-letter ; la reprise se fait par "
    "PULL du manifeste de synchronisation.",
])
h2("3.3 Scénario — navigation")
numbered([
    "L'utilisateur ouvre MapNet Navigation (carte plein écran centrée sur Yaoundé).",
    "Il recherche une destination (recherche Cameroun) ou pose un point sur la carte.",
    "Le moteur routing (FastAPI/OSRM, :8093) calcule l'itinéraire sur le graphe routier local.",
    "Le guidage vocal/textuel est rendu en français ; l'onglet « hors-ligne » (Data Mule) permet un usage "
    "sans réseau des tuiles et traces déjà synchronisées.",
])
h2("3.4 Scénario — intégration microservice")
p("Un système de livraison consomme MAPNET pour géolocaliser ses coursiers et calculer des ETA : il appelle "
  "le gateway (:8080), qui route /api/route/* vers OSRM et /api/gps/* vers gps-collect. Le contrat d'API "
  "complet est au chapitre 11 et dans INTEGRATION.md.", align="justify")
page_break()

# ============================ 4. VUE D'ENSEMBLE ============================
h1("4. Vue d'ensemble de l'architecture")
p("L'architecture MAPNET est une architecture microservices à entrées multiples : les applications mobiles "
  "frappent le backend DDD (:8088) — point d'entrée unique de l'APK — tandis que les clients web et "
  "intégrateurs passent par le gateway Go (:8080) qui répartit vers les services spécialisés.", align="justify")
figure(os.path.join(HERE, "fig01_architecture_globale.png"),
       "Fig. 1 — Architecture globale MAPNET : clients, backend DDD, gateway, microservices, bus Kafka et base PostGIS.")
h2("4.1 Principes structurants")
bullets([
    "Séparation des préoccupations : la collecte (gps-collect), le routage (routing/OSRM), la gestion du "
    "graphe (map-engine) et la logique métier de capture (backend DDD) sont des processus indépendants.",
    "Communication par événements : les traces GPS brutes sont publiées sur Kafka "
    "(topic quamtechs.mapnet.gps.raw) puis consommées pour alimenter PostGIS.",
    "Source de vérité unique pour les ports : PORTS.md — toute intégration commence par un GET /health.",
    "Découplage mobile/serveur par REST JSON + GeoJSON, sans dépendance à un SDK propriétaire.",
])
h2("4.2 Flux de bout en bout")
p("Une capture suit le chemin : APK → backend DDD (validation + état) → persistance + événement ; en "
  "parallèle, les traces GPX volumineuses transitent par gps-collect → Kafka → map-engine (map-matching) → "
  "PostGIS (mapnet_edges, gpx_traces). Le moteur de routage OSRM consomme les arêtes du graphe pour calculer "
  "les itinéraires servis à l'APK Navigation et au web.", align="justify")
page_break()

# ============================ 5. MICROSERVICES ============================
h1("5. Architecture microservices détaillée")
p("Le répertoire services/ contient dix modules, dont sept actifs en production. Le tableau suivant est la "
  "source vérifiée (PORTS.md).", align="justify")
table(["Service", "Port", "Technologie", "Responsabilité"], [
    ["gateway", "8080", "Go", "Routage d'API : /api/gps/* → 8095, /api/map/* → 8096, /api/route/* → 8093"],
    ["backend DDD", "8088", "Python stdlib", "Entrée mobile : /api/captures, /api/routing/navigate, /api/position, /api/agents"],
    ["routing", "8093", "FastAPI + OSRM", "Itinéraires : /api/v1/routing/navigate, /route, /nearest, /health"],
    ["gps-collect", "8095", "Go", "Ingestion : /api/v1/collecte/gpx/upload, /collecte/position, /positions"],
    ["map-engine", "8096", "Go", "Graphe : /api/v1/map/edges.geojson, /sync/manifest, /health"],
    ["places", "—", "Python", "POI, catégories et horaires (migration 2026-08-24)"],
    ["auth", "—", "Python", "Authentification des agents et sessions"],
    ["ccaa-compliance", "—", "Python", "Conformité réglementaire (rapport CCAA)"],
    ["api-gateway", "—", "Kong", "Passerelle d'entreprise (optionnelle, non critique)"],
    ["web-frontend", "8088/8080", "Leaflet/JS", "Cartes de production et de debug"],
])
h2("5.1 Gateway (Go, :8080)")
p("Le gateway est un reverse-proxy minimaliste écrit en Go (un seul fichier source). Il ne porte aucune "
  "logique métier : il route les préfixes d'API vers les services, sert la carte de debug (/mapnet.html) "
  "et isole les consommateurs de la topologie interne. C'est le point d'entrée conseillé pour tout "
  "intégrateur externe.", align="justify")
h2("5.2 gps-collect (Go, :8095)")
p("Service d'ingestion haute fréquence. Il reçoit les uploads GPX et les pings de position des agents, "
  "publie les traces brutes sur Kafka et expose les positions courantes pour la carte temps réel. "
  "Le choix de Go répond à la contrainte de concurrence (centaines de pings simultanés à coût mémoire "
  "minimal).", align="justify")
h2("5.3 routing (FastAPI + OSRM, :8093)")
p("Façade HTTP au-dessus d'OSRM (Open Source Routing Machine). Les endpoints /route et /nearest exposent "
  "le calcul d'itinéraire et le snapping au graphe ; /api/v1/routing/navigate fournit le guidage au format "
  "attendu par l'APK Navigation (instructions en français).", align="justify")
h2("5.4 map-engine (Go, :8096)")
p("Le map-engine consomme les traces, applique le map-matching sur le graphe routier, maintient les arêtes "
  "(mapnet_edges) et publie le manifeste de synchronisation (/api/v1/sync/manifest) qui permet aux mobiles "
  "de récupérer les deltas en GeoJSON — mécanisme central de la reprise offline.", align="justify")
h2("5.5 Services de support : places, auth, ccaa-compliance")
p("places gère le référentiel de POI (catégories, horaires — migration db/migrations/2026-08-24_places_"
  "categories_hours.sql) ; auth gère l'identité des agents (Device/DeviceSession, heartbeat 30 s) ; "
  "ccaa-compliance produit les pièces de conformité (lettre CCAA dans docs/).", align="justify")
page_break()

# ============================ 6. BACKEND DDD ============================
h1("6. Le backend DDD (Domain-Driven Design)")
p("Le backend (Python stdlib, :8088) est structuré en quatre couches DDD explicites — un choix qui rend les "
  "frontières de contexte lisibles et facilite l'intégration par d'autres systèmes.", align="justify")
table(["Couche", "Fichiers", "Responsabilité"], [
    ["domain/", "entities.py, events.py, quality.py, schema.py, state_machine.py", "Modèle métier pur : Capture, Device, événements, règles de qualité, transitions d'état"],
    ["application/", "capture_service.py, device_service.py, event_bus.py, plugins.py", "Orchestration des cas d'usage, bus d'événements interne, points d'extension"],
    ["infrastructure/", "memory_repo.py, nominatim_cache.py", "Persistance (repo mémoire + PostGIS), cache reverse-geocoding"],
    ["presentation/", "server.py, container.py", "API HTTP stdlib, injection de dépendances"],
])
h2("6.1 Machine à états des captures")
figure(os.path.join(HERE, "fig03_state_machine.png"),
       "Fig. 3 — Machine à états d'une capture : DRAFT → RECORDING → (PAUSED) → COMPLETED → SYNCED → ARCHIVED.")
p("Chaque transition est gardée par des règles métier : qualité GPS au-dessus du seuil, horodatage "
  "monotonique, idempotence du capture_id. Toute transition illégale (par exemple SYNCED → RECORDING) est "
  "rejetée avec une erreur explicite. Les transitions émettent des DomainEvents persistés, ce qui permet le "
  "rejeu complet (event sourcing) pour l'audit ou la reconstruction d'état.", align="justify")
h2("6.2 Event sourcing et idempotence")
bullets([
    "event_bus.py — bus d'événements en mémoire ; les handlers applicatifs s'y abonnent (découplage).",
    "events.py — CaptureStarted, CapturePaused, CaptureCompleted, CaptureSynced, PositionReceived…",
    "capture_id — clé d'idempotence : un PUSH répété après timeout réseau renvoie 200/201 sans doublon.",
    "quality.py — renormalisation des scores uniquement sur mesures physiques réelles ; None = indisponible.",
])
h2("6.3 API du backend")
code_block(
    "POST /api/captures          # création de capture (idempotent par capture_id)\n"
    "GET  /api/captures          # liste des captures (GeoJSON)\n"
    "POST /api/position          # ping de position agent\n"
    "GET  /api/agents            # devices + sessions (online/offline, heartbeat 30 s)\n"
    "POST /api/routing/navigate  # itinéraire (proxy vers routing :8093)\n"
    "GET  /health                # sonde de vie")
h2("6.4 Choix technologique : Python stdlib")
p("Le serveur HTTP utilise la bibliothèque standard Python, sans framework : dépendances minimales, "
  "surface d'attaque réduite, déploiement trivial sur le VPS. Le conteneur d'injection (container.py) "
  "permet de remplacer le repository mémoire par PostGIS sans toucher au domaine.", align="justify")
page_break()

# ============================ 7. MOBILE ============================
h1("7. Les applications mobiles Android (Flutter)")
p("Le dossier mobile/ (30 fichiers Dart, 5 396 lignes) produit deux APK distinctes distribuées sur le "
  "port 8099 du VPS.", align="justify")
table(["Application", "Version", "Taille", "Fonction"], [
    ["mapnet-terrain", "v1.1.1", "≈ 46,7 Mo", "Capture GPS + capteurs, stockage local, synchronisation"],
    ["mapnet-navigation", "v1.3.1", "≈ 49,0 Mo", "Carte plein écran, recherche, itinéraires guidés, hors-ligne"],
])
h2("7.1 MapNet Terrain")
bullets([
    "Capture GPS précise avec fusion capteurs (sensor fusion) : boussole, accéléromètre, gyroscope, pédomètre.",
    "GPS precision gating : les points sous le seuil de précision sont écartés avant enregistrement.",
    "Stockage local SQLite ; aucune donnée ne part tant que la session n'est pas terminée.",
    "Écran de synchronisation : file d'attente, essais restants, dead-letter consultable.",
    "Échappement du modal de permissions quand le service de localisation est désactivé (correctif 242399d).",
])
h2("7.2 MapNet Navigation")
bullets([
    "Carte plein écran centrée Yaoundé (3.8480, 11.5021), tuiles OSM.",
    "Recherche d'adresses et lieux au Cameroun.",
    "Itinéraires guidés avec instructions en français (routing :8093).",
    "Onglet hors-ligne « Data Mule » : consultation des données synchronisées sans réseau.",
])
h2("7.3 Structure du code mobile")
code_block(
    "mobile/lib/\n"
    "├── main.dart        # point d'entrée, routage des écrans\n"
    "├── config/          # endpoints, seuils GPS, constantes Yaoundé\n"
    "├── models/          # Capture, Position, Device, Quartier\n"
    "├── services/        # GPS, capteurs IMU, sync PUSH/PULL, HTTP\n"
    "└── database/        # SQLite local, file de synchronisation")
h2("7.4 Build et distribution")
p("Les APK sont compilées par mobile/build_apk.sh (logs apk_build*.log conservés) puis copiées dans "
  "apk_dist/, servies par un http.server sur le port 8099 :", align="justify")
code_block(
    "http://169.58.67.16:8099/mapnet-terrain-v1.1.1.apk\n"
    "http://169.58.67.16:8099/mapnet-navigation-v1.3.1.apk\n"
    "http://169.58.67.16:8099/RAPPORT_MAPNET_ARCHITECTURE.docx   # ce rapport")
page_break()

# ============================ 8. SYNCHRONISATION ============================
h1("8. Synchronisation offline-first")
p("La synchronisation est le cœur différenciant de MAPNET. Le terrain impose des coupures ; le système est "
  "donc conçu pour que « hors-ligne » soit le cas normal, et « en ligne » une opportunité de rattrapage.",
  align="justify")
figure(os.path.join(HERE, "fig02_sequence_sync.png"),
       "Fig. 2 — Diagramme de séquence de la synchronisation PUSH/PULL avec retry exponentiel et dead-letter.")
h2("8.1 Protocole PUSH")
numbered([
    "L'APK écrit chaque capture en SQLite local dès l'enregistrement (durabilité immédiate).",
    "À la fin de session, PUSH /api/captures avec le capture_id unique.",
    "Le backend valide (state machine + qualité), persiste, renvoie 201.",
    "Si le réseau tombe pendant le PUSH : retry exponentiel persistant, 5 essais maximum.",
    "Après 5 échecs : la capture part en dead-letter avec horodatage et motif — consultable dans "
    "l'historique de l'APK, jamais perdue.",
])
h2("8.2 Protocole PULL")
p("Au retour réseau, l'APK appelle GET /api/v1/sync/manifest (map-engine) qui décrit les deltas disponibles "
  "(nouvelles arêtes, positions d'agents, captures validées). Le mobile ne télécharge que ce qui lui manque "
  "(GeoJSON incrémental) — économie de data, essentielle sur les forfaits locaux.", align="justify")
h2("8.3 Compatibilité DTN")
p("Le couple PUSH/PULL + idempotence rend MAPNET compatible avec les réseaux à tolérance de délai : un agent "
  "peut physiquement transporter ses données (Data Mule) entre deux zones de connectivité sans perte ni "
  "doublon. L'onglet hors-ligne de l'APK Navigation exploite le même mécanisme.", align="justify")
h2("8.4 Mesure réelle")
p("L'audit V2 (docs/diagnostic-problemes.md) a mesuré un taux de synchronisation réel de 25 % avant "
  "correctifs, à partir des captures snapshot. Les correctifs (retry persistant, gating GPS, idempotence "
  "renforcée) ciblent directement les causes racines identifiées — voir chapitre 19.", align="justify")
page_break()

# ============================ 9. PIPELINE GPS ============================
h1("9. Pipeline de données GPS et graphe routier")
figure(os.path.join(HERE, "fig05_pipeline_gps.png"),
       "Fig. 5 — Pipeline de données : capture APK → gps-collect → Kafka → map-engine (map-matching) → PostGIS → routing OSRM.")
h2("9.1 Étapes")
table(["Étape", "Composant", "Entrée", "Sortie"], [
    ["1. Capture", "APK Terrain", "GPS + IMU", "Trace GPX locale"],
    ["2. Ingestion", "gps-collect :8095", "Upload GPX / pings", "Messages Kafka"],
    ["3. Bus", "Kafka :9092", "topic quamtechs.mapnet.gps.raw", "Flux ordonné"],
    ["4. Map-matching", "map-engine :8096", "Traces brutes", "Arêtes normalisées"],
    ["5. Persistance", "PostGIS :5432", "Arêtes, traces", "mapnet_edges, gpx_traces"],
    ["6. Routage", "routing :8093 (OSRM)", "Graphe", "Itinéraires + instructions FR"],
])
h2("9.2 Seed initial OSM")
p("Le graphe routier initial est seedé depuis OpenStreetMap sur la zone de Yaoundé "
  "(scripts/seed_edges_osm.sh). Les captures terrain viennent ensuite corriger et enrichir ce graphe : "
  "chemins absents d'OSM, sens uniques réels, état des routes.", align="justify")
h2("9.3 Map-matching")
p("Le map-matching rattache chaque point GPS à l'arête la plus plausible du graphe, en tenant compte de la "
  "précision (gating), du cap (boussole) et de la continuité de la trace. Les traces qui ne matchent aucune "
  "arête connue sont candidates à la création de nouvelles arêtes — c'est ainsi que la carte s'enrichit.",
  align="justify")
page_break()

# ============================ 10. DONNÉES ============================
h1("10. Modèle de données et persistance")
h2("10.1 Base PostgreSQL/PostGIS (quamtechs_db)")
table(["Table", "Contenu", "Consommateurs"], [
    ["mapnet_edges", "Arêtes du graphe routier (géométrie PostGIS)", "map-engine, routing"],
    ["gpx_traces", "Traces GPX brutes uploadées", "map-engine, audit"],
    ["agent_positions", "Positions courantes et historique des agents", "web Leaflet, gps-collect"],
    ["places (migr. 2026-08-24)", "POI avec catégories et horaires d'ouverture", "places, APK Navigation"],
])
h2("10.2 Migrations")
code_block(
    "db/migrations/\n"
    "├── 2026-08-23_search_indexes.sql            # index de recherche (GIN/trigram)\n"
    "└── 2026-08-24_places_categories_hours.sql   # POI : catégories + horaires")
h2("10.3 Entités du domaine (backend/domain/entities.py)")
bullets([
    "Capture — identité (capture_id), géométrie, métadonnées capteurs, état (state machine), scores de qualité.",
    "Device — appareil enregistré d'un agent (identifiant matériel, version APK).",
    "DeviceSession — session active avec heartbeat 30 s ; bascule online/offline automatique.",
    "Quartier — entité administrative résolue par reverse-geocoding Nominatim, avec cache disque.",
])
h2("10.4 Schéma événementiel")
p("Chaque événement du domaine (events.py) est horodaté, typé et rattaché à l'agrégat source. Le rejeu de la "
  "séquence d'événements reconstruit l'état — base de l'auditabilité et des exports de conformité CCAA.",
  align="justify")
page_break()

# ============================ 11. API ============================
h1("11. API de référence (endpoints)")
p("Contrat vérifié dans PORTS.md et INTEGRATION.md. Avant toute intégration : GET /health sur chaque "
  "service cible.", bold=True)
h2("11.1 Backend DDD — :8088")
table(["Méthode", "Endpoint", "Description"], [
    ["POST", "/api/captures", "Crée une capture (idempotent par capture_id)"],
    ["GET", "/api/captures", "Liste les captures (GeoJSON)"],
    ["POST", "/api/position", "Ping de position d'un agent"],
    ["GET", "/api/agents", "Devices et sessions (online/offline)"],
    ["POST", "/api/routing/navigate", "Itinéraire guidé (proxy routing)"],
    ["GET", "/health", "Sonde de vie"],
])
h2("11.2 Routing — :8093")
table(["Méthode", "Endpoint", "Description"], [
    ["POST", "/api/v1/routing/navigate", "Itinéraire avec instructions en français"],
    ["GET", "/route", "Calcul d'itinéraire OSRM brut"],
    ["GET", "/nearest", "Snap du point le plus proche sur le graphe"],
    ["GET", "/health", "Sonde de vie"],
])
h2("11.3 gps-collect — :8095")
table(["Méthode", "Endpoint", "Description"], [
    ["POST", "/api/v1/collecte/gpx/upload", "Upload d'une trace GPX"],
    ["POST", "/api/v1/collecte/position", "Ping de position agent"],
    ["GET", "/api/v1/positions", "Positions courantes de tous les agents"],
])
h2("11.4 map-engine — :8096")
table(["Méthode", "Endpoint", "Description"], [
    ["GET", "/api/v1/map/edges.geojson", "Arêtes du graphe en GeoJSON"],
    ["GET", "/api/v1/sync/manifest", "Manifeste de synchronisation (deltas)"],
    ["GET", "/health", "Sonde de vie"],
])
h2("11.5 Exemple d'appel d'intégration")
code_block(
    "# Itinéraire Yaoundé centre → quartier\n"
    "curl -X POST http://169.58.67.16:8093/api/v1/routing/navigate \\\n"
    "  -H 'Content-Type: application/json' \\\n"
    "  -d '{\"from\": [11.5021, 3.8480], \"to\": [11.5174, 3.8667], \"lang\": \"fr\"}'\n"
    "\n"
    "# Positions des agents en temps réel\n"
    "curl http://169.58.67.16:8095/api/v1/positions")
page_break()

# ============================ 12. PORTS ============================
h1("12. Cartographie des ports et interfaces")
h2("12.1 Interfaces web")
table(["Interface", "URL", "Rôle"], [
    ["Production", "http://169.58.67.16:8088/", "Backend DDD + carte de production (entrée unique APK)"],
    ["Debug", "http://169.58.67.16:8080/mapnet.html", "Gateway + carte de debug (tests pipeline, logs)"],
    ["Distribution APK", "http://169.58.67.16:8099/", "Téléchargement des APK et de ce rapport"],
])
h2("12.2 Matrice des flux")
table(["Source", "Destination", "Protocole", "Objet"], [
    ["APK Terrain", "backend :8088", "HTTP/JSON", "Captures, positions"],
    ["APK Navigation", "backend :8088 / routing :8093", "HTTP/JSON", "Carte, itinéraires"],
    ["Navigateur", "gateway :8080", "HTTP", "Carte debug"],
    ["gateway :8080", "gps-collect :8095", "HTTP", "/api/gps/*"],
    ["gateway :8080", "map-engine :8096", "HTTP", "/api/map/*"],
    ["gateway :8080", "routing :8093", "HTTP", "/api/route/*"],
    ["gps-collect", "Kafka :9092", "Kafka", "topic gps.raw"],
    ["map-engine", "PostGIS :5432", "SQL", "edges, traces"],
    ["backend :8088", "Nominatim", "HTTP", "Reverse-geocoding (cache disque)"],
])
h2("12.3 Notes d'exploitation")
bullets([
    "La géolocalisation navigateur exige HTTPS ; en HTTP, utiliser « Position par clic » sur la carte.",
    "PORTS.md est la source de vérité ; tout écart constaté doit y être corrigé en premier.",
    "Le port 8099 sert aussi la distribution — ne pas le réaffecter.",
])
page_break()

# ============================ 13. DÉPLOIEMENT ============================
h1("13. Déploiement et infrastructure")
figure(os.path.join(HERE, "fig06_deploiement.png"),
       "Fig. 6 — Topologie de déploiement : services dockerisés (Kafka, PostGIS, routing) et processus hôtes (backend, gateway).")
h2("13.1 docker-compose")
p("Le fichier docker-compose.yml (≈ 8,3 Ko) orchestre les services stateful et les moteurs : Kafka + "
  "Zookeeper, PostgreSQL 15 + PostGIS (volume persistant), routing/OSRM. Le backend DDD et le gateway "
  "tournent en processus hôtes (systemd / nohup) pour un redémarrage fin.", align="justify")
h2("13.2 Procédure de redéploiement")
code_block(
    "# Depuis la racine du dépôt (branche genspark_ai_developer)\n"
    "git fetch origin && git reset --hard origin/genspark_ai_developer\n"
    "./redeploy.sh                        # redémarrage ordonné des services\n"
    "curl -s http://127.0.0.1:8088/health # vérification backend\n"
    "curl -s http://127.0.0.1:8093/health # vérification routing\n"
    "curl -s http://127.0.0.1:8096/health # vérification map-engine")
h2("13.3 Seed cartographique")
code_block(
    "./scripts/seed_edges_osm.sh   # import OSM zone Yaoundé → mapnet_edges")
h2("13.4 Environnement")
p("Les variables sensibles sont externalisées (.env.example fourni : connexions DB, URL Nominatim, clés). "
  "Aucun secret n'est commité — le .gitignore couvre .env et les artefacts de build.", align="justify")
page_break()

# ============================ 14. QUALITÉ ============================
h1("14. Qualité des données et capteurs")
h2("14.1 Principe fondateur : zéro donnée synthétique")
p("Depuis la version 2.1, tous les chemins de seed de données synthétiques à l'exécution ont été supprimés "
  "(mobile et backend). Un capteur absent produit la valeur None — affichée « indisponible » — et jamais une "
  "constante de substitution. Les scores de qualité sont renormalisés dynamiquement sur le sous-ensemble de "
  "mesures physiques réellement disponibles.", align="justify")
h2("14.2 Capteurs exploités")
table(["Capteur", "Usage", "Rôle qualité"], [
    ["GPS/GNSS", "Position, vitesse, précision (HDOP)", "Gating : rejet sous le seuil de précision"],
    ["Boussole", "Cap magnétique", "Désambiguïsation du map-matching"],
    ["Accéléromètre", "Détection de mouvement/arrêt", "Filtrage des points à l'arrêt"],
    ["Gyroscope", "Rotation", "Lissage de trajectoire"],
    ["Pédomètre", "Pas", "Mode piéton vs véhicule"],
])
h2("14.3 Scoring (backend/domain/quality.py)")
p("Le score d'une capture agrège : précision GPS médiane, continuité temporelle, cohérence cap/vitesse, "
  "taux de points rejetés par le gating. La renormalisation garantit qu'une capture sans gyroscope n'est "
  "pas pénalisée : le barème s'ajuste aux capteurs présents.", align="justify")
h2("14.4 Indexation des quartiers")
p("Chaque capture est rattachée à son quartier par reverse-geocoding Nominatim. Le cache disque "
  "(infrastructure/nominatim_cache.py) évite de re-interroger le service externe pour des points proches "
  "et permet le fonctionnement dégradé si Nominatim est injoignable.", align="justify")
page_break()

# ============================ 15. SÉCURITÉ ============================
h1("15. Sécurité et conformité CCAA")
h2("15.1 Mesures implémentées")
bullets([
    "Service auth dédié : enregistrement des devices, sessions à heartbeat 30 s, révocation possible.",
    "Idempotence capture_id : protection native contre les rejouements accidentels (retry) et malveillants.",
    "Validation stricte côté state machine : rejet des transitions illégales et des captures hors seuils.",
    "Secrets hors dépôt (.env ignoré par git) ; surface réduite du backend (stdlib, pas de framework).",
    "Endpoints /health sans donnée sensible ; les flux internes (Kafka, PostGIS) ne sont pas exposés publiquement.",
])
h2("15.2 Conformité CCAA")
p("Le service ccaa-compliance produit les pièces réglementaires (lettre CCAA disponible dans docs/). "
  "L'event sourcing fournit la traçabilité exigée : qui a capturé, quand, où, avec quel device, et quel "
  "chemin de validation la donnée a suivi.", align="justify")
h2("15.3 Recommandations")
numbered([
    "Passer les interfaces publiques en HTTPS (reverse-proxy TLS) — requis aussi pour la géoloc navigateur.",
    "Ajouter une authentification par token sur les endpoints d'écriture du gateway.",
    "Restreindre Kafka (:9092) et PostGIS (:5432) au réseau interne du VPS (bind localhost / firewall).",
    "Activer la rotation des logs (mapnet_server.log atteint déjà ≈ 276 Ko).",
])
page_break()

# ============================ 16. TESTS ============================
h1("16. Tests et validation")
h2("16.1 Suites présentes")
table(["Suite", "Fichier", "Portée"], [
    ["Tests unitaires backend", "tests/test_mapnet_backend.py", "Domaine : state machine, qualité, idempotence, entités"],
    ["Tests d'intégration", "tests/test_integration.py", "Flux bout-en-bout : capture → API → persistance"],
    ["Suite E2E mobile", "tests/ (E2E suite)", "GPS precision gating, sensor fusion, navigation"],
])
h2("16.2 Historique de validation")
bullets([
    "31 août 2026 — validation opérationnelle : backend, carte Leaflet, deux APK (README).",
    "Commit 9015353 — GPS precision gating + sensor fusion + suite E2E.",
    "Commit 242399d — correctif modal permissions quand localisation désactivée.",
    "Commit 9fa03d0 — documentation d'intégration microservice (INTEGRATION.md vérifié).",
])
h2("16.3 Lancer les tests")
code_block(
    "cd MAPNET\n"
    "python3 -m pytest tests/ -v            # suites backend + intégration\n"
    "cd mobile && flutter test              # tests unitaires Dart")
page_break()

# ============================ 17. STATS ============================
h1("17. Statistiques du code")
figure(os.path.join(HERE, "fig04_stats_code.png"),
       "Fig. 4 — Répartition du code par langage (gauche, comptage réel) et par fonction (droite).")
h2("17.1 Comptage réel (branche genspark_ai_developer)")
table(["Langage", "Fichiers", "Lignes", "Usage"], [
    ["Dart", "30", "5 396", "Applications mobiles Flutter"],
    ["Python", "41", "4 250", "Backend DDD + services support"],
    ["Go", "13", "1 829", "Gateway, gps-collect, map-engine"],
    ["JavaScript", "7", "1 457", "Cartes web Leaflet"],
    ["SQL", "5", "841", "Schéma, migrations, index"],
    ["Shell", "3", "90", "Build APK, seed OSM, redeploy"],
    ["Total", "≈ 99", "≈ 15 863", "—"],
])
p("Comptage hors node_modules et artefacts de build. Le dépôt complet (branche genspark_ai_developer) "
  "contient 194 fichiers contre 70 sur main — la branche de développement est donc bien la référence.",
  italic=True)
page_break()

# ============================ 18. INTÉGRATION ============================
h1("18. Intégration MAPNET comme microservice")
p("MAPNET est consommable par d'autres projets (livraison, VTC/hub, immobilier, gestion de flotte) via le "
  "gateway :8080. Le guide complet est INTEGRATION.md ; ce chapitre en résume l'essentiel.", align="justify")
h2("18.1 Contrat minimal d'intégration")
numbered([
    "Vérifier la disponibilité : GET /health sur routing (:8093), gps-collect (:8095), map-engine (:8096).",
    "Itinéraires : POST /api/v1/routing/navigate — réponse avec instructions en français.",
    "Positions : GET /api/v1/positions — snapshot temps réel des agents.",
    "Graphe : GET /api/v1/map/edges.geojson — pour affichage ou calculs côté consommateur.",
])
h2("18.2 Ce que MAPNET ne fait pas (frontières)")
p("MAPNET n'est ni un système de commandes, ni de facturation, ni un CRM. Il répond à « où » et « comment "
  "y aller ». Toute logique métier (tarification, dispatch, facturation) appartient au système consommateur, "
  "qui garde la maîtrise de ses identifiants (corrélation par ses propres clés).", align="justify")
h2("18.3 Bonnes pratiques consommateur")
bullets([
    "Toujours passer par le gateway :8080, jamais en direct sur les services internes.",
    "Mettre en cache le manifeste de sync ; ne pas poller /positions à haute fréquence sans débounce.",
    "Gérer les erreurs 4xx/5xx avec backoff ; les services évoluent — tester /health au démarrage.",
])
page_break()

# ============================ 19. DIAGNOSTIC ============================
h1("19. Diagnostic et problèmes connus")
p("L'audit technique V2 (docs/diagnostic-problemes.md) a identifié six problèmes avec snapshots de code et "
  "causes racines. Synthèse :", align="justify")
table(["#", "Problème", "Cause racine", "Statut"], [
    ["1", "Taux de sync réel de 25 %", "Retry non persistant, pertes à la coupure réseau", "Corrigé (retry ×5 persistant + dead-letter)"],
    ["2", "Captures GPS bruitées en zone dense", "Pas de filtrage par précision", "Corrigé (GPS precision gating, commit 9015353)"],
    ["3", "Boucle du modal de permissions", "Cas localisation désactivée non géré", "Corrigé (commit 242399d)"],
    ["4", "Scores de qualité biaisés", "Constantes substituées aux capteurs absents", "Corrigé (renormalisation sur mesures réelles)"],
    ["5", "Doublons après retransmission", "Absence de clé d'idempotence", "Corrigé (capture_id)"],
    ["6", "Données de démo mélangées au réel", "Seeds synthétiques à l'exécution", "Corrigé (seeds runtime supprimés, v2.1)"],
])
h2("19.1 Points de vigilance restants")
bullets([
    "Interfaces en HTTP clair — migration TLS recommandée (chapitre 15.3).",
    "Backend :8088 mono-processus stdlib — prévoir un superviseur avec redémarrage automatique.",
    "La couverture du graphe hors Yaoundé exige un nouveau seed OSM par zone.",
])
page_break()

# ============================ 20. FEUILLE DE ROUTE ============================
h1("20. Feuille de route MVP")
p("Selon docs/mvp-feuille-route.md et l'état opérationnel au 31 août 2026 :", align="justify")
h2("20.1 Réalisé")
bullets([
    "Backend DDD complet avec state machine, event sourcing, idempotence.",
    "Deux APK Android en distribution (Terrain v1.1.1, Navigation v1.3.1).",
    "Synchronisation offline-first avec retry persistant et dead-letter.",
    "Carte web temps réel (agents, captures, quartiers) + carte de debug.",
    "Pipeline GPS → Kafka → PostGIS → OSRM opérationnel sur Yaoundé.",
    "Documentation d'intégration microservice (INTEGRATION.md).",
])
h2("20.2 Court terme (T4 2026)")
numbered([
    "TLS sur les interfaces publiques + token d'authentification gateway.",
    "Extension du graphe : Douala, puis axes Yaoundé–Douala.",
    "Tableau de bord coordinateur : taux de sync par agent, heatmap des captures.",
])
h2("20.3 Moyen terme (2027)")
numbered([
    "Mode Data Mule multi-relais (transfert device-à-device).",
    "Détection automatique de nouvelles routes à partir des traces non matchées.",
    "API publique versionnée avec quotas par consommateur.",
])
page_break()

# ============================ 21. OPÉRATIONS ============================
h1("21. Opérations : sauvegarde, monitoring, mise à jour")
h2("21.1 Sauvegarde 3-2-1")
p("La stratégie suit la règle 3-2-1 : trois copies, deux supports différents, une hors site. Les scripts "
  "de déploiement (deploy/) automatisent la sauvegarde de la base PostGIS (pg_dump horodaté) et de la "
  "configuration avant toute mise à jour.", align="justify")
h2("21.2 Monitoring")
bullets([
    "Sondes /health sur chaque service (8088, 8093, 8095, 8096) — à brancher sur un superviseur.",
    "Log serveur : mapnet_server.log (rotation à prévoir).",
    "Carte de debug :8080/mapnet.html — visualisation directe du pipeline et des positions.",
    "Heartbeat agents 30 s : un device sans heartbeat passe offline automatiquement.",
])
h2("21.3 Procédure de mise à jour")
numbered([
    "Sauvegarde PostGIS + .env.",
    "git fetch origin && git reset --hard origin/genspark_ai_developer.",
    "Migrations SQL éventuelles (db/migrations/, ordre lexicographique).",
    "./redeploy.sh puis vérification des /health.",
    "Test de bout en bout : capture APK → visible sur la carte :8088.",
])
page_break()

# ============================ 22. QUICK START ============================
h1("22. Guide de démarrage rapide")
h2("22.1 Pour l'agent terrain")
numbered([
    "Télécharger l'APK : http://169.58.67.16:8099/mapnet-terrain-v1.1.1.apk",
    "Installer (autoriser les sources inconnues), accorder la localisation « toujours ».",
    "Démarrer une capture, parcourir la zone, terminer la session.",
    "La synchronisation est automatique ; vérifier l'écran Sync en cas de zone blanche.",
])
h2("22.2 Pour le coordinateur")
numbered([
    "Ouvrir http://169.58.67.16:8088/ — carte de production.",
    "Filtrer par quartier (reverse-geocoding Nominatim) et par agent (online/offline).",
    "Exporter le GeoJSON combiné pour analyse externe.",
])
h2("22.3 Pour le développeur")
code_block(
    "git clone https://github.com/Cabrel10/Mapnet.git\n"
    "cd Mapnet && git checkout genspark_ai_developer\n"
    "cp .env.example .env          # renseigner les variables\n"
    "docker compose up -d          # Kafka, PostGIS, routing\n"
    "python3 backend/presentation/server.py   # backend :8088\n"
    "cd services/gateway && go run .          # gateway :8080\n"
    "python3 -m pytest tests/ -v              # validation")
h2("22.4 Téléchargements")
table(["Ressource", "URL"], [
    ["APK Terrain v1.1.1", "http://169.58.67.16:8099/mapnet-terrain-v1.1.1.apk"],
    ["APK Navigation v1.3.1", "http://169.58.67.16:8099/mapnet-navigation-v1.3.1.apk"],
    ["Ce rapport (.docx)", "http://169.58.67.16:8099/RAPPORT_MAPNET_ARCHITECTURE.docx"],
])
page_break()

# ============================ 23. GLOSSAIRE ============================
h1("23. Glossaire")
table(["Terme", "Définition"], [
    ["APK", "Android Package — fichier d'installation d'application Android."],
    ["Capture", "Session d'enregistrement GPS/capteurs d'un agent, dotée d'un état et d'un capture_id unique."],
    ["DDD", "Domain-Driven Design — architecture centrée sur le modèle métier (domain/application/infrastructure/presentation)."],
    ["Dead-letter", "File de dernier recours pour les captures ayant échoué 5 fois à la synchronisation."],
    ["DTN", "Delay-Tolerant Networking — réseau tolérant les coupures longues."],
    ["Event sourcing", "Persistance de l'état sous forme de séquence d'événements rejouables."],
    ["GeoJSON", "Format JSON standard pour données géographiques."],
    ["Gating (précision GPS)", "Rejet des points GPS dont la précision est sous le seuil configuré."],
    ["GPX", "GPS Exchange Format — format XML de traces GPS."],
    ["IMU", "Centrale inertielle : accéléromètre + gyroscope (+ boussole)."],
    ["Idempotence", "Propriété garantissant qu'une même requête répétée produit le même effet unique."],
    ["Kafka", "Bus de messages distribué (topic quamtechs.mapnet.gps.raw)."],
    ["Map-matching", "Rattachement des points GPS aux arêtes du graphe routier."],
    ["Nominatim", "Service de géocodage/reverse-geocoding OpenStreetMap."],
    ["OSRM", "Open Source Routing Machine — moteur de calcul d'itinéraires."],
    ["PostGIS", "Extension spatiale de PostgreSQL (géométries, index spatiaux)."],
    ["POI", "Point Of Interest — lieu d'intérêt cartographié."],
    ["State machine", "Machine à états finis gouvernant le cycle de vie d'une capture."],
])
page_break()

# ============================ 24. ANNEXES ============================
h1("24. Annexes")
h2("24.1 Annexe A — Arborescence du dépôt (extraits)")
code_block(
    "MAPNET/\n"
    "├── backend/                  # DDD Python :8088\n"
    "│   ├── domain/               # entities, events, quality, schema, state_machine\n"
    "│   ├── application/          # capture_service, device_service, event_bus, plugins\n"
    "│   ├── infrastructure/       # memory_repo, nominatim_cache\n"
    "│   └── presentation/         # server, container\n"
    "├── services/                 # microservices\n"
    "│   ├── gateway/              # Go :8080\n"
    "│   ├── gps-collect/          # Go :8095\n"
    "│   ├── routing/              # FastAPI/OSRM :8093\n"
    "│   ├── map-engine/           # Go :8096\n"
    "│   ├── places/  auth/  ccaa-compliance/  api-gateway(Kong)/  web-frontend/\n"
    "├── mobile/                   # Flutter (lib/, android/, build_apk.sh)\n"
    "├── db/migrations/            # SQL versionné\n"
    "├── scripts/seed_edges_osm.sh # seed graphe Yaoundé\n"
    "├── tests/                    # pytest backend + intégration\n"
    "├── apk_dist/                 # distribution :8099 (APK + ce rapport)\n"
    "├── docs/                     # INDEX, executive-summary, diagnostic, feuille de route\n"
    "├── docker-compose.yml        # Kafka, PostGIS, routing\n"
    "├── PORTS.md                  # source de vérité des ports\n"
    "├── INTEGRATION.md            # consommation microservice\n"
    "└── DEPLOYMENT.md             # déploiement détaillé")
h2("24.2 Annexe B — Références internes")
bullets([
    "docs/INDEX.md — point d'entrée de la documentation, parcours par rôle.",
    "docs/executive-summary.md — vision, KPIs, budget, risques (15 min).",
    "docs/diagnostic-problemes.md — audit V2 : 6 problèmes, causes racines (20 min).",
    "docs/mvp-feuille-route.md — plan MVP détaillé (60 min).",
    "docs/application-mobile.md — spécifications des applications.",
    "docs/carte-serveur.md — interfaces web production/debug.",
])
h2("24.3 Annexe C — Historique git récent (branche genspark_ai_developer)")
code_block(
    "9fa03d0 docs(integration): MAPNET as a consumable microservice\n"
    "242399d fix(gps): escape permission-loop modal when location service disabled\n"
    "9015353 feat(navigation): GPS precision gating, sensor fusion, E2E suite")
page_break()

# ============================ 25. CONCLUSION ============================
h1("25. Conclusion")
p("MAPNET est une plateforme de cartographie collaborative mature et opérationnelle. Son architecture — "
  "microservices Go/FastAPI derrière un gateway, backend DDD à la logique rigoureuse, mobile Flutter "
  "genuinement offline-first — est adaptée aux contraintes réelles du terrain camerounais : connectivité "
  "intermittente, GPS dégradé, besoin de traçabilité.", align="justify")
p("Les choix structurants (idempotence, event sourcing, machine à états, zéro donnée synthétique, "
  "renormalisation qualité) ne sont pas des raffinements théoriques : ils corrigent des défauts mesurés "
  "lors de l'audit V2 (taux de synchronisation réel de 25 %) et constituent la base de la fiabilité "
  "actuelle.", align="justify")
p("Les prochaines étapes prioritaires sont la mise en TLS des interfaces publiques, l'extension "
  "géographique du graphe au-delà de Yaoundé, et l'outillage du pilotage coordinateur. La documentation "
  "d'intégration (chapitre 18) ouvre d'ores et déjà MAPNET à l'écosystème de services consommateurs.",
  align="justify")
doc.add_paragraph()
p("— Fin du rapport —", align="center", italic=True)
p("Rapport généré le 7 septembre 2026 à partir du dépôt github.com/Cabrel10/Mapnet "
  "(branche genspark_ai_developer). Figures produites par matplotlib ; sources : README.md, PORTS.md, "
  "INTEGRATION.md, DEPLOYMENT.md, docs/ et le code source.", size=8, italic=True, align="center")

doc.save(OUT_DOCX)
print("OK ->", OUT_DOCX)
