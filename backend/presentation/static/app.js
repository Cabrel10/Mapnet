/* MapNet PROD frontend — MapLibre GL JS 4.7.x
 * Local search (Cameroun-first), 3-level click info panel, vector tiles,
 * 3D terrain + fill-extrusion buildings, ESRI satellite, Valhalla navigation.
 * NO Nominatim. NO emoji. Lucide icons only.
 */
'use strict';

/* ------------------------------------------------------------------ config */
const YAOUNDE = { lng: 11.5021, lat: 3.8480 };
const START_ZOOM = 13;

// Category -> Lucide icon name (SVG, never emoji)
const CAT_ICON = {
  restaurant:'utensils', food:'utensils', cafe:'coffee', bar:'wine',
  hotel:'bed', lodging:'bed',
  hospital:'cross', clinic:'cross', health:'heart-pulse', pharmacy:'pill',
  school:'book-open', elementary_school:'book-open', college_university:'graduation-cap', education:'graduation-cap',
  bank:'landmark', atm:'landmark', finance:'landmark',
  shopping:'shopping-bag', supermarket:'shopping-cart', market:'store', store:'store',
  gas_station:'fuel', fuel:'fuel',
  church:'church', mosque:'building-2', place_of_worship:'building-2',
  stadium_arena:'trophy', sports:'trophy',
  police:'shield', central_government_office:'building', government:'building',
  professional_services:'briefcase', spas:'sparkles',
  real_estate_service:'home',
  neighborhood:'map', microhood:'map', quarter:'map', locality:'map',
  county:'map-pinned', region:'map-pinned', country:'flag',
  road:'route', building:'building-2', poi:'map-pin'
};
function iconFor(cat, kind){
  if (kind === 'division') return CAT_ICON[cat] || 'map';
  if (kind === 'building') return 'building-2';
  return CAT_ICON[(cat||'').toLowerCase()] || 'map-pin';
}

/* ------------------------------------------------------------------ style
 * Style vectoriel RICHE : OpenFreeMap "Liberty" (gratuit, sans clé API,
 * rues nommées + bâtiments + POI + eau/parcs stylisés). Nos couches locales
 * pg_tileserv (POI/bâtiments/routes/quartiers MapNet) sont AJOUTÉES par-dessus
 * dans addVectorLayers(). On n'écrase JAMAIS le style de base — on l'enrichit.
 */
const OFM_STYLE = 'https://tiles.openfreemap.org/styles/liberty';
const ESRI_SAT = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
// Terrarium-encoded DEM (AWS open data, free, CORS-enabled)
const DEM_TILES = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
// Repli raster OSM si OpenFreeMap est indisponible (réseau/CORS).
const OSM_TILES = ['https://a.tile.openstreetmap.org/{z}/{x}/{y}.png',
                   'https://b.tile.openstreetmap.org/{z}/{x}/{y}.png',
                   'https://c.tile.openstreetmap.org/{z}/{x}/{y}.png'];
const RASTER_FALLBACK = {
  version: 8,
  glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
  sources: { osm: { type:'raster', tiles: OSM_TILES, tileSize:256, maxzoom:19,
                    attribution:'© OpenStreetMap · MapNet' } },
  layers: [ { id:'bg', type:'background', paint:{ 'background-color':'#e8eef3' } },
            { id:'osm', type:'raster', source:'osm' } ]
};

const map = new maplibregl.Map({
  container:'map', style: OFM_STYLE,
  center:[YAOUNDE.lng, YAOUNDE.lat], zoom:START_ZOOM,
  pitch:0, bearing:0, maxPitch:75,
  maxBounds:[[8.0,1.5],[16.5,13.0]],        // Cameroun
  attributionControl:{compact:true}
});
window.map = map;

// Si le style vectoriel échoue à charger, on retombe sur le raster OSM.
let styleFellBack = false;
map.on('error', (e)=>{
  const msg = (e && e.error && e.error.message) || '';
  if (!styleFellBack && /style|sprite|glyphs|tiles\.openfreemap/i.test(msg)){
    styleFellBack = true;
    try{ map.setStyle(RASTER_FALLBACK); map.once('styledata', ()=>{ addVectorLayers(); addTerrain(); }); }catch(_){}
  }
});

// Le clic sur le compas remet déjà bearing=0 ; on garde un helper programmatique.
function resetNorth(){ map.easeTo({ bearing:0, pitch: currentView==='3d'?60:0, duration:600 }); }
window.resetNorth = resetNorth;

/* ------------------------------------------------------------------ state */
let satelliteOn = false;
let currentView = '2d';
let userMarker = null, userPos = null;
let destMarker = null;                  // marqueur "ICI" du résultat sélectionné / destination
let selectedPlace = null;               // {title, lat, lon, ...}  = DESTINATION
let routeOptions = [];                  // alternatives
let chosenRoute = null;
const NavMath = window.MapNetNavigationMath;
let geoWatchId = null;
let sensorsStarted = false;
let sensorState = { heading:null, accel:null, gyro:null };
let gpsAccuracy = null;
let nav = {
  active:false, steps:[], route:null, destName:'', currentStep:0,
  rerouting:false, offRouteSince:null, lastRerouteAt:0
};

/* ---- Origine libre (GPS / clic carte / recherche) + profil transport ---- */
let originMode = 'gps';                  // 'gps' | 'map' | 'search'
let originPos  = null;                   // {lat, lng, name} lorsque map/search
let pickingOrigin = false;               // en attente d'un clic carte
let originMarker = null;
let travelProfile = 'pedestrian';        // pedestrian|auto|motorcycle|taxi
const PROFILE_LABEL = { pedestrian:'Piéton', auto:'Voiture', motorcycle:'Moto', taxi:'Taxi' };

/* ------------------------------------------------------------------ helpers */
const $ = id => document.getElementById(id);
function toast(msg, ms=2200){
  const t=$('toast'); t.textContent=msg; t.classList.add('show');
  clearTimeout(t._h); t._h=setTimeout(()=>t.classList.remove('show'), ms);
}
// NOTE: do NOT name this helper `lucide` — a top-level `function lucide(){}`
// overwrites window.lucide (the library object), destroying createIcons.
// The UMD build assigns `global.lucide = {}` with exports.createIcons on it,
// so we must keep window.lucide intact and only reference it here.
function renderIcons(root){
  try{
    if(window.lucide && typeof window.lucide.createIcons==='function'){
      if(root) window.lucide.createIcons({ nodes: [root] });
      else window.lucide.createIcons();
    }
  }catch(e){ console.warn('lucide createIcons failed', e); }
}
function fmtDist(m){ return m>=1000 ? (m/1000).toFixed(m<10000?1:0)+' km' : Math.round(m)+' m'; }
function fmtDur(s){ const m=Math.round(s/60); return m>=60 ? Math.floor(m/60)+' h '+(m%60)+' min' : m+' min'; }
function haversine(a,b){ const R=6371000,dLat=(b.lat-a.lat)*Math.PI/180,dLon=(b.lng-a.lng)*Math.PI/180,
  la1=a.lat*Math.PI/180,la2=b.lat*Math.PI/180;
  const h=Math.sin(dLat/2)**2+Math.cos(la1)*Math.cos(la2)*Math.sin(dLon/2)**2;
  return 2*R*Math.asin(Math.sqrt(h)); }
