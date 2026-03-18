// Gebaeude-Grundriss – SVG-Visualisierung
// Daten werden CSP-sicher via json_script aus dem Template gelesen.

var STRUKTUR    = JSON.parse(document.getElementById("grundriss-struktur").textContent);
var RAEUME      = JSON.parse(document.getElementById("grundriss-raeume").textContent);
var GESCHOSS_ID = JSON.parse(document.getElementById("grundriss-geschoss-id").textContent);
var GESCHOSS_KUERZEL = JSON.parse(document.getElementById("grundriss-kuerzel").textContent);

// ─── Farben ────────────────────────────────────────────────────────────────
var FARBEN = {
  einzelbuero: '#1d4ed8', konferenz: '#d97706', besprechung: '#ca8a04',
  schulung: '#c2410c', teekueche: '#065f46', pausenraum: '#047857',
  wc_herren: '#334155', wc_damen: '#334155', wc_barrierefrei: '#1e293b',
  druckerraum: '#5b21b6', eingang: '#713f12', windfang: '#78350f',
  flur: '#1e293b', heizungsraum: '#7f1d1d', lueftungsraum: '#991b1b',
  elektroverteilung: '#b91c1c', serverraum: '#7f1d1d', it_verteiler: '#991b1b',
  lager: '#78350f', archiv: '#713f12', abstellraum: '#57534e', putzraum: '#3f3f46',
};
var FARBE_FALLBACK = '#374151';
var IT_TYPEN = ['serverraum','it_verteiler','elektroverteilung','heizungsraum','lueftungsraum'];
var BUCHUNGS_TYPEN = ['konferenz','besprechung','schulung'];
var KEIN_SCHLOSS = ['wc_herren','wc_damen','wc_barrierefrei','flur','windfang','eingang','putzraum'];
var ELEKTRONISCH_TYPEN = ['serverraum','it_verteiler','elektroverteilung','konferenz','besprechung'];

// ─── Simulation ────────────────────────────────────────────────────────────
var simModus = 'tag';
var buchungsStatus = {};

function seededZufall(seed) {
  var x = Math.sin(seed + 1) * 10000;
  return x - Math.floor(x);
}

function simuliereLock(raumId) {
  var basis = seededZufall(raumId * 7 + (simModus === 'tag' ? 13 : 97));
  return simModus === 'tag' ? basis < 0.65 : basis < 0.01;
}

function simulierePing(raumId) {
  var v = seededZufall(raumId * 3 + 42);
  if (v < 0.75) return 'ok';
  if (v < 0.92) return 'warn';
  return 'err';
}

function simuliereTemp(raumId) {
  return (18 + seededZufall(raumId * 11) * 12).toFixed(1);
}

function setSimModus(modus) {
  simModus = modus;
  document.getElementById('btnTag').className   = 'sim-btn' + (modus === 'tag'   ? ' aktiv' : '');
  document.getElementById('btnNacht').className = 'sim-btn' + (modus === 'nacht' ? ' aktiv' : '');
  if (RAEUME.length) zeichneGrundriss(RAEUME);
}

// ─── Status API ────────────────────────────────────────────────────────────
function aktualisiereStatus() {
  if (!GESCHOSS_ID) return;
  fetch('/raumbuch/grundriss/status/?geschoss=' + GESCHOSS_ID)
    .then(function(r) { return r.json(); })
    .then(function(data) {
      buchungsStatus = data.raeume || {};
      if (RAEUME.length) zeichneGrundriss(RAEUME);
    }).catch(function() {});
}

// ─── SVG Hilfsfunktionen ────────────────────────────────────────────────────
function el(tag, attrs, children) {
  var e = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attrs || {}).forEach(function(kv) { e.setAttribute(kv[0], kv[1]); });
  (children || []).forEach(function(c) {
    if (typeof c === 'string') e.appendChild(document.createTextNode(c));
    else e.appendChild(c);
  });
  return e;
}
function rect(x, y, w, h, fill, attrs) {
  return el('rect', Object.assign({x: x, y: y, width: w, height: h, fill: fill, rx: 2}, attrs));
}
function textEl(x, y, str, attrs) {
  return el('text', Object.assign({x: x, y: y, 'font-family': 'Arial,sans-serif'}, attrs), [str]);
}

