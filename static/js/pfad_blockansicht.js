// pfad_blockansicht.js – Schreibgeschuetzte Blockdiagramm-Ansicht

document.addEventListener("DOMContentLoaded", function () {

    var schritte     = JSON.parse(document.getElementById("schritte-daten").textContent);
    var transitionen = JSON.parse(document.getElementById("transitionen-daten").textContent);

    // ------------------------------------------------------------------
    // Pfadzugehörigkeit berechnen
    // Idee: Alle Transitionen mit nicht-leerer Bedingung markieren den
    // Ziel-Knoten als "verzweigt". Knoten die von mehreren Quellen
    // erreichbar sind gelten als "gemeinsam". Loop-Anker = LOOP-Label.
    // ------------------------------------------------------------------

    var knotenMap = {};
    schritte.forEach(function (s) { knotenMap[s.node_id] = s; });

    // Eingehende Kanten pro Knoten zaehlen
    var eingehend = {};
    var hatBedingung = {};
    var loopAnker = {};

    transitionen.forEach(function (t) {
        eingehend[t.zu] = (eingehend[t.zu] || 0) + 1;
        if (t.bedingung) hatBedingung[t.zu] = true;
        if (t.label === "LOOP") loopAnker[t.zu] = true;
    });

    // Farbe pro Knoten
    function knotenFarbe(s) {
        if (s.ist_start || s.ist_ende) {
            return { background: "#2e7d4f", border: "#1b5e20", font: "#fff" };
        }
        if (loopAnker[s.node_id]) {
            return { background: "#7b1fa2", border: "#4a148c", font: "#fff" };
        }
        if (hatBedingung[s.node_id]) {
            return { background: "#f57c00", border: "#e65100", font: "#fff" };
        }
        return { background: "#1976d2", border: "#0d47a1", font: "#fff" };
    }

    // Feldtyp-Labels fuer das Panel
    var TYP_LABEL = {
        text: "Text", mehrzeil: "Mehrzeilig", zahl: "Zahl", datum: "Datum",
        bool: "Checkbox", auswahl: "Dropdown", radio: "Auswahl", checkboxen: "Checkboxen",
        email: "E-Mail", iban: "IBAN", datei: "Datei-Upload", signatur: "Unterschrift",
        berechnung: "Berechnung", gruppe: "Wiederholungsgruppe", textblock: "Infotext",
        abschnitt: "Abschnitt", trennlinie: "Trennlinie", leerblock: "Leerzeile",
        link: "Link", zusammenfassung: "Zusammenfassung",
    };

    // ------------------------------------------------------------------
    // vis.js Nodes + Edges aufbauen
    // ------------------------------------------------------------------

    var nodes = new vis.DataSet();
    var edges = new vis.DataSet();

    schritte.forEach(function (s) {
        var farbe = knotenFarbe(s);
        var anzahl = s.felder.filter(function (f) {
            return ["textblock","abschnitt","trennlinie","leerblock","link","zusammenfassung"].indexOf(f.typ) === -1;
        }).length;
        var label = s.titel + (anzahl > 0 ? "\n(" + anzahl + " Felder)" : "");

        nodes.add({
            id: s.node_id,
            label: label,
            title: s.titel,
            color: { background: farbe.background, border: farbe.border, highlight: { background: farbe.background, border: "#ff6f00" } },
            font: { color: farbe.font, size: 13, face: "sans-serif", bold: s.ist_start || s.ist_ende },
            shape: s.ist_start ? "diamond" : s.ist_ende ? "ellipse" : "box",
            margin: 10,
            widthConstraint: { minimum: 120, maximum: 200 },
        });
    });

    transitionen.forEach(function (t, idx) {
        var istLoop = t.label === "LOOP";
        var kantenlabel = "";
        if (t.bedingung) {
            // Bedingung kompakt: {{feld}} == "Wert" → nur "Wert" anzeigen
            var m = t.bedingung.match(/"([^"]{1,30})"/);
            kantenlabel = m ? m[1] : "";
        }
        if (t.label && t.label !== "LOOP") kantenlabel = t.label;

        edges.add({
            id: idx,
            from: t.von,
            to: t.zu,
            label: kantenlabel,
            font: { size: 10, color: "#555", align: "middle" },
            arrows: { to: { enabled: true, scaleFactor: 0.7 } },
            color: { color: istLoop ? "#7b1fa2" : "#607d8b", highlight: "#ff6f00" },
            dashes: istLoop,
            smooth: { type: "cubicBezier", forceDirection: "none", roundness: 0.4 },
        });
    });

    // ------------------------------------------------------------------
    // Netzwerk rendern
    // ------------------------------------------------------------------

    function baueOptionen(modus) {
        if (modus === "frei") {
            return {
                layout: { hierarchical: { enabled: false } },
                interaction: { hover: true, dragNodes: true, zoomView: true, dragView: true },
                physics: {
                    enabled: true,
                    repulsion: { nodeDistance: 180, springLength: 200, springConstant: 0.05 },
                    solver: "repulsion",
                },
                edges: { smooth: { type: "dynamic" } },
            };
        }
        return {
            layout: {
                hierarchical: {
                    enabled: true,
                    direction: modus === "UD" ? "UD" : "LR",
                    sortMethod: "directed",
                    levelSeparation: modus === "UD" ? 160 : 220,
                    nodeSpacing: 80,
                },
            },
            interaction: { hover: true, dragNodes: false, zoomView: true, dragView: true },
            physics: { enabled: false },
            edges: { smooth: { type: "cubicBezier" } },
        };
    }

    var container = document.getElementById("blockdiagramm");
    var network = new vis.Network(container, { nodes: nodes, edges: edges }, baueOptionen("LR"));

    // ------------------------------------------------------------------
    // Detail-Panel bei Klick
    // ------------------------------------------------------------------

    var panel        = document.getElementById("detail-panel");
    var panelTitel   = document.getElementById("panel-titel");
    var panelBadges  = document.getElementById("panel-badge-row");
    var panelFelder  = document.getElementById("panel-felder");
    var btnSchliessen = document.getElementById("panel-schliessen");

    network.on("click", function (params) {
        if (!params.nodes.length) return;
        var nodeId = params.nodes[0];
        var schritt = knotenMap[nodeId];
        if (!schritt) return;

        // Titel
        panelTitel.textContent = schritt.titel;

        // Badges
        var badges = "";
        if (schritt.ist_start) badges += '<span class="badge me-1" style="background:#2e7d4f;">Start</span>';
        if (schritt.ist_ende)  badges += '<span class="badge me-1" style="background:#2e7d4f;">Ende</span>';
        if (loopAnker[schritt.node_id]) badges += '<span class="badge me-1" style="background:#7b1fa2;">Loop-Anker</span>';
        panelBadges.innerHTML = badges;

        // Felder
        var eingabeFelder = schritt.felder.filter(function (f) {
            return ["textblock","abschnitt","trennlinie","leerblock","link","zusammenfassung"].indexOf(f.typ) === -1;
        });
        var infoFelder = schritt.felder.filter(function (f) {
            return ["textblock","link"].indexOf(f.typ) >= 0;
        });

        var html = "";

        if (infoFelder.length) {
            html += '<p class="text-muted small mb-2"><em>Enthält Informationstext / Link</em></p>';
        }

        if (eingabeFelder.length) {
            html += '<table class="table table-sm table-borderless mb-0" style="font-size:0.8rem;">';
            html += '<thead><tr><th class="text-muted fw-normal">Feld</th><th class="text-muted fw-normal">Typ</th><th></th></tr></thead><tbody>';
            eingabeFelder.forEach(function (f) {
                var pflichtBadge = f.pflicht
                    ? '<span class="text-danger fw-bold" title="Pflichtfeld">*</span>'
                    : '<span class="text-muted" title="Optional">○</span>';
                html += "<tr>" +
                    "<td>" + (f.label || f.id) + "</td>" +
                    "<td class=\"text-muted\">" + (TYP_LABEL[f.typ] || f.typ) + "</td>" +
                    "<td class=\"text-center\">" + pflichtBadge + "</td>" +
                    "</tr>";
            });
            html += "</tbody></table>";
        } else {
            html += '<p class="text-muted small">Keine Eingabefelder.</p>';
        }

        panelFelder.innerHTML = html;
        panel.style.display = "block";
    });

    // Panel schliessen
    btnSchliessen.addEventListener("click", function () {
        panel.style.display = "none";
        network.unselectAll();
    });

    network.on("deselectNode", function () {
        panel.style.display = "none";
    });

    // Netzwerk nach dem ersten Zeichnen auf Inhalt zoomen
    // (stabilized feuert nicht wenn physics deaktiviert ist)
    network.once("afterDrawing", function () {
        network.fit({ animation: { duration: 400, easingFunction: "easeInOutQuad" } });
    });

    // ------------------------------------------------------------------
    // Layout-Toggle-Buttons
    // ------------------------------------------------------------------

    function setzeLayout(modus) {
        network.setOptions(baueOptionen(modus));
        if (modus !== "frei") {
            // Nach Layoutwechsel Zoom anpassen
            network.once("afterDrawing", function () {
                network.fit({ animation: { duration: 300, easingFunction: "easeInOutQuad" } });
            });
        }
        // Aktiven Button hervorheben
        ["layout-lr", "layout-ud", "layout-frei"].forEach(function (id) {
            document.getElementById(id).classList.remove("active");
        });
        var aktiv = modus === "UD" ? "layout-ud" : modus === "frei" ? "layout-frei" : "layout-lr";
        document.getElementById(aktiv).classList.add("active");
    }

    document.getElementById("layout-lr").addEventListener("click", function () { setzeLayout("LR"); });
    document.getElementById("layout-ud").addEventListener("click", function () { setzeLayout("UD"); });
    document.getElementById("layout-frei").addEventListener("click", function () { setzeLayout("frei"); });
});