function setText(id, value){ const el=$(id); if(el) el.textContent=value; }
function setRerouteState(text, warning=false){
  setText('reroute-state', text);
  const chip=$('reroute-chip'); if(chip) chip.classList.toggle('warn', warning);
}
function updateSensorHud(){
  setText('gps-state', userPos ? `±${Math.round(gpsAccuracy||0)} m` : 'inactif');
  setText('heading-state', sensorState.heading==null ? '—' : `${Math.round(sensorState.heading)}°`);
  setText('accel-state', sensorState.accel==null ? '—' : `${sensorState.accel.toFixed(1)} m/s²`);
  setText('gyro-state', sensorState.gyro==null ? '—' : `${sensorState.gyro.toFixed(2)} rad/s`);
  const button=$('btn-locate'); if(button) button.classList.toggle('tracking', geoWatchId!=null);
}

/* ------------------------------------------------------------------ vector layers */
function addVectorLayers(){
  map.addSource('mn-districts', { type:'vector', tiles:['/tiles/public.mapnet_divisions/{z}/{x}/{y}.pbf'], minzoom:8, maxzoom:16 });
  map.addSource('mn-roads',     { type:'vector', tiles:['/tiles/public.mapnet_edges/{z}/{x}/{y}.pbf'],     minzoom:11, maxzoom:18 });
  map.addSource('mn-buildings', { type:'vector', tiles:['/tiles/public.mapnet_buildings/{z}/{x}/{y}.pbf'], minzoom:13, maxzoom:18 });
  map.addSource('mn-pois',      { type:'vector', tiles:['/tiles/public.raw_places/{z}/{x}/{y}.pbf'],        minzoom:12, maxzoom:18 });

  map.addLayer({ id:'districts-line', type:'line', source:'mn-districts', 'source-layer':'public.mapnet_divisions',
    minzoom:8, paint:{ 'line-color':'#7c3aed', 'line-opacity':0.35, 'line-width':1.2, 'line-dasharray':[2,2] } });

  map.addLayer({ id:'roads-line', type:'line', source:'mn-roads', 'source-layer':'public.mapnet_edges',
    minzoom:12, layout:{'line-cap':'round','line-join':'round'},
    paint:{ 'line-color':'#f59e0b', 'line-opacity':0.5,
      'line-width':['interpolate',['linear'],['zoom'],12,0.5,17,2.5] } });

  map.addLayer({ id:'buildings-fill', type:'fill', source:'mn-buildings', 'source-layer':'public.mapnet_buildings',
    minzoom:14, maxzoom:16, paint:{ 'fill-color':'#cbd2d9', 'fill-opacity':0.55, 'fill-outline-color':'#9aa5b1' } });

  map.addLayer({ id:'buildings-3d', type:'fill-extrusion', source:'mn-buildings', 'source-layer':'public.mapnet_buildings',
    minzoom:15, layout:{ visibility:'none' },
    paint:{
      'fill-extrusion-color':['interpolate',['linear'],['coalesce',['get','height_m'],['*',['coalesce',['get','num_floors'],1],3.2]],
        0,'#d7dbe0', 12,'#c2c8d0', 40,'#a7b0bb', 100,'#8b95a3'],
      'fill-extrusion-height':['coalesce',['get','height_m'],['*',['coalesce',['get','num_floors'],1],3.2],6],
      'fill-extrusion-base':0,
      'fill-extrusion-opacity':0.85 } });

  map.addLayer({ id:'pois', type:'circle', source:'mn-pois', 'source-layer':'public.raw_places',
    minzoom:13, paint:{
      'circle-radius':['interpolate',['linear'],['zoom'],13,3.2,17,7],
      'circle-color':['match',['get','category'],
        'restaurant','#f97316','hospital','#ef4444','pharmacy','#22c55e',
        'school','#3b82f6','college_university','#3b82f6','bank','#a855f7',
        'hotel','#ec4899','gas_station','#eab308','shopping','#14b8a6',
        '#64748b'],
      'circle-stroke-width':1.3, 'circle-stroke-color':'#ffffff', 'circle-opacity':0.9 } });

  map.addLayer({ id:'poi-labels', type:'symbol', source:'mn-pois', 'source-layer':'public.raw_places',
    minzoom:16, layout:{ 'text-field':['get','name'], 'text-size':11, 'text-offset':[0,1.1],
      'text-anchor':'top', 'text-font':['Noto Sans Regular'] },
    paint:{ 'text-color':'#1f2937', 'text-halo-color':'#fff', 'text-halo-width':1.4 } });

  ['pois','buildings-fill','buildings-3d'].forEach(l=>{
    map.on('mouseenter', l, ()=>map.getCanvas().style.cursor='pointer');
    map.on('mouseleave', l, ()=>map.getCanvas().style.cursor='');
  });

  // Click POI directly -> panel (fast path before generic identify)
  map.on('click','pois', e=>{
    if (nav.active) return;
    e.preventDefault && e.preventDefault();
    const p=e.features[0].properties, c=e.features[0].geometry.coordinates;
    showPlacePanel({ title:p.name||'Lieu', subtitle:prettyCat(p.category)||'Lieu',
      lat:c[1], lon:c[0], type:'poi', category:p.category, city:p.city });
    e._mnHandled = true;
  });
}

/* ------------------------------------------------------------------ terrain */
function addTerrain(){
  if (map.getSource('dem')) return;
  map.addSource('dem', { type:'raster-dem', tiles:[DEM_TILES], tileSize:256, encoding:'terrarium', maxzoom:15 });
  if (!map.getLayer('hillshade')){
    map.addLayer({ id:'hillshade', type:'hillshade', source:'dem',
      paint:{ 'hillshade-exaggeration':0.45 } }, 'districts-line');
  }
}

/* ------------------------------------------------------------------ satellite
 * OpenFreeMap n'a pas de couche unique "osm". On insère l'imagerie ESRI JUSTE
 * SOUS notre première couche MapNet (districts-line) : elle recouvre le fond
 * OFM tout en laissant nos POI/bâtiments/routes visibles par-dessus. En mode
 * satellite on masque les couches de FOND OFM (fill/background/raster) pour ne
 * pas les voir sous l'imagerie ; les labels OFM restent.
 */