// ─── Moebel ────────────────────────────────────────────────────────────────
function zeichneBueroMoebel(g, x, y, w, h, seite) {
  var dx = seite === 'nord' ? x + w - 10 - 90 : x + 10;
  var dy = seite === 'nord' ? y + h - 10 - 50 : y + 10;
  g.appendChild(rect(dx, dy, 90, 50, '#1e3a5f', {rx: 3}));
  g.appendChild(rect(dx, dy, 90, 4, '#2563eb', {rx: 0}));
  g.appendChild(rect(dx + 25, dy + 8, 35, 22, '#0f172a', {rx: 2}));
  g.appendChild(rect(dx + 38, dy + 30, 10, 4, '#334155'));
  var cDy = seite === 'nord' ? dy - 34 : dy + 56;
  g.appendChild(el('ellipse', {cx: dx + 40, cy: cDy + 15, rx: 16, ry: 16, fill: '#374151'}));
  g.appendChild(rect(dx + 24, seite === 'nord' ? dy - 12 : dy + 52, 32, 10, '#475569', {rx: 4}));
}

function zeichneKonferenzMoebel(g, x, y, w, h) {
  var cx = x + w / 2, cy = y + h / 2;
  var tw = Math.min(w - 40, 200), th = 60;
  g.appendChild(el('ellipse', {cx: cx, cy: cy, rx: tw/2, ry: th/2, fill: '#1c3a2e', stroke: '#065f46', 'stroke-width': 2}));
  var anz = Math.min(Math.floor(tw / 30), 8);
  for (var i = 0; i < anz; i++) {
    var a = (i / anz) * Math.PI * 2;
    var sx = cx + (tw/2 + 18) * Math.cos(a);
    var sy = cy + (th/2 + 18) * Math.sin(a);
    g.appendChild(el('ellipse', {cx: sx, cy: sy, rx: 12, ry: 12, fill: '#374151'}));
  }
}

function zeichneTKMoebel(g, x, y, w, h) {
  g.appendChild(rect(x + 6, y + 6, w - 12, 38, '#134e4a', {rx: 4}));
  g.appendChild(el('ellipse', {cx: x + 30, cy: y + 26, rx: 12, ry: 12, fill: '#0f172a', stroke: '#0d9488', 'stroke-width': 2}));
  g.appendChild(rect(x + 8, y + 50, 50, 25, '#1e293b', {rx: 2}));
}

function zeichneServerMoebel(g, x, y, w, h) {
  var rw = 32, rh = h - 20;
  var rx0 = x + (w - rw * 2 - 10) / 2;
  [rx0, rx0 + rw + 10].forEach(function(rx2, i) {
    g.appendChild(rect(rx2, y + 10, rw, rh, '#0f172a', {rx: 2, stroke: '#1e3a5f', 'stroke-width': 1}));
    for (var j = 0; j < 6; j++) {
      g.appendChild(rect(rx2 + 3, y + 14 + j * (rh - 10) / 6, rw - 6, 4, i === 0 ? '#16a34a' : '#1d4ed8', {rx: 1}));
    }
  });
}

// ─── Tuer ────────────────────────────────────────────────────────────────
function zeichneTuer(g, tx, ty, richtung, oeffnungsSeite) {
  var L = 36, d;
  if (richtung === 'sued') {
    if (oeffnungsSeite === 'links') {
      d = 'M ' + tx + ' ' + ty + ' L ' + tx + ' ' + (ty + L) + ' A ' + L + ' ' + L + ' 0 0 1 ' + (tx + L) + ' ' + ty;
    } else {
      d = 'M ' + (tx + L) + ' ' + ty + ' L ' + (tx + L) + ' ' + (ty + L) + ' A ' + L + ' ' + L + ' 0 0 0 ' + tx + ' ' + ty;
    }
  } else {
    if (oeffnungsSeite === 'links') {
      d = 'M ' + tx + ' ' + ty + ' L ' + tx + ' ' + (ty - L) + ' A ' + L + ' ' + L + ' 0 0 0 ' + (tx + L) + ' ' + ty;
    } else {
      d = 'M ' + (tx + L) + ' ' + ty + ' L ' + (tx + L) + ' ' + (ty - L) + ' A ' + L + ' ' + L + ' 0 0 1 ' + tx + ' ' + ty;
    }
  }
  g.appendChild(el('path', {d: d, stroke: '#94a3b8', 'stroke-width': 1.5, fill: 'rgba(148,163,184,0.08)'}));
  var gapRect = richtung === 'sued'
    ? {x: tx, y: ty - 1, width: L, height: 5}
    : {x: tx, y: ty - 4, width: L, height: 5};
  g.appendChild(rect(gapRect.x, gapRect.y, gapRect.width, gapRect.height, '#0f172a', {stroke: 'none'}));
}

