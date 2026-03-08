/**
 * netzwerkplan_rack.js – Realistischer 19"-Rack SVG Renderer
 * Zeichnet einen vollstaendigen 42HE Serverschrank mit allen Komponenten,
 * Leerslots, Kabelkanaelen und Legende.
 */
(function () {
    "use strict";

    /* ------------------------------------------------------------------
       Farben & Typ-Konfiguration
    ------------------------------------------------------------------ */
    var TYPEN = {
        core_switch:          { farbe: "#6366f1", dunkel: "#3730a3", label: "Core-Switch"   },
        distribution_switch:  { farbe: "#8b5cf6", dunkel: "#5b21b6", label: "Dist-Switch"   },
        access_switch:        { farbe: "#a78bfa", dunkel: "#7c3aed", label: "Access-Switch" },
        patch_panel:          { farbe: "#475569", dunkel: "#1e293b", label: "Patchfeld"      },
        glasfaser_verteiler:  { farbe: "#d97706", dunkel: "#92400e", label: "LWL-Verteiler" },
        firewall:             { farbe: "#dc2626", dunkel: "#991b1b", label: "Firewall"       },
        router:               { farbe: "#ea580c", dunkel: "#9a3412", label: "Router"         },
        server:               { farbe: "#16a34a", dunkel: "#14532d", label: "Server"         },
        nas:                  { farbe: "#15803d", dunkel: "#14532d", label: "NAS/Storage"    },
        ups:                  { farbe: "#0369a1", dunkel: "#1e3a5f", label: "USV"            },
        kvm:                  { farbe: "#4b5563", dunkel: "#111827", label: "KVM"            },
        accesspoint:          { farbe: "#0891b2", dunkel: "#164e63", label: "Access Point"   },
        sonstiges:            { farbe: "#374151", dunkel: "#111827", label: "Sonstiges"      },
    };

    /* ------------------------------------------------------------------
       Layout
    ------------------------------------------------------------------ */
    var MAX_HE   = 42;
    var HE_H     = 28;          // Pixel pro HE
    var RACK_L   = 52;          // Linke Rails-Breite
    var RACK_R   = 12;          // Rechte Rails-Breite
    var SLOT_W   = 340;         // Nutzbreite Einschub
    var SVG_W    = RACK_L + SLOT_W + RACK_R + 20;
    var PAD_T    = 24;          // Padding oben (Rack-Dach)
    var PAD_B    = 24;          // Padding unten (Rack-Boden)

    /* ------------------------------------------------------------------
       SVG-Helfer
    ------------------------------------------------------------------ */
    var NS = "http://www.w3.org/2000/svg";

    function e(tag, attrs) {
        var el = document.createElementNS(NS, tag);
        for (var k in attrs) el.setAttribute(k, attrs[k]);
        return el;
    }
    function rect(x, y, w, h, fill, extra) {
        var a = { x: x, y: y, width: w, height: h, fill: fill };
        for (var k in (extra || {})) a[k] = extra[k];
        return e("rect", a);
    }
    function text(x, y, str, attrs) {
        var el = e("text", Object.assign({ x: x, y: y, "font-family": "monospace, Arial" }, attrs));
        el.textContent = str;
        return el;
    }
    function line(x1, y1, x2, y2, attrs) {
        return e("line", Object.assign({ x1: x1, y1: y1, x2: x2, y2: y2 }, attrs));
    }
    function circle(cx, cy, r, attrs) {
        return e("circle", Object.assign({ cx: cx, cy: cy, r: r }, attrs));
    }

    /* ------------------------------------------------------------------
       Rack-Rahmen zeichnen
    ------------------------------------------------------------------ */
    function zeichneRahmen(svg, totalH) {
        // Gehaeuse-Hintergrund
        svg.appendChild(rect(0, 0, SVG_W, totalH, "#0a0a0f",
            { rx: 6, stroke: "#1e293b", "stroke-width": 2 }));

        // Dach
        svg.appendChild(rect(0, 0, SVG_W, PAD_T, "#1e293b", { rx: 4 }));
        svg.appendChild(text(SVG_W / 2, 15, "19\" Rack – 42 HE",
            { "text-anchor": "middle", "font-size": "10", fill: "#64748b", "font-weight": "bold" }));

        // Boden
        svg.appendChild(rect(0, totalH - PAD_B, SVG_W, PAD_B, "#1e293b", { rx: 4 }));

        // Linke Rails
        svg.appendChild(rect(0, PAD_T, RACK_L - 4, MAX_HE * HE_H, "#111827"));
        // Rechte Rails
        svg.appendChild(rect(RACK_L + SLOT_W + 4, PAD_T, RACK_R + 4, MAX_HE * HE_H, "#111827"));

        // HE-Nummern + Gitternetz
        for (var he = MAX_HE; he >= 1; he--) {
            var yTop = PAD_T + (MAX_HE - he) * HE_H;
            var yMid = yTop + HE_H / 2;

            // Gitternetz
            svg.appendChild(line(RACK_L, yTop, RACK_L + SLOT_W, yTop,
                { stroke: "#0f172a", "stroke-width": 1 }));

            // Rail-Markierungen links (kleine Querrillen)
            if (he % 1 === 0) {
                svg.appendChild(rect(4, yTop + 2, RACK_L - 12, HE_H - 4, "#1a2336",
                    { rx: 1 }));
                // HE-Nummer
                svg.appendChild(text(RACK_L - 6, yMid, String(he),
                    { "text-anchor": "end", "dominant-baseline": "middle",
                      "font-size": "8", fill: "#334155" }));
                // Kleine Schrauben-Symbole
                ["top", "bot"].forEach(function (pos) {
                    var sy = pos === "top" ? yTop + 4 : yTop + HE_H - 4;
                    svg.appendChild(circle(10, sy, 2.5,
                        { fill: "#0f172a", stroke: "#334155", "stroke-width": 0.8 }));
                    svg.appendChild(line(8, sy, 12, sy,
                        { stroke: "#475569", "stroke-width": 0.5 }));
                });
            }
        }

        // Kabelkanal rechts (hinterer Bereich)
        svg.appendChild(rect(RACK_L + SLOT_W + 4, PAD_T, 12, MAX_HE * HE_H,
            "#111827", { opacity: "0.8" }));
        for (var ci = 0; ci < MAX_HE; ci++) {
            var cy2 = PAD_T + ci * HE_H + HE_H / 2;
            svg.appendChild(circle(RACK_L + SLOT_W + 10, cy2, 2,
                { fill: "#0f172a", stroke: "#1e293b", "stroke-width": 0.5 }));
        }
    }

    /* ------------------------------------------------------------------
       Leerslot
    ------------------------------------------------------------------ */
    function zeichneLeerslot(svg, he) {
        var yTop = PAD_T + (MAX_HE - he) * HE_H;
        var g = e("g", {});
        g.appendChild(rect(RACK_L, yTop + 1, SLOT_W, HE_H - 2, "#0d1117",
            { rx: 1 }));
        // Schrauben
        [[RACK_L + 4, yTop + HE_H / 2], [RACK_L + SLOT_W - 4, yTop + HE_H / 2]].forEach(function (p) {
            g.appendChild(circle(p[0], p[1], 2.5,
                { fill: "#111827", stroke: "#1e293b", "stroke-width": 0.8 }));
            g.appendChild(line(p[0] - 2, p[1], p[0] + 2, p[1],
                { stroke: "#374151", "stroke-width": 0.6 }));
        });
        svg.appendChild(g);
    }

    /* ------------------------------------------------------------------
       Komponenten-Renderer je Typ
    ------------------------------------------------------------------ */

    // Gemeinsames Geraete-Grundgeruest
    function baseGeraet(svg, he, anzHe, typ) {
        var cfg = TYPEN[typ] || TYPEN.sonstiges;
        var yTop = PAD_T + (MAX_HE - he - anzHe + 1) * HE_H;
        var h = anzHe * HE_H - 2;
        var g = e("g", { style: "cursor:pointer" });

        // Hauptkoerper
        g.appendChild(rect(RACK_L, yTop + 1, SLOT_W, h, cfg.dunkel,
            { rx: 2, stroke: cfg.farbe, "stroke-width": 1 }));
        // Linker Farbbalken (Typ-Indikator)
        g.appendChild(rect(RACK_L, yTop + 1, 5, h, cfg.farbe, { rx: 1 }));
        // Frontblende-Struktur (leichter Glanz oben)
        g.appendChild(rect(RACK_L + 5, yTop + 1, SLOT_W - 5, 3,
            "#ffffff", { opacity: "0.04" }));
        // Befestigungsschrauben
        [[RACK_L + 12, yTop + HE_H / 2], [RACK_L + SLOT_W - 6, yTop + HE_H / 2]].forEach(function (p) {
            g.appendChild(circle(p[0], p[1], 3,
                { fill: cfg.dunkel, stroke: cfg.farbe, "stroke-width": 0.8 }));
            g.appendChild(line(p[0] - 2, p[1], p[0] + 2, p[1],
                { stroke: cfg.farbe, "stroke-width": 0.5 }));
        });

        return { g: g, yTop: yTop, h: h, cfg: cfg };
    }

    function zeichneSwitch(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var g = b.g; var yTop = b.yTop; var h = b.h; var cfg = b.cfg;

        var portAnz = k.ports_ges || 48;
        var belegte = k.ports_bel || 0;
        var portsProReihe = portAnz / 2;
        var portW = Math.min(8, (SLOT_W - 90) / (portsProReihe + 1));
        var portH = Math.min(6, (h - 10) / 3);
        var portAbst = (SLOT_W - 90) / portsProReihe;
        var startX = RACK_L + 30;

        // Port-Raster (2 Reihen)
        for (var p = 0; p < portsProReihe; p++) {
            for (var r = 0; r < 2; r++) {
                var portIdx = p * 2 + r;
                var isBelegt = portIdx < belegte;
                var px = startX + p * portAbst;
                var py = yTop + h / 2 - portH - 2 + r * (portH + 3);
                var pFill = isBelegt ? "#22c55e" : "#0f172a";
                var pStroke = isBelegt ? "#16a34a" : "#1e293b";
                b.g.appendChild(rect(px, py, portW, portH, pFill,
                    { stroke: pStroke, "stroke-width": 0.5, rx: 0.5 }));
                // LED-Punkt oben auf belegten Ports
                if (isBelegt) {
                    b.g.appendChild(circle(px + portW / 2, py - 2, 1,
                        { fill: "#86efac" }));
                }
            }
        }
        // SFP/Uplink-Ports (rechts, goldene Farbe = Glasfaser)
        [0, 1, 2, 3].forEach(function (si) {
            var spx = RACK_L + SLOT_W - 42 + si * 9;
            var spy = yTop + h / 2 - 5;
            b.g.appendChild(rect(spx, spy, 7, 10,
                si < 2 ? "#78350f" : "#0f172a",
                { stroke: "#f59e0b", "stroke-width": 0.8, rx: 0.5 }));
            if (si < 2) {
                b.g.appendChild(circle(spx + 3.5, spy - 2, 1, { fill: "#fcd34d" }));
            }
        });

        // Konsolen-Port (ganz links, klein)
        b.g.appendChild(rect(RACK_L + 22, yTop + h / 2 - 3, 5, 6,
            "#312e81", { stroke: "#6366f1", "stroke-width": 0.5, rx: 1 }));

        // Power-LED
        b.g.appendChild(circle(RACK_L + SLOT_W - 10, yTop + h / 2, 3,
            { fill: "#22c55e", opacity: "0.9" }));

        zeichneLabel(b.g, k, yTop, h, cfg);
        tooltipUndKlick(svg, b.g, k);
    }

    function zeichnePatchpanel(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var portAnz = k.ports_ges || 24;
        var belegte = k.ports_bel || 0;
        var portW = (SLOT_W - 40) / portAnz - 2;
        var portH = b.h - 8;
        var startX = RACK_L + 20;

        for (var p = 0; p < portAnz; p++) {
            var isBelegt = p < belegte;
            var px = startX + p * ((SLOT_W - 40) / portAnz);
            var py = b.yTop + 4;
            // Port-Buchse (rechteckig)
            b.g.appendChild(rect(px, py, portW, portH, "#0f172a",
                { stroke: isBelegt ? "#22c55e" : "#1e293b", "stroke-width": 0.8, rx: 0.5 }));
            // Innerer Stift-Punkt
            b.g.appendChild(circle(px + portW / 2, py + portH / 2, 1.2,
                { fill: isBelegt ? "#22c55e" : "#374151" }));
            // Nummerierung (jede 6. Port)
            if (p % 6 === 0) {
                b.g.appendChild(text(px + portW / 2, b.yTop + b.h - 2,
                    String(p + 1),
                    { "text-anchor": "middle", "font-size": "5", fill: "#475569" }));
            }
        }
        zeichneLabel(b.g, k, b.yTop, b.h, b.cfg);
        tooltipUndKlick(svg, b.g, k);
    }

    function zeichneServer(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var g = b.g; var yTop = b.yTop; var h = b.h;

        // Laufwerks-Schacht-Reihe
        var hddAnz = 8;
        var hddW = 18; var hddH = h * 0.55;
        var hddY = yTop + h / 2 - hddH / 2;
        for (var i = 0; i < hddAnz; i++) {
            var hx = RACK_L + 24 + i * (hddW + 2);
            var hfill = i < 6 ? "#064e3b" : "#0f172a";
            var hstroke = i < 6 ? "#22c55e" : "#1e293b";
            g.appendChild(rect(hx, hddY, hddW, hddH, hfill,
                { stroke: hstroke, "stroke-width": 0.8, rx: 1 }));
            // Aktivitaets-LED auf Laufwerk
            if (i < 6) {
                var ledFarbe = i % 3 === 0 ? "#86efac" : "#4ade80";
                g.appendChild(circle(hx + hddW / 2, hddY + 4, 1.5,
                    { fill: ledFarbe, opacity: "0.9" }));
            }
            // Auswurf-Knopf unten
            g.appendChild(rect(hx + 2, hddY + hddH - 5, hddW - 4, 3,
                "#1a2336", { rx: 1 }));
        }

        // Prozessor/Blink-LEDs rechts
        var ledY = yTop + h / 2;
        [
            { farbe: "#22c55e", label: "PWR" },
            { farbe: "#3b82f6", label: "NIC" },
            { farbe: "#fbbf24", label: "HDD" },
        ].forEach(function (led, li) {
            var lx = RACK_L + SLOT_W - 60 + li * 16;
            g.appendChild(circle(lx, ledY - 4, 3, { fill: led.farbe, opacity: "0.9" }));
            g.appendChild(text(lx, ledY + 6, led.label,
                { "text-anchor": "middle", "font-size": "5", fill: "#475569" }));
        });

        // USB + VGA Port
        g.appendChild(rect(RACK_L + SLOT_W - 20, yTop + h / 2 - 5, 7, 5,
            "#1e3a5f", { stroke: "#3b82f6", "stroke-width": 0.5, rx: 0.5 }));

        // Power-Taste
        g.appendChild(circle(RACK_L + SLOT_W - 8, yTop + h / 2, 4,
            { fill: "#1a2336", stroke: "#22c55e", "stroke-width": 1 }));
        g.appendChild(circle(RACK_L + SLOT_W - 8, yTop + h / 2, 1.5,
            { fill: "#22c55e" }));

        zeichneLabel(b.g, k, yTop, h, b.cfg);
        tooltipUndKlick(svg, g, k);
    }

    function zeichneNas(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var g = b.g; var yTop = b.yTop; var h = b.h;

        // Mehr Laufwerke (NAS hat mehr Slots)
        var hddAnz = 12;
        var hddW = 14; var hddH = h * 0.65;
        var hddY = yTop + h / 2 - hddH / 2;
        for (var i = 0; i < hddAnz; i++) {
            var hx = RACK_L + 20 + i * (hddW + 2);
            var belegt = i < 10;
            g.appendChild(rect(hx, hddY, hddW, hddH,
                belegt ? "#064e3b" : "#0f172a",
                { stroke: belegt ? "#16a34a" : "#1e293b", "stroke-width": 0.7, rx: 1 }));
            if (belegt) {
                g.appendChild(circle(hx + hddW / 2, hddY + 3, 1.2,
                    { fill: "#4ade80" }));
            }
        }
        // RAID-Status-Anzeige
        g.appendChild(rect(RACK_L + SLOT_W - 70, yTop + h / 2 - 8, 50, 16,
            "#064e3b", { stroke: "#22c55e", "stroke-width": 0.5, rx: 2 }));
        g.appendChild(text(RACK_L + SLOT_W - 45, yTop + h / 2 + 1, "RAID 10",
            { "text-anchor": "middle", "font-size": "7", fill: "#86efac", "font-weight": "bold" }));

        zeichneLabel(b.g, k, yTop, h, b.cfg);
        tooltipUndKlick(svg, g, k);
    }

    function zeichneUps(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var g = b.g; var yTop = b.yTop; var h = b.h;

        // Batterie-Indikatoren (Akkuzellenoptik)
        var batAnz = 6;
        var batW = (SLOT_W - 80) / batAnz - 4;
        var batH = h * 0.6;
        var batY = yTop + h / 2 - batH / 2;
        for (var i = 0; i < batAnz; i++) {
            var bx = RACK_L + 30 + i * (batW + 4);
            g.appendChild(rect(bx, batY, batW, batH, "#0c1f3f",
                { stroke: "#0369a1", "stroke-width": 1, rx: 2 }));
            // Fuellstand (100%)
            g.appendChild(rect(bx + 2, batY + 3, batW - 4, batH - 6,
                "#0284c7", { rx: 1 }));
            // + Pol oben
            g.appendChild(rect(bx + batW / 2 - 2, batY - 3, 4, 3,
                "#0369a1", { rx: 0.5 }));
        }

        // Status-Panel rechts
        var spx = RACK_L + SLOT_W - 80;
        g.appendChild(rect(spx, yTop + 4, 68, h - 8, "#0c1a2e",
            { stroke: "#0369a1", "stroke-width": 0.5, rx: 2 }));
        [
            { lbl: "NETZ", ok: true  },
            { lbl: "AKKU", ok: true  },
            { lbl: "LAST", ok: false },
        ].forEach(function (row, ri) {
            var ry = yTop + 10 + ri * 9;
            g.appendChild(circle(spx + 8, ry, 2.5,
                { fill: row.ok ? "#22c55e" : "#fbbf24" }));
            g.appendChild(text(spx + 14, ry + 1, row.lbl,
                { "dominant-baseline": "middle", "font-size": "6", fill: "#94a3b8" }));
        });

        zeichneLabel(b.g, k, yTop, h, b.cfg);
        tooltipUndKlick(svg, g, k);
    }

    function zeichneFirewall(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var g = b.g; var yTop = b.yTop; var h = b.h;

        // WAN/LAN-Port-Gruppen
        var gruppen = [
            { label: "WAN",  ports: 2, farbe: "#dc2626" },
            { label: "DMZ",  ports: 4, farbe: "#f97316" },
            { label: "LAN",  ports: 8, farbe: "#22c55e" },
        ];
        var gx = RACK_L + 28;
        gruppen.forEach(function (gr) {
            // Gruppen-Label
            g.appendChild(text(gx + gr.ports * 8, b.yTop + h + (h > 20 ? -4 : -2), gr.label,
                { "text-anchor": "middle", "font-size": "5", fill: "#64748b" }));
            for (var p = 0; p < gr.ports; p++) {
                var px = gx + p * 8;
                var py = b.yTop + h / 2 - 4;
                g.appendChild(rect(px, py, 6, 8, "#0f172a",
                    { stroke: gr.farbe, "stroke-width": 0.8, rx: 0.5 }));
                g.appendChild(circle(px + 3, py - 2, 1,
                    { fill: gr.farbe, opacity: "0.7" }));
            }
            gx += gr.ports * 8 + 10;
        });

        // Konsole + Power
        g.appendChild(rect(RACK_L + SLOT_W - 24, yTop + h / 2 - 4, 6, 8,
            "#1a0505", { stroke: "#dc2626", "stroke-width": 0.5, rx: 0.5 }));
        g.appendChild(circle(RACK_L + SLOT_W - 10, yTop + h / 2, 4,
            { fill: "#1a0505", stroke: "#ef4444", "stroke-width": 1 }));
        g.appendChild(circle(RACK_L + SLOT_W - 10, yTop + h / 2, 1.5,
            { fill: "#ef4444" }));

        zeichneLabel(b.g, k, yTop, h, b.cfg);
        tooltipUndKlick(svg, g, k);
    }

    function zeichneRouter(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var g = b.g; var yTop = b.yTop; var h = b.h;

        // Ports (WAN + LAN)
        var ports = [
            { farbe: "#f97316", label: "WAN1" },
            { farbe: "#fb923c", label: "WAN2" },
            { farbe: "#22c55e", label: "LAN1" },
            { farbe: "#22c55e", label: "LAN2" },
            { farbe: "#22c55e", label: "LAN3" },
            { farbe: "#22c55e", label: "LAN4" },
        ];
        ports.forEach(function (port, pi) {
            var px = RACK_L + 28 + pi * 20;
            var py = yTop + h / 2 - 5;
            g.appendChild(rect(px, py, 14, 10, "#0f172a",
                { stroke: port.farbe, "stroke-width": 0.8, rx: 1 }));
            g.appendChild(circle(px + 7, py - 2, 1.5,
                { fill: port.farbe, opacity: "0.8" }));
            g.appendChild(text(px + 7, py + 16, port.label,
                { "text-anchor": "middle", "font-size": "5", fill: "#64748b" }));
        });

        zeichneLabel(b.g, k, yTop, h, b.cfg);
        tooltipUndKlick(svg, g, k);
    }

    function zeichneLwl(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var g = b.g; var yTop = b.yTop; var h = b.h;

        // LC-Duplex-Buchsen
        var portAnz = k.ports_ges || 24;
        var belegte = k.ports_bel || 0;
        var portW = Math.min(10, (SLOT_W - 40) / portAnz - 1);
        var startX = RACK_L + 20;
        for (var p = 0; p < portAnz; p++) {
            var isBelegt = p < belegte;
            var px = startX + p * ((SLOT_W - 40) / portAnz);
            var py = yTop + h / 2 - 5;
            // LC-Duplex-Buchse (zwei kleine Kreise nebeneinander)
            [0, portW * 0.5].forEach(function (dx) {
                g.appendChild(circle(px + portW * 0.25 + dx, py + 4, portW * 0.2,
                    { fill: isBelegt ? "#fbbf24" : "#0f172a",
                      stroke: isBelegt ? "#f59e0b" : "#1e293b", "stroke-width": 0.5 }));
            });
            // Faserschutz-Kappe
            g.appendChild(rect(px, py, portW, 8, "none",
                { stroke: isBelegt ? "#d97706" : "#1e293b", "stroke-width": 0.7, rx: 1 }));
            // Glasfaser-Kabel (kleiner gelber Strich nach hinten)
            if (isBelegt) {
                g.appendChild(e("line", {
                    x1: px + portW / 2, y1: py + 8,
                    x2: px + portW / 2, y2: py + h / 2 + 2,
                    stroke: "#fbbf24", "stroke-width": 0.8, opacity: "0.5"
                }));
            }
        }

        zeichneLabel(b.g, k, yTop, h, b.cfg);
        tooltipUndKlick(svg, g, k);
    }

    function zeichneKvm(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        var g = b.g;

        // Port-Raster (8 Ports)
        var portAnz = k.ports_ges || 8;
        for (var p = 0; p < portAnz; p++) {
            var isBelegt = p < (k.ports_bel || 2);
            var px = RACK_L + 28 + p * 20;
            var py = b.yTop + b.h / 2 - 4;
            g.appendChild(rect(px, py, 16, 8, "#111827",
                { stroke: isBelegt ? "#4b5563" : "#1e293b", "stroke-width": 0.8, rx: 0.5 }));
        }
        zeichneLabel(b.g, k, b.yTop, b.h, b.cfg);
        tooltipUndKlick(svg, g, k);
    }

    function zeichneSonstiges(svg, k, he) {
        var b = baseGeraet(svg, he, k.he_anzahl, k.typ);
        zeichneLabel(b.g, k, b.yTop, b.h, b.cfg);
        tooltipUndKlick(svg, b.g, k);
    }

    /* ------------------------------------------------------------------
       Gemeinsames Label (Bezeichnung + IP)
    ------------------------------------------------------------------ */
    function zeichneLabel(g, k, yTop, h, cfg) {
        var textY = h >= 24 ? yTop + h - 6 : yTop + h / 2 + 4;
        if (h >= 36) textY = yTop + h - 14;

        // Bezeichnung
        g.appendChild(text(RACK_L + 10, h >= 24 ? yTop + 10 : yTop + h / 2 + 1,
            k.bezeichnung,
            {
                "dominant-baseline": "middle",
                "font-size": "9",
                "font-weight": "bold",
                fill: "#f1f5f9",
            }));

        // Modell (nur wenn genug Platz)
        if (h >= 32 && k.modell) {
            var modell = k.modell.length > 38 ? k.modell.substring(0, 38) + "…" : k.modell;
            g.appendChild(text(RACK_L + 10, yTop + 20,
                modell,
                { "font-size": "7", fill: "#64748b" }));
        }

        // IP rechts oben
        if (k.ip) {
            g.appendChild(text(RACK_L + SLOT_W - 6, yTop + 10, k.ip,
                { "text-anchor": "end", "dominant-baseline": "middle",
                  "font-size": "8", fill: "#38bdf8", "font-weight": "bold" }));
        }

        // VLAN (klein, unten links)
        if (k.vlan && h >= 24) {
            g.appendChild(text(RACK_L + 10, yTop + h - 4, k.vlan,
                { "font-size": "6", fill: cfg.farbe, opacity: "0.7" }));
        }
    }

    /* ------------------------------------------------------------------
       Tooltip + Klick-Highlight
    ------------------------------------------------------------------ */
    function tooltipUndKlick(svg, g, k) {
        var title = document.createElementNS(NS, "title");
        title.textContent = [
            k.bezeichnung,
            k.typ_label,
            k.modell ? (k.hersteller + " " + k.modell) : "",
            k.ip     ? ("IP: " + k.ip)     : "",
            k.vlan   ? ("VLAN: " + k.vlan) : "",
            k.ports_ges ? (k.ports_bel + "/" + k.ports_ges + " Ports belegt") : "",
            k.bemerkung || "",
        ].filter(Boolean).join("\n");
        g.appendChild(title);
        svg.appendChild(g);
    }

    /* ------------------------------------------------------------------
       Legende
    ------------------------------------------------------------------ */
    function zeichneLegende(container) {
        var legend = document.createElement("div");
        legend.style.cssText = "display:flex;flex-wrap:wrap;gap:8px;padding:12px;background:#0a0a0f;border-top:1px solid #1e293b;font-family:monospace;font-size:11px";

        Object.keys(TYPEN).forEach(function (typ) {
            var cfg = TYPEN[typ];
            var item = document.createElement("span");
            item.style.cssText = "display:inline-flex;align-items:center;gap:4px;color:#94a3b8";
            item.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:' +
                cfg.farbe + '"></span>' + cfg.label;
            legend.appendChild(item);
        });

        // Leerslot
        var leer = document.createElement("span");
        leer.style.cssText = "display:inline-flex;align-items:center;gap:4px;color:#94a3b8";
        leer.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:2px;background:#0d1117;border:1px solid #1e293b"></span>Leerslot';
        legend.appendChild(leer);

        var card = document.getElementById("rack-svg");
        if (card && card.parentNode) {
            card.parentNode.insertAdjacentElement("afterend", legend);
        }
    }

    /* ------------------------------------------------------------------
       Hauptfunktion
    ------------------------------------------------------------------ */
    function zeichneRack() {
        var svg = document.getElementById("rack-svg");
        if (!svg) return;

        var maxHe  = typeof MAX_HE !== "undefined" ? MAX_HE : 42;
        var daten  = typeof RACK_DATEN !== "undefined" ? RACK_DATEN : [];

        var svgH   = PAD_T + maxHe * HE_H + PAD_B;
        svg.setAttribute("width",   SVG_W);
        svg.setAttribute("height",  svgH);
        svg.setAttribute("viewBox", "0 0 " + SVG_W + " " + svgH);
        while (svg.firstChild) svg.removeChild(svg.firstChild);

        // Rahmen + Rails
        zeichneRahmen(svg, svgH);

        // Belegte HE-Slots merken
        var belegteHe = {};
        daten.forEach(function (k) {
            if (!k.he_start) return;
            for (var u = k.he_start; u < k.he_start + k.he_anzahl; u++) {
                belegteHe[u] = true;
            }
        });

        // Leerslots zeichnen (zuerst, dann ueberlagern Komponenten)
        for (var he = 1; he <= maxHe; he++) {
            if (!belegteHe[he]) {
                zeichneLeerslot(svg, he);
            }
        }

        // Komponenten zeichnen
        daten.forEach(function (k) {
            if (!k.he_start) return;
            var typ = k.typ;
            if (typ === "core_switch" || typ === "distribution_switch" || typ === "access_switch") {
                zeichneSwitch(svg, k, k.he_start);
            } else if (typ === "patch_panel") {
                zeichnePatchpanel(svg, k, k.he_start);
            } else if (typ === "server") {
                zeichneServer(svg, k, k.he_start);
            } else if (typ === "nas") {
                zeichneNas(svg, k, k.he_start);
            } else if (typ === "ups") {
                zeichneUps(svg, k, k.he_start);
            } else if (typ === "firewall") {
                zeichneFirewall(svg, k, k.he_start);
            } else if (typ === "router") {
                zeichneRouter(svg, k, k.he_start);
            } else if (typ === "glasfaser_verteiler") {
                zeichneLwl(svg, k, k.he_start);
            } else if (typ === "kvm") {
                zeichneKvm(svg, k, k.he_start);
            } else {
                zeichneSonstiges(svg, k, k.he_start);
            }
        });

        // Legende einfuegen
        zeichneLegende(svg);
    }

    document.addEventListener("DOMContentLoaded", zeichneRack);
})();