function firstMapnetLayerId(){
  for (const id of ['districts-line','roads-line','buildings-fill','pois','poi-labels']){
    if (map.getLayer(id)) return id;
  }
  return undefined;
}
function ofmBaseLayerIds(){
  // couches de fond OFM (surfaces) à masquer sous l'imagerie satellite
  try{
    return map.getStyle().layers
      .filter(l => (l.type==='background' || l.type==='fill' || l.type==='raster')
                   && !String(l.id).startsWith('mn') && l.id!=='esri'
                   && !['districts-line','roads-line','buildings-fill','buildings-3d','pois','poi-labels','cat-halo','cat-dot','route-line','route-casing','hillshade'].includes(l.id))
      .map(l => l.id);
  }catch(_){ return []; }
}
function toggleSatellite(){
  satelliteOn = !satelliteOn;
  if (satelliteOn){
    if (!map.getSource('esri')) map.addSource('esri', { type:'raster', tiles:[ESRI_SAT], tileSize:256, maxzoom:19,
      attribution:'© Esri World Imagery' });
    if (!map.getLayer('esri')) map.addLayer({ id:'esri', type:'raster', source:'esri' }, firstMapnetLayerId());
    map.setLayoutProperty('esri','visibility','visible');
    ofmBaseLayerIds().forEach(id=>{ try{ map.setLayoutProperty(id,'visibility','none'); }catch(_){}});
    $('btn-sat').classList.add('active');
  } else {
    if (map.getLayer('esri')) map.setLayoutProperty('esri','visibility','none');
    ofmBaseLayerIds().forEach(id=>{ try{ map.setLayoutProperty(id,'visibility','visible'); }catch(_){}});
    $('btn-sat').classList.remove('active');
  }
}
window.toggleSatellite = toggleSatellite;

/* ------------------------------------------------------------------ view (2D/3D) */
function setView(v){
  currentView = v;
  $('btn-2d').classList.toggle('active', v==='2d');
  $('btn-3d').classList.toggle('active', v==='3d');
  if (v==='3d'){
    addTerrain();
    map.setTerrain({ source:'dem', exaggeration:1.25 });
    if (map.getLayer('buildings-3d')) map.setLayoutProperty('buildings-3d','visibility','visible');
    if (map.getLayer('buildings-fill')) map.setLayoutProperty('buildings-fill','visibility','none');
    map.easeTo({ pitch:60, bearing:-18, zoom:Math.max(map.getZoom(),15.5), duration:900 });
  } else {
    map.setTerrain(null);
    if (map.getLayer('buildings-3d')) map.setLayoutProperty('buildings-3d','visibility','none');
    if (map.getLayer('buildings-fill')) map.setLayoutProperty('buildings-fill','visibility','visible');
    map.easeTo({ pitch:0, bearing:0, duration:700 });
  }
}
window.setView = setView;

/* ------------------------------------------------------------------ SEARCH (local, Cameroun-first) */
let searchTimer = null, searchAbort = null;
const searchCache = new Map();

$('q').addEventListener('input', e=>{
  const q = e.target.value.trim();
  $('q-clear').style.display = q ? 'flex' : 'none';
  clearTimeout(searchTimer);
  if (q.length < 2){ closeResults(); return; }
  searchTimer = setTimeout(()=>doSearch(q), 250);
});
$('q').addEventListener('keydown', e=>{ if(e.key==='Enter'){ clearTimeout(searchTimer); doSearch(e.target.value.trim()); }});
$('q-go').addEventListener('click', ()=>doSearch($('q').value.trim()));
$('q-clear').addEventListener('click', ()=>{ $('q').value=''; $('q-clear').style.display='none'; closeResults(); $('q').focus(); });

async function doSearch(q){
  if (!q || q.length<2) return;
  const c = map.getCenter();
  const key = q.toLowerCase()+'@'+c.lat.toFixed(3)+','+c.lng.toFixed(3);
  if (searchCache.has(key)){ renderResults(searchCache.get(key), q); return; }
  if (searchAbort) searchAbort.abort();
  searchAbort = new AbortController();
  const url = `/api/v1/places/search?q=${encodeURIComponent(q)}&grouped=true&limit=12`
            + `&lat=${c.lat}&lon=${c.lng}`;
  try{
    const r = await fetch(url, { signal:searchAbort.signal }).then(r=>r.json());
    searchCache.set(key, r);
    renderResults(r, q);
  }catch(err){ if(err.name!=='AbortError') console.error('search',err); }
}

function renderResults(data, q){
  const groups = data.groups || {};
  const box = $('results');
  // Cameroun-first ordering of groups
  const order = [
    ['districts','Quartiers & zones'],
    ['neighborhoods','Quartiers'],
    ['places','Lieux & services'],
    ['buildings','Bâtiments'],
    ['roads','Rues']
  ];
  let html='';
  let total=0;
  for (const [gk,label] of order){
    const items = groups[gk]||[];
    if (!items.length) continue;
    html += `<div class="res-group-title">${label}</div>`;
    for (const it of items){
      total++;
      html += resItemHtml(it);
    }
  }
  if (!total){
    const flat = data.results||[];
    if (flat.length){
      html='<div class="res-group-title">Résultats</div>';
      for (const it of flat) html += resItemHtml(it);
    } else {
      html = `<div class="res-empty">Aucun résultat au Cameroun pour « ${esc(q)} ».</div>`;
    }
  }
  box.innerHTML = html;
  box.classList.add('show');
  renderIcons();
  box.querySelectorAll('.res-item').forEach(el=>{
    el.addEventListener('click', ()=>pickResult(el.dataset));
  });
}
function fmtDistShort(m){
  if (m==null || !Number.isFinite(m)) return '';
  return m>=1000 ? (m/1000).toFixed(m<10000?1:0)+' km' : Math.round(m)+' m';
}
function confDot(c){
  if (c==null) return '';
  const cls = c>=0.85 ? 'conf-hi' : (c>=0.65 ? 'conf-mid' : 'conf-lo');
  const title = 'Confiance ' + Math.round(c*100) + '%';
  return `<span class="conf-dot ${cls}" title="${title}"></span>`;
}
function resItemHtml(it){
  const ic = iconFor(it.category, it.kind);
  const sub = [prettyCat(it.category), it.city ? cap(it.city) : ''].filter(Boolean).join(' · ');
  const dist = fmtDistShort(it.distance_m);
  return `<div class="res-item" data-lat="${it.latitude}" data-lon="${it.longitude}"
      data-name="${esc(it.name)}" data-cat="${esc(it.category||'')}" data-kind="${esc(it.kind||'')}">
    <div class="res-ico"><i data-lucide="${ic}" class="lucide" width="17" height="17"></i></div>
    <div class="res-txt"><div class="res-name">${confDot(it.confidence)}${esc(it.name)}</div>
      <div class="res-sub">${esc(sub)||'Cameroun'}</div></div>
    ${dist ? `<div class="res-dist">${dist}</div>` : ''}
  </div>`;
}

