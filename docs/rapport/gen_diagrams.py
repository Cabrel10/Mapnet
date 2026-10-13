#!/usr/bin/env python3
"""Génère les diagrammes du rapport MAPNET (matplotlib pur, sans dépendances externes)."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np, os

OUT = os.path.dirname(os.path.abspath(__file__))
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})

C = {"backend": "#1f6fb2", "gateway": "#2e8b57", "svc": "#c9541e", "data": "#7a3fa0",
     "mobile": "#b21f6f", "web": "#3f7fbf", "infra": "#666666"}


def box(ax, x, y, w, h, label, color, fs=9, sub=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.06",
                                fc=color, ec="#222", lw=1.1, alpha=0.92))
    txt = label if not sub else label + "\n" + sub
    ax.text(x + w / 2, y + h / 2, txt, ha="center", va="center", color="white",
            fontsize=fs, fontweight="bold", linespacing=1.3)


def arrow(ax, x1, y1, x2, y2, label=None, color="#333", style="-|>", lw=1.4, rad=0.0, fs=7.5, off=(0, 0.12)):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=13,
                                 color=color, lw=lw, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1], label, fontsize=fs,
                ha="center", color=color, fontstyle="italic",
                bbox=dict(fc="white", ec="none", alpha=0.85, pad=0.6))


# ---------------------------------------------------------------- 1. Architecture globale
fig, ax = plt.subplots(figsize=(11, 8.2))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
ax.set_title("MAPNET — Architecture globale (microservices, VPS 169.58.67.16)", fontsize=13, fontweight="bold", pad=12)

box(ax, 2, 78, 20, 12, "MapNet Terrain\n(Flutter APK)", C["mobile"], 9, "GPS + IMU réels")
box(ax, 2, 62, 20, 12, "MapNet Navigation\n(Flutter APK)", C["mobile"], 9, "Itinéraires + offline")
box(ax, 2, 46, 20, 12, "Client Web\nLeaflet", C["web"], 9, "Carte temps réel")

box(ax, 38, 78, 24, 12, "Backend DDD :8088", C["backend"], 10, "Python stdlib — entrée mobile")
box(ax, 38, 58, 24, 12, "API Gateway :8080", C["gateway"], 10, "Go — routage /api/*")

box(ax, 78, 82, 20, 9, "gps-collect :8095", C["svc"], 8.5, "Go — GPX / positions")
box(ax, 78, 69, 20, 9, "routing :8093", C["svc"], 8.5, "FastAPI + OSRM")
box(ax, 78, 56, 20, 9, "map-engine :8096", C["svc"], 8.5, "Go — graphe / sync")
box(ax, 78, 43, 20, 9, "places / auth /\nccaa-compliance", C["svc"], 8)

box(ax, 30, 22, 22, 12, "Kafka :9092", C["data"], 9.5, "topic quamtechs.mapnet.gps.raw")
box(ax, 62, 22, 28, 12, "PostgreSQL / PostGIS :5432", C["data"], 9.5, "quamtechs_db — mapnet_edges,\ngpx_traces, agent_positions")
box(ax, 2, 22, 20, 12, "Distribution APK :8099", C["infra"], 8.5, "http.server\n(v1.1.1 / v1.3.1)")

arrow(ax, 22, 84, 38, 84, "REST /api/captures")
arrow(ax, 22, 68, 38, 84, "", rad=0.15)
arrow(ax, 22, 52, 38, 62, "GET carte / GeoJSON")
arrow(ax, 62, 78, 78, 86.5, "/api/gps/*")
arrow(ax, 62, 66, 78, 73.5, "/api/route/*")
arrow(ax, 62, 60, 78, 60.5, "/api/map/*")
arrow(ax, 88, 82, 88, 78, "ingest", off=(3.5, 0))
arrow(ax, 78, 86.5, 52, 32, "produce", rad=-0.25, off=(-2, 0))
arrow(ax, 52, 28, 62, 28, "consume / persist")
arrow(ax, 88, 56, 88, 34, "SQL", off=(4, 0))
arrow(ax, 50, 78, 50, 34, "fallback sync", rad=0.2, off=(2, 0))

ax.text(50, 6, "DDD : domain (entities, events, state_machine, quality) · application (services, event_bus, plugins) · infrastructure (repos, cache Nominatim) · presentation (server :8088)",
        ha="center", fontsize=8, color="#444")
fig.savefig(f"{OUT}/fig01_architecture_globale.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------- 2. Séquence synchronisation offline-first
fig, ax = plt.subplots(figsize=(11, 7.5))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
ax.set_title("MAPNET — Séquence de synchronisation offline-first (PUSH/PULL)", fontsize=13, fontweight="bold", pad=12)

actors = [("Agent terrain\n(APK)", 12), ("Stockage local\nSQLite", 33), ("Backend DDD\n:8088", 56),
          ("Event bus\n/ State machine", 75), ("PostgreSQL\n:5432", 93)]
for name, x in actors:
    ax.add_patch(FancyBboxPatch((x - 7, 88), 14, 8, boxstyle="round,pad=0.05", fc="#1f6fb2", ec="#222"))
    ax.text(x, 92, name, ha="center", va="center", color="white", fontsize=8.5, fontweight="bold")
    ax.plot([x, x], [12, 88], ls="--", color="#999", lw=1)

def msg(a, b, y, label, dashed=False, color="#333"):
    ax.annotate("", xy=(b, y), xytext=(a, y),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5,
                                linestyle="--" if dashed else "-"))
    ax.text((a + b) / 2, y + 1.6, label, ha="center", fontsize=8, color=color)

y = 82
msg(12, 33, y, "1. capture GPS + IMU (offline OK)"); y -= 7
msg(12, 56, y, "2. PUSH /api/captures (capture_id idempotent)"); y -= 7
msg(56, 75, y, "3. validation + transition d'état"); y -= 7
msg(75, 93, y, "4. persist event (event sourcing)"); y -= 7
msg(93, 75, y, "5. ACK"); y -= 7
msg(56, 12, y, "6. 201 Created (ACK)", dashed=True); y -= 9
ax.text(12, y + 2.5, "Si échec réseau :", fontsize=8, fontweight="bold", color="#c9541e"); y -= 5
msg(33, 56, y, "7. retry exponentiel ×5 (persistant)", color="#c9541e"); y -= 7
msg(33, 33, y, "8. dead-letter + historique après 5 échecs", color="#c9541e"); y -= 7
msg(12, 56, y, "9. PULL /api/sync/manifest (reprise)"); y -= 7
msg(56, 12, y, "10. delta GeoJSON (captures + agents)", dashed=True)
fig.savefig(f"{OUT}/fig02_sequence_sync.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------- 3. State machine capture
fig, ax = plt.subplots(figsize=(11, 5.2))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
ax.set_title("MAPNET — Machine à états d'une capture (backend/domain/state_machine.py)", fontsize=12.5, fontweight="bold", pad=10)
st = [("DRAFT", 8), ("RECORDING", 26), ("PAUSED", 44), ("COMPLETED", 62), ("SYNCED", 80), ("ARCHIVED", 94)]
for name, x in st:
    box(ax, x - 7, 55, 13, 14, name, C["backend"], 9)
for (a, b, lab) in [(8, 26, "start"), (26, 44, "pause"), (44, 62, "stop"), (62, 80, "push OK"), (80, 94, "TTL")]:
    arrow(ax, a + 6.5, 62, b - 6.5, 62, lab, off=(0, 3.5))
arrow(ax, 44, 55, 26, 52, "resume", rad=-0.35, off=(0, -4))
ax.text(50, 30, "Garde-fous : idempotence capture_id · horodatage monotonique · qualité GPS > seuil · rejet si état illégal (ex. SYNCED → RECORDING interdit)",
        ha="center", fontsize=8.5, color="#444")
ax.text(50, 20, "Chaque transition émet un DomainEvent (events.py) persisté — rejeu possible (event sourcing)", ha="center", fontsize=8.5, color="#444")
fig.savefig(f"{OUT}/fig03_state_machine.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------- 4. Répartition du code (données réelles)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))
langs = ["Dart\n(mobile)", "Python\n(backend)", "Go\n(gateway/svc)", "JS\n(web)", "SQL", "Shell"]
lines = [5396, 4250, 1829, 1457, 841, 90]
colors = [C["mobile"], C["backend"], C["gateway"], C["web"], C["data"], C["infra"]]
ax1.bar(langs, lines, color=colors)
ax1.set_title("Lignes de code par langage (dépôt réel)", fontsize=11, fontweight="bold")
ax1.set_ylabel("Lignes")
for i, v in enumerate(lines):
    ax1.text(i, v + 60, str(v), ha="center", fontsize=9, fontweight="bold")
ax1.spines[["top", "right"]].set_visible(False)

labels = ["Mobile Flutter\n(30 fichiers)", "Backend DDD\n(41 py)", "Services Go/FastAPI\n(gateway, gps, routing,\nmap-engine, places, auth, ccaa)",
          "Web frontend", "DB / migrations", "Tests"]
sizes = [5396, 4250, 3286, 1457, 841, 900]
ax2.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=90, textprops={"fontsize": 8},
        colors=[C["mobile"], C["backend"], C["svc"], C["web"], C["data"], "#999"])
ax2.set_title("Répartition fonctionnelle du code (≈16 100 lignes)", fontsize=11, fontweight="bold")
fig.savefig(f"{OUT}/fig04_stats_code.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------- 5. Pipeline données GPS
fig, ax = plt.subplots(figsize=(11, 4.8))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
ax.set_title("MAPNET — Pipeline de données GPS (collecte → graphe routier)", fontsize=12.5, fontweight="bold", pad=10)
steps = [("Capture\nGPS+IMU\n(APK)", 7, C["mobile"]), ("gps-collect\n:8095\n(Go)", 22, C["svc"]),
         ("Kafka\n:9092\ngps.raw", 37, C["data"]), ("map-engine\n:8096\nmap-matching", 52, C["svc"]),
         ("PostGIS\n:5432\nedges/traces", 67, C["data"]), ("routing :8093\nOSRM\nitinéraires", 84, C["svc"])]
for name, x, c in steps:
    box(ax, x - 6.5, 45, 13, 22, name, c, 8.5)
for a, b in [(7, 22), (22, 37), (37, 52), (52, 67), (67, 84)]:
    arrow(ax, a + 6.5, 56, b - 6.5, 56)
labels = ["upload GPX", "publish", "consume", "SQL/PostGIS", "edges.geojson"]
for (a, b), lab in zip([(7, 22), (22, 37), (37, 52), (52, 67), (67, 84)], labels):
    ax.text((a + b) / 2, 70, lab, ha="center", fontsize=7.5, color="#555", fontstyle="italic")
ax.text(50, 25, "Qualité : renormalisation des scores uniquement sur capteurs physiques réels — aucune constante substituée · seed OSM zone Yaoundé (scripts/seed_edges_osm.sh)",
        ha="center", fontsize=8.5, color="#444")
fig.savefig(f"{OUT}/fig05_pipeline_gps.png", dpi=150, bbox_inches="tight")
plt.close(fig)

# ---------------------------------------------------------------- 6. Déploiement docker-compose
fig, ax = plt.subplots(figsize=(11, 6.2))
ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
ax.set_title("MAPNET — Topologie de déploiement (docker-compose + services hôtes)", fontsize=12.5, fontweight="bold", pad=10)
box(ax, 4, 74, 26, 14, "Réseau public\n169.58.67.16", C["infra"], 9)
box(ax, 40, 74, 26, 14, "gateway :8080 (Go)", C["gateway"], 9)
box(ax, 74, 74, 22, 14, "web-frontend\ncarte Leaflet", C["web"], 8.5)
box(ax, 4, 48, 26, 14, "backend DDD :8088\n(systemd / python)", C["backend"], 8.5)
box(ax, 40, 48, 18, 14, "routing :8093\n(docker)", C["svc"], 8.5)
box(ax, 62, 48, 16, 14, "gps-collect\n:8095", C["svc"], 8.5)
box(ax, 82, 48, 16, 14, "map-engine\n:8096", C["svc"], 8.5)
box(ax, 20, 20, 24, 14, "Kafka + Zookeeper\n(docker)", C["data"], 8.5)
box(ax, 56, 20, 28, 14, "PostgreSQL 15 + PostGIS\n(docker, volume persistant)", C["data"], 8.5)
arrow(ax, 30, 81, 40, 81); arrow(ax, 66, 81, 74, 81)
arrow(ax, 17, 74, 17, 62); arrow(ax, 53, 74, 53, 62); arrow(ax, 70, 62, 70, 62 + 0)
arrow(ax, 62, 55, 62 - 0, 55); arrow(ax, 82, 55, 82, 55)
arrow(ax, 49, 48, 34, 34, "", rad=0.2); arrow(ax, 49, 48, 60, 34, "", rad=-0.2)
arrow(ax, 90, 48, 76, 34, "", rad=0.25)
ax.text(50, 8, "Backup 3-2-1 : scripts deploy/ · migrations SQL versionnées (db/migrations/) · santé : /health sur chaque service",
        ha="center", fontsize=8.5, color="#444")
fig.savefig(f"{OUT}/fig06_deploiement.png", dpi=150, bbox_inches="tight")
plt.close(fig)

print("OK — 6 figures générées dans", OUT)