// ─── Fenster ───────────────────────────────────────────────────────────────
function zeichneFenster(g, x, y, w, aussenwandSeite) {
  var wy = aussenwandSeite === 'nord' ? y : y - 7;
  var slots = 3, sw = (w - 20) / slots;
  for (var i = 0; i < slots; i++) {
    var fx = x + 10 + i * sw;
    g.appendChild(rect(fx, wy, sw - 4, 7, '#bfdbfe', {rx: 1, opacity: 0.7}));
  }
}

// ─── Schloss-Indikator ─────────────────────────────────────────────────────
function zeichneLockIndikator(g, ix, iy, istOffen, istElektronisch) {
  var fill   = istOffen ? '#22c55e' : '#ef4444';
  var stroke = istElektronisch ? '#38bdf8' : fill;
  var sw     = istElektronisch ? 2 : 0;
  g.appendChild(el('circle', {cx: ix, cy: iy, r: 7, fill: fill, stroke: stroke, 'stroke-width': sw}));
  var sym = el('text', {x: ix, y: iy + 4, 'text-anchor': 'middle',
    'font-size': 8, fill: 'white', 'font-family': 'Arial'});
  sym.textContent = istElektronisch ? '\u26a1' : (istOffen ? '\u25CB' : '\u25CF');
  g.appendChild(sym);
}

// ─── Ping Indikator ────────────────────────────────────────────────────────
function zeichnePingIndikator(g, px, py, pingStatus) {
  var farben = {ok: '#22c55e', warn: '#fbbf24', err: '#ef4444'};
  [0, 8, 16].forEach(function(dx, i) {
    var alpha = i === 0 ? 1 : i === 1 ? 0.7 : 0.4;
    g.appendChild(el('circle', {cx: px + dx, cy: py, r: 3,
      fill: farben[pingStatus] || '#64748b', opacity: alpha}));
  });
  var lbl = el('text', {x: px - 2, y: py + 12, 'font-size': 7, fill: '#94a3b8', 'font-family': 'Arial'});
  lbl.textContent = pingStatus === 'ok' ? 'online' : pingStatus === 'warn' ? 'latenz' : 'offline';
  g.appendChild(lbl);
}

// ─── Temperatur Badge ─────────────────────────────────────────────────────
function zeichneTempBadge(g, bx, by, temp) {
  var t = parseFloat(temp);
  var fill = t < 22 ? '#166534' : t < 26 ? '#713f12' : '#7f1d1d';
  g.appendChild(rect(bx, by, 44, 16, fill, {rx: 3}));
  var lbl = el('text', {x: bx + 22, y: by + 12, 'text-anchor': 'middle',
    'font-size': 9, fill: 'white', 'font-family': 'Arial', 'font-weight': 'bold'});
  lbl.textContent = temp + '\u00b0C';
  g.appendChild(lbl);
}

// ─── Buchungs-Overlay ─────────────────────────────────────────────────────
function zeichneBuchungsOverlay(g, x, y, w, h, aktiv, naechste) {
  if (aktiv) {
    g.appendChild(rect(x + 4, y + 4, w - 8, 18, '#7f1d1d', {rx: 2, opacity: 0.92}));
    var lbl = el('text', {x: x + w/2, y: y + 16, 'text-anchor': 'middle',
      'font-size': 9, fill: '#fca5a5', 'font-weight': 'bold', 'font-family': 'Arial'});
    lbl.textContent = 'BELEGT';
    g.appendChild(lbl);
  } else if (naechste) {
    g.appendChild(rect(x + 4, y + 4, w - 8, 15, '#1c3a2e', {rx: 2, opacity: 0.9}));
    var lbl2 = el('text', {x: x + w/2, y: y + 14, 'text-anchor': 'middle',
      'font-size': 8, fill: '#6ee7b7', 'font-family': 'Arial'});
    lbl2.textContent = naechste.length > 14 ? naechste.slice(0, 14) + '\u2026' : naechste;
    g.appendChild(lbl2);
  }
}