// Marqueur "ICI" de destination / résultat de recherche.
// Élément DOM custom (épingle animée) — distinct du marqueur d'origine (bleu) et du GPS.
function setDestMarker(lat, lon, label){
  if (!(Number.isFinite(lat) && Number.isFinite(lon))) return;
  if (!destMarker){
    const el = document.createElement('div');
    el.className = 'dest-marker';
    el.innerHTML =
      '<div class="dest-pin"><i data-lucide="map-pin" class="lucide" width="18" height="18"></i></div>'
      + '<div class="dest-label"></div>';
    destMarker = new maplibregl.Marker({ element:el, anchor:'bottom' })
      .setLngLat([lon, lat]).addTo(map);
    renderIcons(el);
  } else {
    destMarker.setLngLat([lon, lat]);
  }
  const lbl = destMarker.getElement().querySelector('.dest-label');
  if (lbl) lbl.textContent = label || 'ICI';
}
function clearDestMarker(){ if (destMarker){ destMarker.remove(); destMarker = null; } }
window.setDestMarker = setDestMarker;
window.clearDestMarker = clearDestMarker;

function pickResult(d){
  const lat=parseFloat(d.lat), lon=parseFloat(d.lon);
  closeResults();
  $('q').value = d.name;
  // VALIDATION GÉOGRAPHIQUE : un résultat sans position exploitable ne doit
  // jamais aboutir à un état "sélectionné" silencieux.
  if (!(Number.isFinite(lat) && Number.isFinite(lon))){
    toast('Ce résultat n’a pas de position géographique exploitable.');
    return;
  }
  const z = d.kind==='division' ? 14 : 17;
  // 1) point réel -> 2) zoom automatique -> 3) marker "ICI" -> 4) panneau de confirmation
  map.flyTo({ center:[lon,lat], zoom:z, pitch:currentView==='3d'?55:0, duration:1100 });
  setDestMarker(lat, lon, d.name);
  showPlacePanel({ title:d.name, subtitle:prettyCat(d.cat)||'Lieu', lat, lon,
    type:d.kind||'poi', category:d.cat });
}
function closeResults(){ $('results').classList.remove('show'); }
document.addEventListener('click', e=>{ if(!e.target.closest('.search-wrap')) closeResults(); });

function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
function cap(s){ s=String(s||''); return s.charAt(0).toUpperCase()+s.slice(1); }
function prettyCat(c){ if(!c) return ''; return cap(String(c).replace(/_/g,' ')); }

/* ------------------------------------------------------------------ ORIGIN SEARCH + MARKER */
function setOriginPoint(lat, lng, name){
  originPos = { lat, lng, name: name || 'Origine' };
  if (!originMarker){
    const el = document.createElement('div');
    el.style.cssText='width:16px;height:16px;border-radius:50%;background:#16a34a;border:3px solid #fff;box-shadow:0 0 0 4px rgba(22,163,74,.3)';
    originMarker = new maplibregl.Marker({element:el}).setLngLat([lng,lat]).addTo(map);
  } else originMarker.setLngLat([lng,lat]);
  setOriginLabel();
}
window.setOriginPoint = setOriginPoint;

let originSearchTimer=null, originSearchAbort=null;
const rcoq = $('rc-origin-q');
if (rcoq){
  rcoq.addEventListener('input', e=>{
    const q = e.target.value.trim();
    clearTimeout(originSearchTimer);
    if (q.length<2){ $('rc-origin-results').classList.remove('show'); return; }
    originSearchTimer = setTimeout(()=>doOriginSearch(q), 250);
  });
}
async function doOriginSearch(q){
  const c = map.getCenter();
  if (originSearchAbort) originSearchAbort.abort();
  originSearchAbort = new AbortController();
  const url = `/api/v1/places/search?q=${encodeURIComponent(q)}&grouped=true&limit=8&lat=${c.lat}&lon=${c.lng}`;
  try{
    const r = await fetch(url, { signal:originSearchAbort.signal }).then(r=>r.json());
    const box = $('rc-origin-results');
    const groups = r.groups||{};
    const flat = [].concat(groups.districts||[], groups.neighborhoods||[], groups.places||[], groups.buildings||[], groups.roads||[]);
    const items = flat.length?flat:(r.results||[]);
    if (!items.length){ box.innerHTML='<div class="res-empty">Aucun lieu trouvé.</div>'; box.classList.add('show'); return; }
    box.innerHTML = items.slice(0,8).map(resItemHtml).join('');
    box.classList.add('show'); renderIcons();
    box.querySelectorAll('.res-item').forEach(el=>{
      el.addEventListener('click', async ()=>{
        const d=el.dataset, lat=parseFloat(d.lat), lon=parseFloat(d.lon);
        if (Number.isFinite(lat)&&Number.isFinite(lon)){
          setOriginPoint(lat, lon, d.name);
          rcoq.value = d.name;
          box.classList.remove('show');
          $('rc-origin-search').classList.remove('show');
          await computeRoutes();
        }
      });
    });
  }catch(err){ if(err.name!=='AbortError') console.error('origin-search',err); }
}

/* ------------------------------------------------------------------ CATEGORIES (chips) */
async function loadCategories(){
  try{
    const r = await fetch('/api/v1/places/categories').then(r=>r.json());
    const cats = (r.categories||[]).slice(0,14);
    const box = $('chips');
    box.innerHTML = cats.map(c=>{
      const ic = CAT_ICON[c.category] || 'map-pin';
      return `<button class="chip" data-cat="${esc(c.category)}">
        <i data-lucide="${ic}" class="lucide"></i>${prettyCat(c.category)}</button>`;
    }).join('');
    renderIcons();
    box.querySelectorAll('.chip').forEach(el=>{
      el.addEventListener('click', ()=>toggleCategory(el, el.dataset.cat));
    });
  }catch(e){ console.warn('categories',e); }
}
let activeCategory = null;
async function toggleCategory(el, cat){
  const box=$('chips');
  if (activeCategory===cat){ activeCategory=null; el.classList.remove('active'); clearCategory(); return; }
  box.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));
  el.classList.add('active'); activeCategory=cat;
  const c=map.getCenter();
  try{
    const r = await fetch(`/api/v1/places/by-category?category=${encodeURIComponent(cat)}&lat=${c.lat}&lon=${c.lng}&radius=6000&limit=80`).then(r=>r.json());
    showCategoryResults(r.results||[], cat);
  }catch(e){ toast('Erreur catégorie'); }
}
function showCategoryResults(rows, cat){
  const fc = { type:'FeatureCollection', features: rows.map(p=>({
    type:'Feature', geometry:{type:'Point',coordinates:[p.longitude,p.latitude]},
    properties:{ name:p.name, category:cat } })) };
  if (map.getSource('cat')) map.getSource('cat').setData(fc);
  else {
    map.addSource('cat', { type:'geojson', data:fc });
    map.addLayer({ id:'cat-halo', type:'circle', source:'cat',
      paint:{ 'circle-radius':11, 'circle-color':'#f97316', 'circle-opacity':0.18 } });
    map.addLayer({ id:'cat-dot', type:'circle', source:'cat',
      paint:{ 'circle-radius':6, 'circle-color':'#f97316', 'circle-stroke-width':2, 'circle-stroke-color':'#fff' } });
    map.on('click','cat-dot', e=>{
      const p=e.features[0].properties, c=e.features[0].geometry.coordinates;
      showPlacePanel({ title:p.name, subtitle:prettyCat(cat), lat:c[1], lon:c[0], type:'poi', category:cat });
    });
    map.on('mouseenter','cat-dot',()=>map.getCanvas().style.cursor='pointer');
    map.on('mouseleave','cat-dot',()=>map.getCanvas().style.cursor='');
  }
  if (rows.length){
    const b = rows.reduce((bb,p)=>bb.extend([p.longitude,p.latitude]),
      new maplibregl.LngLatBounds([rows[0].longitude,rows[0].latitude],[rows[0].longitude,rows[0].latitude]));
    map.fitBounds(b, { padding:80, maxZoom:16, duration:800 });
  }
  toast(`${rows.length} ${prettyCat(cat).toLowerCase()} à proximité`);
}
function clearCategory(){
  if (map.getLayer('cat-dot')) map.removeLayer('cat-dot');
  if (map.getLayer('cat-halo')) map.removeLayer('cat-halo');
  if (map.getSource('cat')) map.removeSource('cat');
}

