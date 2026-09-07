(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  root.MapNetNavigationMath = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const EARTH_RADIUS_M = 6371000;

  function toRadians(value) {
    return value * Math.PI / 180;
  }

  function normalizeHeading(value) {
    if (!Number.isFinite(value)) return null;
    return ((value % 360) + 360) % 360;
  }

  function projectMeters(point, referenceLat) {
    const latitudeScale = Math.PI * EARTH_RADIUS_M / 180;
    const longitudeScale = latitudeScale * Math.cos(toRadians(referenceLat));
    return {
      x: point.lng * longitudeScale,
      y: point.lat * latitudeScale,
    };
  }

  function pointToSegmentDistanceMeters(point, start, end) {
    const referenceLat = (point.lat + start.lat + end.lat) / 3;
    const p = projectMeters(point, referenceLat);
    const a = projectMeters(start, referenceLat);
    const b = projectMeters(end, referenceLat);
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const lengthSquared = dx * dx + dy * dy;
    if (lengthSquared === 0) return Math.hypot(p.x - a.x, p.y - a.y);
    const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSquared));
    return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
  }

  function closestRouteSegment(point, coordinates) {
    if (!Array.isArray(coordinates) || coordinates.length === 0) {
      return { distance: Infinity, segmentIndex: 0 };
    }
    if (coordinates.length === 1) {
      const only = { lng: coordinates[0][0], lat: coordinates[0][1] };
      return {
        distance: pointToSegmentDistanceMeters(point, only, only),
        segmentIndex: 0,
      };
    }
    let bestDistance = Infinity;
    let segmentIndex = 0;
    for (let index = 0; index < coordinates.length - 1; index += 1) {
      const distance = pointToSegmentDistanceMeters(
        point,
        { lng: coordinates[index][0], lat: coordinates[index][1] },
        { lng: coordinates[index + 1][0], lat: coordinates[index + 1][1] },
      );
      if (distance < bestDistance) {
        bestDistance = distance;
        segmentIndex = index;
      }
    }
    return { distance: bestDistance, segmentIndex };
  }

  function shouldReroute(options) {
    const {
      distance,
      accuracy = 0,
      now,
      offRouteSince,
      lastRerouteAt = 0,
      threshold = 80,
      confirmationMs = 4000,
      cooldownMs = 20000,
      rerouting = false,
    } = options;
    const effectiveThreshold = Math.max(threshold, Math.max(0, accuracy) * 2);
    if (!Number.isFinite(distance) || distance <= effectiveThreshold) {
      return { trigger: false, offRouteSince: null, effectiveThreshold };
    }
    const startedAt = offRouteSince == null ? now : offRouteSince;
    const confirmed = now - startedAt >= confirmationMs;
    const cooledDown = now - lastRerouteAt >= cooldownMs;
    return {
      trigger: confirmed && cooledDown && !rerouting,
      offRouteSince: startedAt,
      effectiveThreshold,
    };
  }

  return {
    normalizeHeading,
    pointToSegmentDistanceMeters,
    closestRouteSegment,
    shouldReroute,
  };
});