// ─── Raum zeichnen ─────────────────────────────────────────────────────────
function zeichneRaum(g, raum, x, y, w, h, zone) {
  var fill = FARBEN[raum.typ] || FARBE_FALLBACK;
  var bs   = buchungsStatus[String(raum.id)] || {};
  var lock  = simuliereLock(raum.id);
  var istEl = ELEKTRONISCH_TYPEN.includes(raum.typ);
  var ohneSchloss = KEIN_SCHLOSS.includes(raum.typ);

  var raumEl = rect(x, y, w, h, fill, {stroke: '#0f172a', 'stroke-width': 2, rx: 3, style: 'cursor:pointer'});
  raumEl.addEventListener('click', (function(r, l, e, b) {
    return function() { zeigeInfo(r, l, e, b); };
  })(raum, lock, istEl, bs));
  g.appendChild(raumEl);

  if (zone === 'nord') zeichneFenster(g, x, y, w, 'nord');
  if (zone === 'sued') zeichneFenster(g, x, y + h, w, 'sued');

  var mg = el('g', {opacity: '0.9'});
  if (raum.typ === 'einzelbuero')  zeichneBueroMoebel(mg, x, y, w, h, zone === 'nord' ? 'nord' : 'sued');
  if (raum.typ === 'konferenz' || raum.typ === 'besprechung') zeichneKonferenzMoebel(mg, x, y, w, h);
  if (raum.typ === 'teekueche')    zeichneTKMoebel(mg, x, y, w, h);
  if (raum.typ === 'serverraum' || raum.typ === 'it_verteiler') zeichneServerMoebel(mg, x, y, w, h);
  g.appendChild(mg);

  var tuerX = x + w/2 - 18;
  if (zone === 'nord') zeichneTuer(g, tuerX, y + h, 'sued', 'links');
  if (zone === 'sued') zeichneTuer(g, tuerX, y, 'nord', 'links');
  if (zone === 'kern') {
    zeichneTuer(g, tuerX, y, 'nord', 'links');
    zeichneTuer(g, tuerX, y + h, 'sued', 'rechts');
  }
  if (zone === 'grid') zeichneTuer(g, tuerX, y + h, 'sued', 'links');

  if (!ohneSchloss) {
    var liy = zone === 'nord' ? y + h - 10 : (zone === 'sued' ? y + 10 : y + h/2);
    zeichneLockIndikator(g, x + w - 12, liy, lock, istEl);
  }

  if (IT_TYPEN.includes(raum.typ)) {
    zeichnePingIndikator(g, x + 8, y + 20, simulierePing(raum.id));
    if (raum.typ === 'serverraum') zeichneTempBadge(g, x + w - 50, y + 8, simuliereTemp(raum.id));
  }

  if (BUCHUNGS_TYPEN.includes(raum.typ)) {
    zeichneBuchungsOverlay(g, x, y, w, h, bs.buchung_aktiv, bs.naechste_buchung);
  }

  var lblY = zone === 'nord' ? y + h - 14 : y + 14;
  var lbl = el('text', {x: x + w/2, y: lblY + 4, 'text-anchor': 'middle', 'dominant-baseline': 'middle',
    'font-size': 10, 'font-weight': 'bold', fill: 'white', 'font-family': 'Arial',
    'paint-order': 'stroke', stroke: 'rgba(0,0,0,0.5)', 'stroke-width': 3, style: 'pointer-events:none'});
  lbl.textContent = raum.nummer;
  g.appendChild(lbl);
}