/* ------------------------------------------------------------------ CLICK -> 3-level identify */
map.on('click', async e=>{
  if (nav.active) return;
  // Mode "origine sur la carte" : le clic définit le point de départ.
  if (pickingOrigin){
    const { lat, lng } = e.lngLat;
    setOriginPoint(lat, lng, 'Point sur la carte');
    pickingOrigin = false;
    toast('Origine définie');
    await computeRoutes();
    return;
  }
  if (e._mnHandled) return;                      // a POI/cat feature already handled it
  const feats = map.queryRenderedFeatures(e.point, { layers:layersPresent(['pois','cat-dot']) });
  if (feats.length) return;                      // handled by their own click handlers
  const { lat, lng } = e.lngLat;

  const [bld, dist] = await Promise.all([
    fetch(`/api/v1/places/building-at?lat=${lat}&lon=${lng}&radius=45`).then(r=>r.json()).catch(()=>null),
    fetch(`/api/v1/places/nearest-district?lat=${lat}&lon=${lng}`).then(r=>r.json()).catch(()=>null)
  ]);
  const building = bld && bld.buildings && bld.buildings[0];
  const districtName = dist && dist.name;

  if (building){
    showPlacePanel({
      title: (building.label||'Bâtiment').trim(),
      subtitle: prettyCat(building.poi_category||building.class)||'Bâtiment',
      district: districtName, districtSub: dist && dist.subtype,
      city: building.city, lat:building.latitude, lon:building.longitude,
      type:'building', category:building.poi_category||building.class,
      distance_m: building.distance_m
    });
  } else if (districtName){
    showPlacePanel({
      title: districtName, subtitle: prettyCat(dist.subtype)||'Quartier',
      city: dist.city, lat, lon:lng, type:'division', category:dist.subtype
    });
  }
  // else: empty area -> show nothing
});
function layersPresent(ids){ return ids.filter(id=>map.getLayer(id)); }

/* ------------------------------------------------------------------ PLACE PANEL */
async function showPlacePanel(p){
  selectedPlace = p;
  $('pp-title').textContent = p.title || '—';
  $('pp-sub').textContent = p.subtitle || '';
  $('pp-ico').innerHTML = `<i data-lucide="${iconFor(p.category,p.type)}" class="lucide" width="24" height="24"></i>`;

  let rows = '';
  const typeLabel = p.type==='building' ? 'Bâtiment' : p.type==='division' ? 'Quartier / zone' : 'Lieu';
  rows += ppRow('tag', typeLabel);
  if (p.city) rows += ppRow('building-2', cap(p.city));
  if (p.district && p.type==='building') rows += ppRow('map', 'Quartier : '+p.district);
  if (Number.isFinite(p.lat)&&Number.isFinite(p.lon))
    rows += ppRow('map-pin', p.lat.toFixed(5)+', '+p.lon.toFixed(5));
  if (userPos){
    const d = haversine(userPos, {lat:p.lat,lng:p.lon});
    rows += ppRow('ruler', 'À '+fmtDist(d)+' de vous');
  }
  rows += `<div class="pp-row" id="pp-status"><i data-lucide="clock" class="lucide" width="18" height="18"></i>
           <span class="badge unknown">Horaires inconnus</span></div>`;
  $('pp-body').innerHTML = rows;
  $('place-panel').classList.add('show');
  $('route-choose').classList.remove('show');
  renderIcons();

  if (p.type==='poi' || p.type==='building'){
    try{
      const r = await fetch(`/api/v1/places/status?lat=${p.lat}&lon=${p.lon}&name=${encodeURIComponent(p.title||'')}`).then(r=>r.json());
      applyStatus(r);
    }catch(e){/* keep unknown */}
  }
}
function applyStatus(r){
  const el = $('pp-status'); if(!el) return;
  let isOpen = null, label = 'Horaires inconnus', nextChange = null;
  if (r){
    const src = (r.result && typeof r.result==='object') ? r.result : r;
    if (typeof src.is_open === 'boolean') isOpen = src.is_open;
    if (src.label) label = src.label;
    if (src.next_change) nextChange = src.next_change;
  }
  let cls='unknown', txt=label||'Horaires inconnus';
  if (isOpen===true){ cls='open'; txt='Ouvert'+(nextChange?` · ferme ${nextChange}`:''); }
  else if (isOpen===false){ cls='closed'; txt='Fermé'+(nextChange?` · ouvre ${nextChange}`:''); }
  el.innerHTML = `<i data-lucide="clock" class="lucide" width="18" height="18"></i><span class="badge ${cls}">${esc(txt)}</span>`;
  renderIcons();
}
function ppRow(icon, text){
  return `<div class="pp-row"><i data-lucide="${icon}" class="lucide" width="18" height="18"></i><span>${esc(text)}</span></div>`;
}
function closePlacePanel(){ $('place-panel').classList.remove('show'); }
window.closePlacePanel = closePlacePanel;
window.showPlacePanel = showPlacePanel;

