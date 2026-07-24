"""MapNet DOMAIN — Schema Versioning (V1 / V2 / Migration / Rollback).

Les captures évoluent. Une capture V1 (schéma plat, sans qualité) doit pouvoir
être lue, migrée en V2 (avec bloc qualité + état), et au besoin ré-abaissée
(rollback) pour compatibilité descendante.

    migrate_v1_to_v2(dict_v1) -> dict_v2
    rollback_v2_to_v1(dict_v2) -> dict_v1
    ensure_current(any_dict) -> dict_v2   (migre si nécessaire)
"""
from __future__ import annotations

from typing import Any, Dict

CURRENT_VERSION = 2


def migrate_v1_to_v2(d: Dict[str, Any]) -> Dict[str, Any]:
    """V1 (plat: lat/lon/name) -> V2 (structuré: point{}, state, quality)."""
    out = dict(d)
    out["schema_version"] = 2
    if "point" not in out:
        out["point"] = {
            "lat": d.get("lat", 0.0),
            "lon": d.get("lon", 0.0),
            "accuracy_m": d.get("accuracy_m", 10.0),
        }
        out.pop("lat", None)
        out.pop("lon", None)
    out.setdefault("state", "NEW")
    out.setdefault("kind", d.get("type", "gps"))
    out.setdefault("label", d.get("name", ""))
    out.setdefault("quality", None)
    out.setdefault("metadata", {})
    return out


def rollback_v2_to_v1(d: Dict[str, Any]) -> Dict[str, Any]:
    """V2 -> V1 : aplatit le point, retire les champs V2-only."""
    out: Dict[str, Any] = {}
    pt = d.get("point", {})
    out["lat"] = pt.get("lat", 0.0)
    out["lon"] = pt.get("lon", 0.0)
    out["accuracy_m"] = pt.get("accuracy_m", 10.0)
    out["name"] = d.get("label", "")
    out["type"] = d.get("kind", "gps")
    out["schema_version"] = 1
    return out


def ensure_current(d: Dict[str, Any]) -> Dict[str, Any]:
    """Migre un dict quel que soit sa version vers la version courante (V2)."""
    v = int(d.get("schema_version", 1))
    if v >= CURRENT_VERSION:
        return d
    if v == 1:
        return migrate_v1_to_v2(d)
    raise ValueError(f"Version de schéma inconnue : {v}")