// ─── OG Etage (Standard 1-7) ───────────────────────────────────────────────
function zeichneOGEtage(svg, raeume) {
  var W = 900, WALL = 7, BUERO_H = 155, KORR = 46, KERN_H = 150;
  var yN0 = WALL, yN1 = yN0 + BUERO_H;
  var yKN1 = yN1 + KORR;
  var yK1 = yKN1 + KERN_H;
  var yKS1 = yK1 + KORR;
  var yS1 = yKS1 + BUERO_H;
  var TOTAL_H = yS1 + WALL;

  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + TOTAL_H);
  svg.setAttribute('height', TOTAL_H);

  var nord = raeume.filter(function(r) { return r.nummer.match(/A0[1-9]$|A[1-9][0-9]$/); }).sort(function(a, b) { return a.nummer.localeCompare(b.nummer); });
  var sued = raeume.filter(function(r) { return r.nummer.match(/B0[1-9]$|B[1-9][0-9]$/); }).sort(function(a, b) { return a.nummer.localeCompare(b.nummer); });
  var kern = raeume.filter(function(r) { return !r.nummer.match(/[AB]0[1-9]$/); }).sort(function(a, b) { return a.nummer.localeCompare(b.nummer); });

  var g = el('g', {});

  g.appendChild(rect(0, 0, W, WALL, '#475569'));
  g.appendChild(rect(0, yS1, W, WALL, '#475569'));
  g.appendChild(rect(0, yN1, W, KORR, '#1a2a3a'));
  g.appendChild(el('text', {x: 8, y: yN1 + KORR/2 + 5, 'font-size': 10, fill: '#334155', 'font-family': 'Arial'})).textContent = 'KORRIDOR NORD';
  g.appendChild(rect(0, yK1, W, KORR, '#1a2a3a'));
  g.appendChild(el('text', {x: 8, y: yK1 + KORR/2 + 5, 'font-size': 10, fill: '#334155', 'font-family': 'Arial'})).textContent = 'KORRIDOR SUED';

  var nW = nord.length > 0 ? W / nord.length : W;
  nord.forEach(function(raum, i) { zeichneRaum(g, raum, i * nW, yN0, nW, BUERO_H, 'nord'); });

  var sW = sued.length > 0 ? W / sued.length : W;
  sued.forEach(function(raum, i) { zeichneRaum(g, raum, i * sW, yKS1, sW, BUERO_H, 'sued'); });

  var kernBreiten = { konferenz: 300, besprechung: 300, teekueche: 300, wc_herren: 150, wc_damen: 150 };
  var gesamtKern = kern.reduce(function(s, r) { return s + (kernBreiten[r.typ] || 180); }, 0);
  var kx = 0;
  var skalierung = W / Math.max(gesamtKern, 1);
  kern.forEach(function(raum) {
    var kw = (kernBreiten[raum.typ] || 180) * skalierung;
    zeichneRaum(g, raum, kx, yKN1, kw, KERN_H, 'kern');
    kx += kw;
  });

  svg.appendChild(g);
}

// ─── Grid Etage (EG, UG, Reserve) ─────────────────────────────────────────
function zeichneGridEtage(svg, raeume) {
  var W = 900;
  var COLS = 5, RAUMW = W / COLS, RAUMH = 130;
  var ROWS = Math.ceil(raeume.length / COLS);
  var TOTAL_H = ROWS * RAUMH + 20;

  svg.setAttribute('viewBox', '0 0 ' + W + ' ' + TOTAL_H);
  svg.setAttribute('height', TOTAL_H);

  var g = el('g', {});
  raeume.forEach(function(raum, i) {
    var col = i % COLS, row = Math.floor(i / COLS);
    zeichneRaum(g, raum, col * RAUMW, row * RAUMH, RAUMW, RAUMH, 'grid');
  });
  svg.appendChild(g);
}

// ─── Hauptfunktion ─────────────────────────────────────────────────────────
function zeichneGrundriss(raeume) {
  var svg = document.getElementById('grundrissSvg');
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  if (!raeume || raeume.length === 0) return;

  var isOG = /^[1-9]$/.test(GESCHOSS_KUERZEL);
  if (isOG) {
    zeichneOGEtage(svg, raeume);
  } else {
    zeichneGridEtage(svg, raeume);
  }
}