/* ------------------------------------------------------------------ ORIGINE LIBRE */
// Coordonnées d'origine effectives selon le mode courant.
function resolveOrigin(){
  if (originMode === 'gps') return userPos ? {lat:userPos.lat, lng:userPos.lng, name:'Ma position'} : null;
  return originPos; // 'map' ou 'search'
}
function setOriginLabel(){
  const o = resolveOrigin();
  const el = $('rc-origin-val');
  if (!el) return;
  if (originMode === 'gps') el.textContent = userPos ? 'Ma position (GPS)' : 'Ma position (GPS non fixée)';
  else if (o && o.name) el.textContent = o.name;
  else if (originMode === 'map') el.textContent = pickingOrigin ? 'Touchez la carte…' : 'Choisir sur la carte';
  else el.textContent = 'Rechercher l’origine…';
}
function setOriginMode(mode){
  originMode = mode;
  ['gps','map','search'].forEach(m=>{
    const b = $('rc-o-'+m); if (b) b.classList.toggle('on', m===mode);
  });
  $('rc-origin-search').classList.toggle('show', mode==='search');
  pickingOrigin = (mode==='map');
  if (mode==='gps'){ pickingOrigin=false; if(!userPos) locateMe(true).then(setOriginLabel); }
  if (mode==='map'){ toast('Touchez la carte pour définir l’origine'); }
  if (mode==='search'){ setTimeout(()=>$('rc-origin-q') && $('rc-origin-q').focus(), 60); }
  setOriginLabel();
}
window.setOriginMode = setOriginMode;

function setProfile(p){
  travelProfile = p;
  document.querySelectorAll('#rc-profiles .rc-prof').forEach(el=>{
    el.classList.toggle('sel', el.dataset.profile===p);
  });
  // VRAI profil : on RECALCULE l'itinéraire côté moteur (géométrie + durée
  // propres au mode). On ne truque JAMAIS l'ETA d'une route voiture.
  if (selectedPlace && resolveOrigin()){ computeRoutes(); }
}
window.setProfile = setProfile;

// La durée vient désormais du moteur (Valhalla/OSRM selon le profil).
// Plus de multiplicateur : profDuration = identité (conservée pour compat).
function profDuration(sec){ return sec; }
let lastEngine = null;   // 'osrm' | 'valhalla' | ... renvoyé par le backend

/* ------------------------------------------------------------------ ROUTING */
// Point d'entrée depuis le panneau lieu : ouvre le sélecteur d'itinéraire.
async function planRouteToCurrent(){
  if (!selectedPlace){ return; }
  closePlacePanel();
  // Origine par défaut = GPS ; on tente une localisation silencieuse.
  if (originMode === 'gps' && !userPos){ toast('Localisation en cours…'); await locateMe(true); }
  nav.destName = selectedPlace.title;
  $('rc-dest-val').textContent = selectedPlace.title;
  setOriginLabel();
  await computeRoutes();
  // Affiche le sélecteur même si le calcul a échoué (l'utilisateur peut changer l'origine)
  $('route-choose').classList.add('show');
  renderIcons();
}
window.planRouteToCurrent = planRouteToCurrent;

// Calcule les itinéraires en fonction de l'origine résolue + destination.
async function computeRoutes(){
  const o = resolveOrigin();
  if (!o){
    routeOptions = []; chosenRoute = null; clearRoute();
    $('rc-hint').textContent = 'Définissez une origine (GPS, carte ou recherche).';
    $('rc-list').innerHTML=''; return false;
  }
  if (!selectedPlace){ return false; }
  $('rc-hint').textContent = 'Calcul de l’itinéraire ('+(PROFILE_LABEL[travelProfile]||travelProfile)+')…';
  try{
    const r = await fetch('/api/routing/alternatives', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ from_lat:o.lat, from_lon:o.lng,
        to_lat:selectedPlace.lat, to_lon:selectedPlace.lon, count:3,
        costing: travelProfile })          // VRAI profil envoyé au moteur
    }).then(r=>r.json());
    lastEngine = r.engine || null;
    routeOptions = (r.routes||[]).slice(0,3);
    if (!routeOptions.length){ $('rc-hint').textContent='Aucun itinéraire trouvé.'; $('rc-list').innerHTML=''; return false; }
    showRouteChooser();
    return true;
  }catch(e){ $('rc-hint').textContent='Erreur lors du calcul.'; return false; }
}
window.computeRoutes = computeRoutes;

function showRouteChooser(){
  const o = resolveOrigin();
  const eng = lastEngine ? ('  ·  moteur: '+lastEngine) : '';
  $('rc-hint').textContent = (o?o.name:'—') + '  →  ' + (selectedPlace?selectedPlace.title:'—')
     + '   ·   ' + (PROFILE_LABEL[travelProfile]||'') + eng;
  const labels = ['Le plus rapide','Alternative','Alternative 2'];
  $('rc-list').innerHTML = routeOptions.map((rt,i)=>`
    <div class="rc-opt ${i===0?'sel':''}" data-i="${i}">
      <i data-lucide="${i===0?'zap':'route'}" class="lucide" width="22" height="22"></i>
      <div><div class="rc-main">${labels[i]||('Option '+(i+1))}</div>
      <div class="rc-meta">${fmtDist(rt.distance)} · ${fmtDur(profDuration(rt.duration))}${rt.badges&&rt.badges.has_unpaved?' · ⚠ piste':''}</div></div>
    </div>`).join('');
  chosenRoute = routeOptions[0];
  drawRoute(chosenRoute, true);
  $('route-choose').classList.add('show');
  renderIcons();
  $('rc-list').querySelectorAll('.rc-opt').forEach(el=>{
    el.addEventListener('click', ()=>{
      $('rc-list').querySelectorAll('.rc-opt').forEach(x=>x.classList.remove('sel'));
      el.classList.add('sel');
      chosenRoute = routeOptions[parseInt(el.dataset.i,10)];
      drawRoute(chosenRoute, true);
    });
  });
}

function drawRoute(rt, fit){
  const coords = rt.geometry.coordinates;
  const gj = { type:'Feature', geometry:{ type:'LineString', coordinates:coords } };
  if (map.getSource('route')) map.getSource('route').setData(gj);
  else {
    map.addSource('route', { type:'geojson', data:gj });
    map.addLayer({ id:'route-casing', type:'line', source:'route',
      layout:{'line-cap':'round','line-join':'round'},
      paint:{ 'line-color':'#1e3a8a', 'line-width':9, 'line-opacity':0.9 } });
    map.addLayer({ id:'route-line', type:'line', source:'route',
      layout:{'line-cap':'round','line-join':'round'},
      paint:{ 'line-color':'#3b82f6', 'line-width':5.5 } });
  }
  if (fit){
    const b = coords.reduce((bb,c)=>bb.extend(c), new maplibregl.LngLatBounds(coords[0],coords[0]));
    map.fitBounds(b, { padding:{top:90,bottom:230,left:50,right:50}, duration:900 });
  }
}
function clearRoute(){
  ['route-line','route-casing'].forEach(l=>{ if(map.getLayer(l)) map.removeLayer(l); });
  if (map.getSource('route')) map.removeSource('route');
}

