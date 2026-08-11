"""MapNet PRESENTATION — Serveur HTTP (stdlib, zéro dépendance).

Sert :
  GET  /                     -> carte interactive Leaflet (HTML)
  GET  /health               -> {"status":"ok", ...}
  GET  /api/captures         -> liste JSON des captures
  GET  /api/captures.geojson -> FeatureCollection GeoJSON (pour la carte)
  GET  /api/map.geojson      -> captures + appareils actifs/inactifs
  GET  /api/devices          -> appareils et dernière session
  POST /api/devices/heartbeat -> présence et télémétrie mobile
  GET  /api/stats            -> statistiques (états, kinds, trust moyen)
  GET  /api/plugins          -> capteurs disponibles (plugin system)
  GET  /api/events           -> derniers événements de domaine
  POST /api/captures         -> crée une capture {lat,lon,kind,label,signals}
  POST /api/captures/<id>/sync -> fait progresser la capture vers le serveur

  # Itinéraire guidé + suivi agents (proxies vers gateway Go 8080 / routing 8093)
  POST /api/routing/navigate -> itinéraire position->destination (steps FR + GeoJSON)
  POST /api/position         -> remonte la position live d'un agent (vers gps-collect)
  GET  /api/agents           -> dernières positions connues des agents

Choix : bibliothèque standard `http.server` -> démarrage instantané, aucune
installation pip (ne perturbe pas l'entraînement ADAN en cours). Le découpage
DDD reste intact ; ce fichier n'est qu'un adaptateur HTTP fin.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from urllib.request import Request as _UrlRequest, urlopen as _urlopen
from urllib.error import URLError as _URLError

# Upstreams internes (même hôte). Le gateway Go (8080) proxifie vers
# gps-collect (8095) et routing (8093). Configurable par variables d'env.
_GATEWAY_URL = os.environ.get("MAPNET_GATEWAY_URL", "http://127.0.0.1:8080")
_ROUTING_NAVIGATE = os.environ.get(
    "MAPNET_ROUTING_NAVIGATE_URL", f"{_GATEWAY_URL}/api/route/api/v1/routing/navigate"
)
_GPS_POSITION = os.environ.get(
    "MAPNET_GPS_POSITION_URL", f"{_GATEWAY_URL}/api/gps/api/v1/collecte/position"
)
_GPS_POSITIONS = os.environ.get(
    "MAPNET_GPS_POSITIONS_URL", f"{_GATEWAY_URL}/api/gps/api/v1/positions"
)


def _proxy_post(url: str, payload: dict, timeout: float = 30.0):
    """POST JSON vers un upstream interne, retourne (code, objet_json)."""
    body = json.dumps(payload).encode("utf-8")
    req = _UrlRequest(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with _urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8") or "{}")
    except _URLError as e:
        return 502, {"error": "upstream_unavailable", "detail": str(e), "upstream": url}
    except Exception as e:  # noqa: BLE001
        return 502, {"error": "upstream_error", "detail": str(e)}


def _proxy_get(url: str, timeout: float = 15.0):
    try:
        with _urlopen(url, timeout=timeout) as resp:
            return resp.getcode(), json.loads(resp.read().decode("utf-8") or "{}")
    except _URLError as e:
        return 502, {"error": "upstream_unavailable", "detail": str(e), "upstream": url}
    except Exception as e:  # noqa: BLE001
        return 502, {"error": "upstream_error", "detail": str(e)}

# --- bootstrap import path (permet `python backend/presentation/server.py`) --
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_BACKEND)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.presentation.container import Container  # noqa: E402

_STATIC = os.path.join(_HERE, "static")
_SNAPSHOT = os.path.join(_ROOT, "backend", "data", "captures_snapshot.json")

# Container global : seules les captures terrain reçues sont exposées.
CONTAINER = Container(snapshot_path=_SNAPSHOT)


class Handler(BaseHTTPRequestHandler):
    server_version = "MapNet/1.0"

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def log_message(self, fmt, *args):
        sys.stdout.write("[MapNet] " + (fmt % args) + "\n")
        sys.stdout.flush()

    # ----------------------------------------------------------------- #
    def do_OPTIONS(self):
        return self._send(204, b"")

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path in ("/", "/index.html"):
                return self._serve_static("index.html", "text/html; charset=utf-8")
            if path == "/favicon.ico":
                return self._send(204, b"", "image/x-icon")
            if path == "/health":
                return self._json({"status": "ok", "service": "mapnet",
                                   "captures": CONTAINER.repo.list().__len__(),
                                   "events": CONTAINER.bus.event_count})
            if path == "/api/captures":
                return self._json([c.to_dict() for c in CONTAINER.repo.list()])
            if path == "/api/captures.geojson":
                return self._json(CONTAINER.repo.geojson())
            if path == "/api/devices":
                return self._json(CONTAINER.devices.list_devices())
            if path == "/api/map.geojson":
                captures = CONTAINER.repo.geojson()
                devices = CONTAINER.devices.geojson()
                return self._json({
                    "type": "FeatureCollection",
                    "features": captures["features"] + devices["features"],
                })
            if path == "/api/stats":
                return self._json(CONTAINER.service.stats())
            if path == "/api/plugins":
                return self._json(CONTAINER.plugins.snapshot())
            if path == "/api/events":
                return self._json(CONTAINER.bus.recent(30))
            if path == "/api/agents":
                # Dernières positions connues des agents (via gps-collect/gateway)
                minutes = urlparse(self.path).query
                qs = ""
                for kv in minutes.split("&"):
                    if kv.startswith("minutes="):
                        qs = "?" + kv
                code, obj = _proxy_get(_GPS_POSITIONS + qs)
                return self._json(obj, code)
            return self._json({"error": "not_found", "path": path}, 404)
        except Exception as e:  # pragma: no cover
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw or b"{}")
            if path == "/api/captures":
                capture_id = str(data.get("capture_id") or "").strip() or None
                existed = capture_id is not None and CONTAINER.repo.get(capture_id) is not None
                cap = CONTAINER.service.create_capture(
                    lat=float(data.get("lat", 0.0)),
                    lon=float(data.get("lon", 0.0)),
                    kind=str(data.get("kind", "gps")),
                    label=str(data.get("label", "")),
                    signals=data.get("signals", {}),
                    capture_id=capture_id,
                )
                return self._json(cap.to_dict(), 200 if existed else 201)
            if path == "/api/devices/heartbeat":
                session = CONTAINER.devices.heartbeat(data)
                return self._json({
                    "accepted": True,
                    "session": session.to_dict(
                        timeout_s=CONTAINER.devices.online_timeout_s
                    ),
                })
            if path.startswith("/api/captures/") and path.endswith("/sync"):
                cid = path.split("/")[3]
                cap = CONTAINER.service.sync_capture(cid, via_mesh=bool(data.get("via_mesh", False)))
                if cap is None:
                    return self._json({"error": "capture_not_found"}, 404)
                return self._json(cap.to_dict())
            if path == "/api/routing/navigate":
                # Itinéraire guidé position -> destination (proxy routing 8093).
                code, obj = _proxy_post(_ROUTING_NAVIGATE, {
                    "from_lat": float(data.get("from_lat", 0.0)),
                    "from_lon": float(data.get("from_lon", 0.0)),
                    "to_lat": float(data.get("to_lat", 0.0)),
                    "to_lon": float(data.get("to_lon", 0.0)),
                })
                return self._json(obj, code)
            if path == "/api/position":
                # Position live d'un agent de terrain (proxy gps-collect 8095).
                code, obj = _proxy_post(_GPS_POSITION, data)
                return self._json(obj, code)
            return self._json({"error": "not_found", "path": path}, 404)
        except Exception as e:  # pragma: no cover
            return self._json({"error": str(e)}, 400)

    def _serve_static(self, name: str, ctype: str) -> None:
        fp = os.path.join(_STATIC, name)
        if not os.path.exists(fp):
            return self._json({"error": "static_not_found", "name": name}, 404)
        with open(fp, "rb") as f:
            self._send(200, f.read(), ctype)


def main():
    host = os.environ.get("MAPNET_HOST", "0.0.0.0")
    port = int(os.environ.get("MAPNET_PORT", "8080"))
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"[MapNet] DDD backend + Leaflet map serving on http://{host}:{port}", flush=True)
    print(f"[MapNet] seeded {len(CONTAINER.repo.list())} captures, "
          f"{CONTAINER.bus.event_count} domain events", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