// ─── Info Panel ────────────────────────────────────────────────────────────
function zeigeInfo(raum, lock, istEl, bs) {
  var panel = document.getElementById('infoPanel');
  var content = document.getElementById('infoPanelContent');
  panel.classList.add('offen');

  var lockFarbe = lock ? '#22c55e' : '#ef4444';
  var lockText  = lock ? 'Offen' : 'Verschlossen';
  var lockTyp   = istEl ? 'Elektronisch (Chipkarte)' : 'Mechanisch (Riegelkontakt)';

  var html = '<h5>' + raum.nummer + ' \u2013 ' + raum.name + '</h5>'
    + '<div class="info-typ">' + raum.typ.replace(/_/g,' ') + '</div>';

  if (raum.belegt_von) {
    html += '<div class="info-row"><span class="lbl">Belegt von</span><span class="val">' + raum.belegt_von + '</span></div>';
  }
  if (raum.flaeche) {
    html += '<div class="info-row"><span class="lbl">Flaeche</span><span class="val">' + raum.flaeche + ' m\u00b2</span></div>';
  }
  if (raum.kapazitaet) {
    html += '<div class="info-row"><span class="lbl">Kapazitaet</span><span class="val">' + raum.kapazitaet + ' Personen</span></div>';
  }

  if (!KEIN_SCHLOSS.includes(raum.typ)) {
    html += '<div class="info-row"><span class="lbl">Schloss</span>'
      + '<span class="val"><span style="color:' + lockFarbe + ';font-weight:bold;">' + lockText + '</span>'
      + '<br><small style="color:#64748b;">' + lockTyp + '</small></span></div>';
  }

  if (BUCHUNGS_TYPEN.includes(raum.typ)) {
    var aktiv = bs.buchung_aktiv;
    var naechste = bs.naechste_buchung;
    html += '<div class="info-row"><span class="lbl">Buchung jetzt</span>'
      + '<span class="val"><span class="status-badge ' + (aktiv ? 'status-err' : 'status-ok') + '">'
      + (aktiv ? 'BELEGT' : 'FREI') + '</span></span></div>';
    if (naechste) {
      html += '<div class="info-row"><span class="lbl">Naechste</span><span class="val">' + naechste + '</span></div>';
    }
  }

  if (IT_TYPEN.includes(raum.typ)) {
    var ping = simulierePing(raum.id);
    var farben = {ok: 'status-ok', warn: 'status-warn', err: 'status-err'};
    html += '<div class="info-row"><span class="lbl">Netzwerk (Ping)</span>'
      + '<span class="val"><span class="status-badge ' + farben[ping] + '">' + ping.toUpperCase() + '</span></span></div>';
    if (raum.typ === 'serverraum') {
      var temp = simuliereTemp(raum.id);
      var t = parseFloat(temp);
      var tf = t < 22 ? 'status-ok' : t < 26 ? 'status-warn' : 'status-err';
      html += '<div class="info-row"><span class="lbl">Temperatur</span>'
        + '<span class="val"><span class="status-badge ' + tf + '">' + temp + ' \u00b0C</span></span></div>';
    }
  }

  html += '<a href="' + raum.url + '" class="btn-detail">\u2192 Raumdetail oeffnen</a>';

  if (raum.hat_netzwerkplan) {
    html += '<a href="' + raum.netzwerkplan_url + '" class="btn-detail" style="margin-top:6px; background:#6366f1;">'
      + '\uD83D\uDCE1 Netzwerkplan / Rack-Belegung</a>';
  }

  content.innerHTML = html;
}

function schliesseInfoPanel() {
  document.getElementById('infoPanel').classList.remove('offen');
}

// ─── Navigation ────────────────────────────────────────────────────────────
function baueSidebar() {
  var nav = document.getElementById('navStruktur');
  STRUKTUR.forEach(function(gb) {
    var gbLbl = document.createElement('div');
    gbLbl.className = 'gb-label';
    gbLbl.textContent = gb.bezeichnung + ' (' + gb.kuerzel + ')';
    nav.appendChild(gbLbl);
    gb.geschosse.forEach(function(gs) {
      var a = document.createElement('a');
      a.className = 'gs-item' + (String(gs.id) === String(GESCHOSS_ID) ? ' aktiv' : '');
      a.textContent = gs.kuerzel + ' \u2013 ' + gs.bezeichnung;
      a.href = '?geschoss=' + gs.id;
      nav.appendChild(a);
    });
  });
}

// ─── Event-Handler verdrahten ──────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function() {
  document.getElementById("btnTag").addEventListener("click", function() { setSimModus('tag'); });
  document.getElementById("btnNacht").addEventListener("click", function() { setSimModus('nacht'); });
  document.getElementById("btnRefresh").addEventListener("click", aktualisiereStatus);
  document.getElementById("btnInfoClose").addEventListener("click", schliesseInfoPanel);

  baueSidebar();
  if (RAEUME.length) {
    zeichneGrundriss(RAEUME);
    aktualisiereStatus();
    setInterval(aktualisiereStatus, 30000);
  }
});