/* ------------------------------------------------------------------ NAVIGATION */
async function startNavigation(){
  if (!chosenRoute) return;
  if (!userPos){
    const enabled = await activateTracking();
    if (!enabled && !userPos){ toast('Position GPS requise pour démarrer'); return; }
  } else {
    await enableMotionSensors();
    startGpsWatch();
  }
  nav.active = true; nav.route = chosenRoute;
  nav.steps = (chosenRoute.steps||[]); nav.currentStep=0;
  nav.offRouteSince=null; nav.rerouting=false;
  $('route-choose').classList.remove('show');
  $('nav-top').classList.add('show');
  $('nav-bottom').classList.add('show');
  updateNavPanel(chosenRoute.distance, profDuration(chosenRoute.duration), firstInstruction());
  map.easeTo({ pitch:60, zoom:17, bearing:sensorState.heading||map.getBearing(), duration:900 });
}
window.startNavigation = startNavigation;

function firstInstruction(){
  if (nav.steps && nav.steps.length){
    const s=nav.steps[Math.min(nav.currentStep||0, nav.steps.length-1)];
    return s.instruction||s.text||'Continuez tout droit';
  }
  return 'Suivez l’itinéraire vers '+ (nav.destName||'la destination');
}
function updateNavPanel(distRemain, durRemain, instr){
  $('nav-instr').textContent = instr || '—';
  $('nav-dist').textContent = fmtDist(distRemain);
  $('nav-eta').textContent = fmtDur(durRemain);
  $('nav-meta').textContent = fmtDist(distRemain)+' restants vers '+(nav.destName||'destination');
}
function onNavPosition(pos){
  if (!nav.route || !nav.route.geometry) return;
  const coords = nav.route.geometry.coordinates;
  const closest = NavMath.closestRouteSegment(userPos, coords);
  let rem=0;
  for(let i=closest.segmentIndex;i<coords.length-1;i++){
    rem+=haversine({lng:coords[i][0],lat:coords[i][1]},{lng:coords[i+1][0],lat:coords[i+1][1]});
  }
  while(nav.currentStep<nav.steps.length-1){
    const step=nav.steps[nav.currentStep];
    const loc=step.location||step.position;
    if(!Array.isArray(loc) || loc.length<2 || haversine(userPos,{lng:loc[0],lat:loc[1]})>=40) break;
    nav.currentStep++;
  }
  const durRem = profDuration(nav.route.duration * (rem/Math.max(nav.route.distance,1)));
  updateNavPanel(rem, durRem, firstInstruction());

  const decision=NavMath.shouldReroute({
    distance:closest.distance, accuracy:gpsAccuracy||0, now:Date.now(),
    offRouteSince:nav.offRouteSince, lastRerouteAt:nav.lastRerouteAt,
    rerouting:nav.rerouting, threshold:80, confirmationMs:4000, cooldownMs:20000
  });
  nav.offRouteSince=decision.offRouteSince;
  if(closest.distance>decision.effectiveThreshold){
    setRerouteState(`écart ${Math.round(closest.distance)} m`, true);
  }else if(!nav.rerouting){
    setRerouteState('sur itinéraire');
  }
  if(decision.trigger) recalcRoute();
  if (rem < 30){ toast('Vous êtes arrivé'); stopNavigation(); }
}
async function recalcRoute(){
  if (!userPos || !selectedPlace || nav.rerouting) return false;
  nav.rerouting=true; nav.lastRerouteAt=Date.now();
  setRerouteState('recalcul…', true); toast('Recalcul de l’itinéraire…');
  try{
    const response = await fetch('/api/routing/alternatives',{ method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({ from_lat:userPos.lat, from_lon:userPos.lng,
        to_lat:selectedPlace.lat, to_lon:selectedPlace.lon, count:1,
        costing: travelProfile }) });
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const r=await response.json();
    if (!(r.routes && r.routes[0])) throw new Error('aucun itinéraire');
    nav.route=r.routes[0]; nav.steps=nav.route.steps||[]; nav.currentStep=0;
    nav.offRouteSince=null; chosenRoute=nav.route;
    drawRoute(nav.route,false); setRerouteState('recalculé');
    toast('Nouvel itinéraire prêt'); return true;
  }catch(e){
    console.error('rerouting',e); setRerouteState('échec',true);
    toast('Recalcul impossible — nouvel essai automatique'); return false;
  }finally{ nav.rerouting=false; }
}
function stopNavigation(){
  nav.active=false; nav.offRouteSince=null; nav.rerouting=false;
  $('nav-top').classList.remove('show');
  $('nav-bottom').classList.remove('show');
  setRerouteState('prête'); clearRoute();
  map.easeTo({ pitch: currentView==='3d'?60:0, bearing:0, duration:700 });
}
window.stopNavigation = stopNavigation;

/* ---------------------------------------------------- GEOLOCATION + SENSORS */
function showSecurityDiagnostic(){
  const banner=$('permission-banner'); if(!banner) return;
  if(window.isSecureContext){ banner.hidden=true; return; }
  banner.hidden=false;
  banner.innerHTML='<b>GPS et capteurs bloqués :</b> ouvrez MapNet via HTTPS. Les navigateurs refusent ces permissions sur une adresse HTTP publique.';
}
function setUserMarker(pos){
  if (!userMarker){
    const el=document.createElement('div');
    el.style.cssText='width:32px;height:32px;display:flex;align-items:center;justify-content:center;filter:drop-shadow(0 2px 4px rgba(0,0,0,.35))';
    el.innerHTML='<svg viewBox="0 0 32 32" width="32" height="32" aria-label="Position et orientation"><path d="M16 2 L27 28 L16 22 L5 28 Z" fill="#2563eb" stroke="#fff" stroke-width="2.5"/></svg>';
    userMarker = new maplibregl.Marker({element:el,rotationAlignment:'map',pitchAlignment:'map'})
      .setLngLat([pos.lng,pos.lat]).addTo(map);
  } else userMarker.setLngLat([pos.lng,pos.lat]);
  if(sensorState.heading!=null) userMarker.setRotation(sensorState.heading);
}
function consumePosition(pos, recenter=false){
  userPos={ lat:pos.coords.latitude, lng:pos.coords.longitude };
  gpsAccuracy=Number.isFinite(pos.coords.accuracy)?pos.coords.accuracy:null;
  if(sensorState.heading==null && Number.isFinite(pos.coords.heading)) sensorState.heading=NavMath.normalizeHeading(pos.coords.heading);
  setUserMarker(userPos); setOriginLabel(); updateSensorHud();
  if(nav.active){
    map.easeTo({center:[userPos.lng,userPos.lat],bearing:sensorState.heading||map.getBearing(),duration:500});
    onNavPosition(pos);
  }else if(recenter){
    map.flyTo({center:[userPos.lng,userPos.lat],zoom:16,duration:1000});
  }
}
function geolocationError(error, silent=false){
  setText('gps-state', error && error.code===1 ? 'permission refusée' : 'indisponible');
  if(!silent) toast(error && error.code===1 ? 'Autorisez la localisation dans le navigateur' : 'Position GPS indisponible');
}
function startGpsWatch(){
  if(geoWatchId!=null || !('geolocation' in navigator) || !window.isSecureContext) return false;
  geoWatchId=navigator.geolocation.watchPosition(
    pos=>consumePosition(pos,false), err=>geolocationError(err,true),
    {enableHighAccuracy:true,maximumAge:1000,timeout:12000});
  updateSensorHud(); return true;
}
function locateMe(silent){
  return new Promise(resolve=>{
    showSecurityDiagnostic();
    if(!window.isSecureContext){ if(!silent)toast('HTTPS requis pour le GPS'); return resolve(false); }
    if(!('geolocation' in navigator)){ if(!silent)toast('Géolocalisation non disponible'); return resolve(false); }
    navigator.geolocation.getCurrentPosition(pos=>{
      consumePosition(pos,!silent); resolve(true);
    }, err=>{ geolocationError(err,silent); resolve(false); },
    {enableHighAccuracy:true,maximumAge:0,timeout:12000});
  });
}
async function requestSensorPermission(eventType){
  if(!eventType || typeof eventType.requestPermission!=='function') return true;
  try{ return (await eventType.requestPermission())==='granted'; }
  catch(error){ console.warn('sensor permission',error); return false; }
}
function orientationHeading(event){
  if(Number.isFinite(event.webkitCompassHeading)) return NavMath.normalizeHeading(event.webkitCompassHeading);
  if(Number.isFinite(event.alpha)) return NavMath.normalizeHeading(360-event.alpha);
  return null;
}
async function enableMotionSensors(){
  if(sensorsStarted) return true;
  if(!window.isSecureContext){ showSecurityDiagnostic(); return false; }
  const orientationAllowed=await requestSensorPermission(window.DeviceOrientationEvent);
  const motionAllowed=await requestSensorPermission(window.DeviceMotionEvent);
  if(orientationAllowed && 'DeviceOrientationEvent' in window){
    window.addEventListener('deviceorientationabsolute', handleOrientation, true);
    window.addEventListener('deviceorientation', handleOrientation, true);
  }
  if(motionAllowed && 'DeviceMotionEvent' in window) window.addEventListener('devicemotion', handleMotion, true);
  sensorsStarted=orientationAllowed||motionAllowed;
  if(!sensorsStarted) toast('Permission des capteurs refusée');
  return sensorsStarted;
}
function handleOrientation(event){
  const heading=orientationHeading(event); if(heading==null) return;
  sensorState.heading=heading;
  if(userMarker) userMarker.setRotation(heading);
  if(nav.active) map.easeTo({bearing:heading,duration:250});
  updateSensorHud();
}
function handleMotion(event){
  const a=event.accelerationIncludingGravity||event.acceleration;
  const r=event.rotationRate;
  if(a && [a.x,a.y,a.z].some(Number.isFinite)){
    sensorState.accel=Math.hypot(Number(a.x)||0,Number(a.y)||0,Number(a.z)||0);
  }
  if(r && [r.alpha,r.beta,r.gamma].some(Number.isFinite)){
    sensorState.gyro=Math.hypot(Number(r.alpha)||0,Number(r.beta)||0,Number(r.gamma)||0)*Math.PI/180;
  }
  updateSensorHud();
}
async function activateTracking(){
  showSecurityDiagnostic();
  if(!window.isSecureContext){ toast('Ouvrez MapNet en HTTPS pour activer GPS et capteurs',4000); return false; }
  await enableMotionSensors();
  startGpsWatch();
  return locateMe(false);
}
window.locateMe = locateMe;
window.activateTracking = activateTracking;

/* ------------------------------------------------------------------ STATS */
const fmtCount = n => (n==null ? '—' : Number(n).toLocaleString('fr-FR'));
async function loadStats(){
  try{
    // Compteurs réels par couche (PostGIS) — source de vérité unique
    const lc = await fetch('/api/v1/places/layer-counts').then(r=>r.json()).catch(()=>null);
    if (lc && lc.counts){
      const c = lc.counts;
      $('s-places').textContent    = fmtCount(c.pois);
      $('s-buildings').textContent = fmtCount(c.buildings);
      $('s-roads').textContent     = fmtCount(c.roads);
      $('s-districts').textContent = fmtCount(c.districts);
    }
    const s = await fetch('/api/stats').then(r=>r.json()).catch(()=>null);
    if (s && s.total!=null) $('s-caps').textContent = fmtCount(s.total);
    const ag = await fetch('/api/agents?minutes=10').then(r=>r.json()).catch(()=>null);
    if (ag){ const n = Array.isArray(ag)?ag.length:(ag.count||0); $('s-agents').textContent=n; }
  }catch(e){}
}

/* ---------------------------------------------------------------- COMPASS
 * Compas custom fiable (la NavigationControl MapLibre échouait sur appendChild
 * dans cette build). L'aiguille suit le bearing ; orientTo() pivote la carte ;
 * resetNorth() (défini plus haut) remet le nord. Rotation gestuelle : glisser
 * avec le bouton droit ou deux doigts (activé par défaut dans MapLibre).
 */
function orientTo(deg){ map.easeTo({ bearing: deg, duration: 500 }); }
window.orientTo = orientTo;
function updateCompassNeedle(){
  const n = document.getElementById('compass-needle');
  if (n) n.style.transform = 'rotate(' + (-map.getBearing()) + 'deg)';
}
map.on('rotate', updateCompassNeedle);
map.on('rotateend', updateCompassNeedle);

/* ------------------------------------------------------------------ INIT */
map.on('load', ()=>{
  addVectorLayers();
  addTerrain();          // DEM source ready; terrain enabled only in 3D view
  loadCategories();
  loadStats();
  updateCompassNeedle();
  renderIcons();
});
// Les icônes statiques du HTML sont rendues dès que le DOM est prêt (le script
// est en fin de <body>, donc le DOM existe déjà). loadStats() n'attend PAS la carte.
// createIcons() est idempotent : on l'appelle tout de suite, sur DOMContentLoaded,
// et après un court délai, pour couvrir tout aléa de chargement du CDN lucide.
function bootIcons(){
  showSecurityDiagnostic(); updateSensorHud();
  renderIcons();
  const left = document.querySelectorAll('[data-lucide]').length;
  if(left>0){ /* le script CDN n'est peut-être pas encore prêt : on réessaie */
    let tries=0;
    const t=setInterval(()=>{
      renderIcons();
      tries++;
      if(document.querySelectorAll('[data-lucide]').length===0 || tries>=20) clearInterval(t);
    },150);
  }
}
if(document.readyState==='loading'){
  document.addEventListener('DOMContentLoaded', bootIcons);
}else{
  bootIcons();
}
loadStats();
