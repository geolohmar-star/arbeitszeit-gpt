/**
 * antraege_editor.js – Visueller Editor fuer verzweigte Antrags-Pfade. v2
 *
 * Basiert auf vis.js Network (lokal in vis-network.min.js).
 * CSP-konform: kein eval, kein inline-JS, Event-Delegation via data-action.
 *
 * Konzept:
 *  Knoten  = AntragsPfadSchritt (eine Formularseite)
 *  Kanten  = AntragsPfadTransition (Bedingung zwischen Schritten)
 */
(function () {
    "use strict";

    // -----------------------------------------------------------------------
    // Zustand
    // -----------------------------------------------------------------------

    var pfadPk = null;          // DB-PK des Pfads (null = neu)
    var modus = "normal";       // "normal" | "schritt" | "verbinden" | "loeschen"
    var network = null;
    var nodes = null;           // vis.DataSet
    var edges = null;           // vis.DataSet

    var schritte = {};          // node_id → { node_id, titel, felder_json, ist_start, ist_ende }
    var transitionen = [];      // [{ id, von, zu, bedingung, label, reihenfolge }]

    var verbindeVon = null;     // node_id des Quell-Knotens beim Verbinden-Modus

    // Aktuelle Bearbeitungs-IDs
    var editNodeId = null;      // node_id des gerade bearbeiteten Schritts
    var editEdgeId = null;      // interne Kanten-ID (vis edge id)
    var editFeldIndex = null;   // Index in schritt.felder_json beim Feld-Bearbeiten

    var schritteFelder = [];    // temporaere Feld-Liste waehrend Schritt-Bearbeitung
    var gruppeUnterfelder = []; // temporaere Unterfeld-Liste fuer Gruppe-Feld im Feld-Modal

    // Bootstrap Modals
    var schrittModal = null;
    var feldModal = null;
    var transitionModal = null;

    // -----------------------------------------------------------------------
    // Initialisierung
    // -----------------------------------------------------------------------

    document.addEventListener("DOMContentLoaded", function () {
        // PK aus json_script lesen
        var pkEl = document.getElementById("pfad-pk");
        if (pkEl) {
            pfadPk = JSON.parse(pkEl.textContent);
        }

        // vis.js Datasets
        nodes = new vis.DataSet([]);
        edges = new vis.DataSet([]);

        var container = document.getElementById("antraege-canvas");
        network = new vis.Network(container, { nodes: nodes, edges: edges }, visOptionen());

        // Modals
        schrittModal = new bootstrap.Modal(document.getElementById("schritt-modal"));
        feldModal = new bootstrap.Modal(document.getElementById("feld-modal"));
        transitionModal = new bootstrap.Modal(document.getElementById("transition-modal"));

        // Backdrop-Cleanup
        ["schritt-modal", "feld-modal", "transition-modal", "schema-import-modal"].forEach(function (id) {
            document.getElementById(id).addEventListener("hidden.bs.modal", function () {
                document.querySelectorAll(".modal-backdrop").forEach(function (el) { el.remove(); });
                document.body.classList.remove("modal-open");
                document.body.style.removeProperty("overflow");
                document.body.style.removeProperty("padding-right");
            });
        });

        // Bestehenden Pfad laden
        if (pfadPk) {
            ladePfad(pfadPk);
        }

        verdrahteEvents();
    });

    function visOptionen() {
        return {
            autoResize: false,
            physics: { enabled: false },
            interaction: { dragNodes: true, hover: true, selectConnectedEdges: false },
            nodes: {
                shape: "box",
                font: { size: 14, face: "system-ui, sans-serif" },
                borderWidth: 2,
                shadow: { enabled: true, size: 4, x: 2, y: 2 },
                margin: { top: 10, bottom: 10, left: 14, right: 14 },
            },
            edges: {
                arrows: { to: { enabled: true, scaleFactor: 0.8 } },
                font: { size: 11, align: "middle", background: "white" },
                smooth: { type: "curvedCW", roundness: 0.2 },
                color: { color: "#666", highlight: "#1a4d2e" },
                width: 2,
                selectionWidth: 3,
            },
        };
    }

    // -----------------------------------------------------------------------
    // Events verdrahten
    // -----------------------------------------------------------------------

    function verdrahteEvents() {
        // Modus-Buttons
        document.querySelectorAll("[data-modus]").forEach(function (btn) {
            btn.addEventListener("click", function () {
                setzeModus(btn.dataset.modus);
            });
        });

        // Speichern
        document.getElementById("btn-speichern").addEventListener("click", speichern);

        // Schema-Import
        var importModalEl = document.getElementById("schema-import-modal");
        if (importModalEl) {
            var importModal = new bootstrap.Modal(importModalEl);
            var importierteFelderJson = null;
            var importierterName = "";

            document.getElementById("btn-schema-import").addEventListener("click", function () {
                // Auswahl zuruecksetzen
                document.querySelectorAll(".import-schema-btn").forEach(function (b) {
                    b.classList.remove("btn-secondary", "active");
                    b.classList.add("btn-outline-secondary");
                });
                document.getElementById("import-vorschau").classList.add("d-none");
                document.getElementById("btn-import-bestaetigen").disabled = true;
                importierteFelderJson = null;
                importModal.show();
            });

            // Klick auf Formular-Karte
            document.getElementById("import-schema-liste").addEventListener("click", function (e) {
                var btn = e.target.closest(".import-schema-btn");
                if (!btn) return;

                // Aktive Karte markieren
                document.querySelectorAll(".import-schema-btn").forEach(function (b) {
                    b.classList.remove("btn-secondary", "active");
                    b.classList.add("btn-outline-secondary");
                });
                btn.classList.remove("btn-outline-secondary");
                btn.classList.add("btn-secondary", "active");

                var felderRaw = btn.dataset.felder;
                var name = btn.dataset.name || "";
                var felder;
                try {
                    felder = JSON.parse(felderRaw);
                } catch (e) {
                    felder = [];
                }
                importierteFelderJson = felder;
                importierterName = name;

                var TYP_LABEL_IMPORT = {
                    text: "Text", mehrzeil: "Mehrzeilig", zahl: "Zahl", datum: "Datum",
                    bool: "Ja/Nein", auswahl: "Auswahl", radio: "Radio", checkboxen: "Checkboxen",
                    email: "E-Mail", iban: "IBAN", uhrzeit: "Uhrzeit",
                    datei: "Datei-Upload", signatur: "Signatur", berechnung: "Berechnung",
                    textblock: "Fliesstext", abschnitt: "Abschnitt",
                    trennlinie: "Trennlinie", leerblock: "Leerblock", zusammenfassung: "Zusammenfassung",
                };
                var html = "";
                (felder || []).forEach(function (f) {
                    var typLabel = TYP_LABEL_IMPORT[f.typ] || f.typ;
                    var label = f.label || f.text || "(kein Label)";
                    html += '<div class="d-flex align-items-center gap-2 py-1 border-bottom">'
                        + '<span class="badge bg-secondary" style="min-width:90px;">' + typLabel + '</span>'
                        + '<span class="small">' + label + '</span>'
                        + (f.pflicht ? '<span class="text-danger ms-auto small">Pflicht</span>' : '')
                        + '</div>';
                });
                if (!html) html = '<p class="text-muted small mb-0">Keine Felder gefunden.</p>';
                document.getElementById("import-felder-liste").innerHTML = html;
                document.getElementById("import-vorschau").classList.remove("d-none");
                document.getElementById("btn-import-bestaetigen").disabled = false;
            });

            document.getElementById("btn-import-bestaetigen").addEventListener("click", function () {
                if (!importierteFelderJson || importierteFelderJson.length === 0) {
                    alert("Bitte zuerst ein Formular auswaehlen.");
                    return;
                }
                // Jedes Feld wird ein eigener Schritt – vertikal gestapelt, automatisch verbunden
                var startX = 400;
                var startY = 100;
                var abstandY = 120;
                var vorherigenId = null;
                var ts = Date.now();

                importierteFelderJson.forEach(function (feld, idx) {
                    var nodeId = "s" + (ts + idx);
                    var titel = feld.label || feld.text || feld.typ || "Schritt " + (idx + 1);
                    var posY = startY + idx * abstandY;
                    var neuerSchritt = {
                        node_id: nodeId,
                        titel: titel,
                        felder_json: [JSON.parse(JSON.stringify(feld))],
                        ist_start: false,
                        ist_ende: false,
                        pos_x: startX,
                        pos_y: posY,
                    };
                    schritte[nodeId] = neuerSchritt;
                    nodes.add({
                        id: nodeId,
                        label: knotenLabel(neuerSchritt),
                        x: startX,
                        y: posY,
                        color: knotenFarbe(neuerSchritt),
                        font: { color: "#ffffff" },
                    });
                    // Kante zum vorherigen Schritt
                    if (vorherigenId) {
                        var edgeId = "e" + vorherigenId + "_" + nodeId;
                        transitionen.push({ id: edgeId, von: vorherigenId, zu: nodeId, bedingung: "", label: "", reihenfolge: idx });
                        edges.add({ id: edgeId, from: vorherigenId, to: nodeId, label: "" });
                    }
                    vorherigenId = nodeId;
                });

                document.getElementById("canvas-hinweis").style.display = "none";
                importModal.hide();
                network.fit();
                document.getElementById("speicher-status").textContent = "Schritt \"" + importierterName + "\" importiert \u2013 bitte speichern.";
            });
        }

        // vis.js Events
        network.on("click", function (params) {
            if (params.nodes.length > 0) {
                knotenGeklickt(params.nodes[0]);
            } else if (params.edges.length > 0) {
                kanteGeklickt(params.edges[0]);
            } else {
                canvasGeklickt(params.pointer.canvas);
            }
        });

        network.on("dragEnd", function (params) {
            if (params.nodes.length > 0) {
                var nodeId = params.nodes[0];
                var pos = network.getPositions([nodeId])[nodeId];
                if (schritte[nodeId]) {
                    schritte[nodeId].pos_x = Math.round(pos.x);
                    schritte[nodeId].pos_y = Math.round(pos.y);
                }
            }
        });

        // Schritt-Modal: Speichern
        document.getElementById("btn-schritt-speichern").addEventListener("click", schrittSpeichern);

        // Schritt-Modal: Feld hinzufuegen
        document.getElementById("btn-feld-hinzufuegen-schritt").addEventListener("click", function () {
            oeffneFeldModal(null);
        });

        // Schritt-Modal: Event-Delegation auf Feld-Liste
        document.getElementById("schritt-felder-liste").addEventListener("click", function (e) {
            var btn = e.target.closest("[data-feld-action]");
            if (!btn) return;
            var action = btn.dataset.feldAction;
            var idx = parseInt(btn.dataset.idx, 10);
            if (action === "bearbeiten") {
                oeffneFeldModal(idx);
            } else if (action === "loeschen") {
                schritteFelder.splice(idx, 1);
                renderFelderListe();
            }
        });

        // Schritt-Modal: Bausteine einfügen
        document.getElementById("schritt-modal").addEventListener("click", function (e) {
            var btn = e.target.closest("[data-baustein]");
            if (!btn) return;
            var name = btn.dataset.baustein;
            var felder = FELD_BAUSTEINE[name];
            if (!felder) return;
            var alleIds = [];
            Object.values(schritte).forEach(function (s) {
                (s.felder_json || []).forEach(function (f) { if (f.id) alleIds.push(f.id); });
            });
            schritteFelder.forEach(function (f) { if (f.id) alleIds.push(f.id); });
            felder.forEach(function (vorlage) {
                var neuesFeld = JSON.parse(JSON.stringify(vorlage));
                var id = labelZuId(neuesFeld.label, neuesFeld.typ);
                var basis = id; var z = 2;
                while (alleIds.indexOf(id) !== -1) { id = basis + "_" + z++; }
                neuesFeld.id = id;
                alleIds.push(id);
                schritteFelder.push(neuesFeld);
            });
            renderFelderListe();
        });

        // Schritt-Modal: Duplizieren
        document.getElementById("btn-schritt-duplizieren").addEventListener("click", function () {
            if (!editNodeId || !schritte[editNodeId]) return;
            var original = schritte[editNodeId];
            var nodeId = "s" + Date.now();
            var kopie = JSON.parse(JSON.stringify(original));
            kopie.node_id = nodeId;
            kopie.titel = original.titel + " (Kopie)";
            kopie.ist_start = false;
            kopie.pos_x = (original.pos_x || 300) + 50;
            kopie.pos_y = (original.pos_y || 300) + 120;
            schritte[nodeId] = kopie;
            nodes.add({
                id: nodeId,
                label: knotenLabel(kopie),
                x: kopie.pos_x,
                y: kopie.pos_y,
                color: knotenFarbe(kopie),
                font: { color: "#ffffff" },
            });
            document.getElementById("canvas-hinweis").style.display = "none";
            document.getElementById("speicher-status").textContent = "\"" + kopie.titel + "\" erstellt – bitte speichern.";
            schrittModal.hide();
        });

        // Feld-Modal: Option hinzufügen
        document.getElementById("btn-option-hinzu").addEventListener("click", function () {
            var container = document.getElementById("optionen-liste");
            var leer = document.getElementById("optionen-leer-hinweis");
            if (leer) leer.remove();
            var div = document.createElement("div");
            div.className = "d-flex gap-1 mb-1 optionen-item";
            div.innerHTML = '<span class="drag-handle text-muted px-1" style="cursor:grab; line-height:2;">&#8942;&#8942;</span>'
                + '<input type="text" class="form-control form-control-sm optionen-wert" placeholder="Option">'
                + '<button type="button" class="btn btn-sm btn-outline-danger px-2 optionen-loeschen" title="Entfernen">&times;</button>';
            container.appendChild(div);
            div.querySelector("input").focus();
        });

        // Feld-Modal: Typ-Wechsel
        document.getElementById("feld-typ").addEventListener("change", function () {
            toggleOptionenRow(this.value);
        });

        // Feld-Modal: Label → ID-Vorschau
        document.getElementById("feld-label").addEventListener("input", function () {
            document.getElementById("feld-id-vorschau").textContent = labelZuId(this.value, document.getElementById("feld-typ").value);
        });

        // Feld-Modal: OK
        document.getElementById("btn-feld-ok").addEventListener("click", feldSpeichern);

        // Transition-Modal: Speichern
        document.getElementById("btn-transition-speichern").addEventListener("click", transitionSpeichern);

        // Transition-Modal: verfuegbare Felder einfuegen (Event-Delegation)
        document.getElementById("verfuegbare-felder-inhalt").addEventListener("click", function (e) {
            var btn = e.target.closest("[data-feld-id]");
            if (!btn) return;
            var ta = document.getElementById("transition-bedingung");
            var insertion = "{{" + btn.dataset.feldId + "}}";
            var start = ta.selectionStart;
            var end = ta.selectionEnd;
            ta.value = ta.value.slice(0, start) + insertion + ta.value.slice(end);
            ta.selectionStart = ta.selectionEnd = start + insertion.length;
            ta.focus();
        });
    }

    // -----------------------------------------------------------------------
    // Modus
    // -----------------------------------------------------------------------

    var MODUS_HINWEIS = {
        normal: "Klicke auf einen Knoten zum Bearbeiten | Klicke auf eine Kante zum Bearbeiten",
        schritt: "Klicke auf die freie Flaeche um einen neuen Schritt hinzuzufuegen",
        verbinden: "Klicke den Quell-Knoten, dann den Ziel-Knoten",
        loeschen: "Klicke auf einen Knoten oder eine Kante zum Loeschen",
    };

    function setzeModus(neuerModus) {
        modus = neuerModus;
        verbindeVon = null;
        document.querySelectorAll("[data-modus]").forEach(function (btn) {
            btn.classList.toggle("active", btn.dataset.modus === modus);
        });
        document.getElementById("modus-hinweis").textContent = MODUS_HINWEIS[modus] || "";
        network.unselectAll();
    }

    // -----------------------------------------------------------------------
    // Canvas-Klick (neuer Schritt)
    // -----------------------------------------------------------------------

    function canvasGeklickt(pos) {
        if (modus !== "schritt") return;
        document.getElementById("antraege-canvas").style.cursor = "";
        oeffneSchrittModal(null, pos);
    }

    // -----------------------------------------------------------------------
    // Knoten-Klick
    // -----------------------------------------------------------------------

    function knotenGeklickt(nodeId) {
        if (modus === "normal") {
            oeffneSchrittModal(nodeId, null);
        } else if (modus === "loeschen") {
            knotenLoeschen(nodeId);
        } else if (modus === "verbinden") {
            if (!verbindeVon) {
                verbindeVon = nodeId;
                nodes.update({ id: nodeId, borderWidth: 4, color: { border: "#198754" } });
                document.getElementById("modus-hinweis").textContent = "Jetzt Ziel-Knoten klicken";
            } else if (verbindeVon !== nodeId) {
                kanteHinzufuegen(verbindeVon, nodeId);
                nodes.update({ id: verbindeVon, borderWidth: 2, color: knotenFarbe(schritte[verbindeVon]) });
                verbindeVon = null;
                document.getElementById("modus-hinweis").textContent = MODUS_HINWEIS.verbinden;
            }
        }
    }

    // -----------------------------------------------------------------------
    // Kanten-Klick
    // -----------------------------------------------------------------------

    function kanteGeklickt(edgeId) {
        if (modus === "loeschen") {
            kanteLoeschen(edgeId);
        } else if (modus === "normal") {
            oeffneTransitionModal(edgeId);
        }
    }

    // -----------------------------------------------------------------------
    // Schritt Modal
    // -----------------------------------------------------------------------

    function oeffneSchrittModal(nodeId, canvasPos) {
        editNodeId = nodeId;
        var schritt = nodeId ? schritte[nodeId] : null;

        document.getElementById("schritt-modal-titel").textContent =
            schritt ? "Schritt bearbeiten" : "Neuer Schritt";
        document.getElementById("schritt-titel").value = schritt ? schritt.titel : "";
        document.getElementById("schritt-ist-start").checked = schritt ? !!schritt.ist_start : false;
        document.getElementById("schritt-ist-ende").checked = schritt ? !!schritt.ist_ende : false;

        // Temporaere Felder-Liste aufbauen
        schritteFelder = schritt ? JSON.parse(JSON.stringify(schritt.felder_json || [])) : [];
        renderFelderListe();

        // Canvas-Position merken (wird beim Speichern gebraucht)
        if (canvasPos) {
            document.getElementById("schritt-modal").dataset.posX = canvasPos.x;
            document.getElementById("schritt-modal").dataset.posY = canvasPos.y;
        } else {
            delete document.getElementById("schritt-modal").dataset.posX;
        }

        // Duplizieren-Button nur bei bestehendem Schritt anzeigen
        document.getElementById("btn-schritt-duplizieren").style.display = nodeId ? "" : "none";

        schrittModal.show();
    }

    function schrittSpeichern() {
        var titel = document.getElementById("schritt-titel").value.trim();
        if (!titel) {
            document.getElementById("schritt-titel").classList.add("is-invalid");
            return;
        }
        document.getElementById("schritt-titel").classList.remove("is-invalid");

        var istStart = document.getElementById("schritt-ist-start").checked;
        var istEnde = document.getElementById("schritt-ist-ende").checked;
        var modalEl = document.getElementById("schritt-modal");
        var posX = parseFloat(modalEl.dataset.posX || 300);
        var posY = parseFloat(modalEl.dataset.posY || 300);

        if (editNodeId) {
            // Bestehenden Schritt aktualisieren
            schritte[editNodeId].titel = titel;
            schritte[editNodeId].ist_start = istStart;
            schritte[editNodeId].ist_ende = istEnde;
            schritte[editNodeId].felder_json = JSON.parse(JSON.stringify(schritteFelder));
            nodes.update({
                id: editNodeId,
                label: knotenLabel(schritte[editNodeId]),
                color: knotenFarbe(schritte[editNodeId]),
            });
        } else {
            // Neuen Schritt erstellen
            var nodeId = "s" + Date.now();
            var neuerSchritt = {
                node_id: nodeId,
                titel: titel,
                felder_json: JSON.parse(JSON.stringify(schritteFelder)),
                ist_start: istStart,
                ist_ende: istEnde,
                pos_x: Math.round(posX),
                pos_y: Math.round(posY),
            };
            schritte[nodeId] = neuerSchritt;
            nodes.add({
                id: nodeId,
                label: knotenLabel(neuerSchritt),
                x: Math.round(posX),
                y: Math.round(posY),
                color: knotenFarbe(neuerSchritt),
                font: { color: "#ffffff" },
            });
            document.getElementById("canvas-hinweis").style.display = "none";
        }

        schrittModal.hide();
    }

    // -----------------------------------------------------------------------
    // Feld-Liste rendern (in Schritt-Modal)
    // -----------------------------------------------------------------------

    function renderFelderListe() {
        var container = document.getElementById("schritt-felder-liste");

        if (schritteFelder.length === 0) {
            container.innerHTML = '<p class="text-muted small" id="felder-leer-hinweis">Noch keine Felder. Klicke &quot;+ Feld hinzuf\u00fcgen&quot;.</p>';
            return;
        }

        var TYP_LABEL = {
            text: "Text", mehrzeil: "Mehrzeilig", zahl: "Zahl", datum: "Datum",
            datei: "Datei-Upload", signatur: "Signatur", uhrzeit: "Uhrzeit",
            email: "E-Mail", bool: "Ja/Nein", iban: "IBAN",
            auswahl: "Auswahl", radio: "Multiple Choice", checkboxen: "Checkboxen",
            berechnung: "Berechnung", textblock: "Fliesstext", abschnitt: "Abschnitt",
            link: "Link", trennlinie: "—", leerblock: "Leerblock",
            zusammenfassung: "Zusammenfassung", gruppe: "Wiederholungsgruppe",
        };

        var html = '<ul class="list-group list-group-flush" id="felder-sortable">';
        schritteFelder.forEach(function (feld, idx) {
            html += '<li class="list-group-item px-2 py-1 d-flex justify-content-between align-items-center" data-feld-idx="' + idx + '">';
            html += '<span class="d-flex align-items-center gap-1">';
            html += '<span class="drag-handle text-muted" style="cursor:grab; padding:0 4px; font-size:1rem;" title="Ziehen zum Sortieren">&#8942;</span>';
            html += '<span class="badge bg-secondary small">' + (TYP_LABEL[feld.typ] || feld.typ) + '</span> ';
            html += esc(feld.label || "");
            if (feld.pflicht) html += ' <span class="text-danger small">*</span>';
            html += '</span>';
            html += '<span class="d-flex gap-1">';
            html += '<button type="button" class="btn btn-xs btn-outline-primary px-1 py-0" style="font-size:0.7rem;" data-feld-action="bearbeiten" data-idx="' + idx + '">Bearb.</button>';
            html += '<button type="button" class="btn btn-xs btn-outline-danger px-1 py-0" style="font-size:0.7rem;" data-feld-action="loeschen" data-idx="' + idx + '">&#10005;</button>';
            html += '</span></li>';
        });
        html += '</ul>';
        container.innerHTML = html;

        // SortableJS: Drag & Drop Reihenfolge
        if (typeof Sortable !== "undefined") {
            var ulEl = document.getElementById("felder-sortable");
            if (ulEl) {
                Sortable.create(ulEl, {
                    handle: ".drag-handle",
                    animation: 150,
                    onEnd: function (evt) {
                        var item = schritteFelder.splice(evt.oldIndex, 1)[0];
                        schritteFelder.splice(evt.newIndex, 0, item);
                        // Indizes im DOM aktualisieren (fuer Bearbeiten/Loeschen)
                        ulEl.querySelectorAll("li[data-feld-idx]").forEach(function (li, i) {
                            li.dataset.feldIdx = i;
                            li.querySelectorAll("[data-idx]").forEach(function (btn) {
                                btn.dataset.idx = i;
                            });
                        });
                    },
                });
            }
        }
    }

    // -----------------------------------------------------------------------
    // Feld Modal
    // -----------------------------------------------------------------------

    function oeffneFeldModal(idx) {
        editFeldIndex = idx;
        var feld = (idx !== null) ? schritteFelder[idx] : null;
        document.getElementById("feld-modal-titel").textContent = feld ? "Feld bearbeiten" : "Neues Feld";
        var typ = feld ? feld.typ : "text";
        document.getElementById("feld-typ").value = typ;
        document.getElementById("feld-label").value = feld ? (feld.label || feld.text || "") : "";
        document.getElementById("feld-hilfetext").value = feld ? (feld.hilfetext || "") : "";
        document.getElementById("feld-pflicht").checked = feld ? !!feld.pflicht : false;
        document.getElementById("feld-id-vorschau").textContent = feld ? (feld.id || "") : "";
        document.getElementById("feld-formel").value = feld ? (feld.formel || "") : "";
        document.getElementById("feld-einheit").value = feld ? (feld.einheit || "") : "";
        document.getElementById("feld-akzeptieren").value = feld ? (feld.akzeptieren || "") : "";
        document.getElementById("feld-textblock-inhalt").value = feld ? (feld.text || "") : "";
        document.getElementById("feld-abschnitt-groesse").value = feld ? (feld.groesse || "mittel") : "mittel";
        document.getElementById("feld-abschnitt-ausrichtung").value = feld ? (feld.ausrichtung || "links") : "links";
        document.getElementById("feld-abschnitt-stil").value = feld ? (feld.stil || "normal") : "normal";
        document.getElementById("feld-link-url").value = feld ? (feld.url || "") : "";
        document.getElementById("feld-link-ziel").value = feld ? (feld.ziel || "_blank") : "_blank";
        // Optionen: visuelle Liste aufbauen
        renderOptionenListe((feld && feld.optionen) ? feld.optionen : []);
        // Gruppe: Unterfelder laden
        gruppeUnterfelder = (feld && feld.unterfelder) ? JSON.parse(JSON.stringify(feld.unterfelder)) : [];
        document.getElementById("feld-singular").value = feld ? (feld.singular || "") : "";
        renderGruppeUnterfelder();
        toggleOptionenRow(typ);
        feldModal.show();
    }

    // -----------------------------------------------------------------------
    // Optionen: visuelle Liste
    // -----------------------------------------------------------------------

    function renderOptionenListe(optionen) {
        var container = document.getElementById("optionen-liste");
        if (!optionen || optionen.length === 0) {
            container.innerHTML = '<p class="text-muted small mb-1" id="optionen-leer-hinweis">Noch keine Optionen. Klicke "+ Option hinzufügen".</p>';
            return;
        }
        var html = "";
        optionen.forEach(function (opt) {
            html += '<div class="d-flex gap-1 mb-1 optionen-item">'
                + '<span class="drag-handle text-muted px-1" style="cursor:grab; line-height:2;">&#8942;&#8942;</span>'
                + '<input type="text" class="form-control form-control-sm optionen-wert" value="' + esc(opt) + '" placeholder="Option">'
                + '<button type="button" class="btn btn-sm btn-outline-danger px-2 optionen-loeschen" title="Entfernen">&times;</button>'
                + '</div>';
        });
        container.innerHTML = html;
        // SortableJS fuer Optionen-Liste
        if (typeof Sortable !== "undefined") {
            Sortable.create(container, {
                handle: ".drag-handle",
                animation: 100,
            });
        }
        // Loeschen-Events
        container.addEventListener("click", function (e) {
            if (e.target.classList.contains("optionen-loeschen")) {
                e.target.closest(".optionen-item").remove();
                if (!container.querySelector(".optionen-item")) {
                    container.innerHTML = '<p class="text-muted small mb-1" id="optionen-leer-hinweis">Noch keine Optionen. Klicke "+ Option hinzuf\u00fcgen".</p>';
                }
            }
        });
    }

    function leseOptionen() {
        return Array.from(document.querySelectorAll("#optionen-liste .optionen-wert"))
            .map(function (inp) { return inp.value.trim(); })
            .filter(Boolean);
    }

    var STRUKTUR_TYPEN = ["textblock", "abschnitt", "trennlinie", "leerblock", "zusammenfassung", "link"];

    function toggleOptionenRow(typ) {
        var mitOptionen = ["auswahl", "radio", "checkboxen"];
        var mitFormel = ["berechnung"];
        var mitDatei = ["datei"];
        var mitTextblock = ["textblock"];
        var mitAbschnitt = ["abschnitt"];
        var mitGruppe = ["gruppe"];
        var mitLink = ["link"];
        var ohneLabel = ["trennlinie", "leerblock", "zusammenfassung"];
        var ohneHilfe = ["trennlinie", "leerblock", "bool", "abschnitt", "textblock", "berechnung", "zusammenfassung", "signatur", "gruppe", "link"];
        var ohnePflicht = STRUKTUR_TYPEN.concat(["berechnung", "signatur"]);

        document.getElementById("optionen-row").style.display = mitOptionen.indexOf(typ) >= 0 ? "" : "none";
        document.getElementById("formel-row").style.display = mitFormel.indexOf(typ) >= 0 ? "" : "none";
        document.getElementById("einheit-row").style.display = mitFormel.indexOf(typ) >= 0 ? "" : "none";
        document.getElementById("akzeptieren-row").style.display = mitDatei.indexOf(typ) >= 0 ? "" : "none";
        document.getElementById("textblock-row").style.display = mitTextblock.indexOf(typ) >= 0 ? "" : "none";
        document.getElementById("abschnitt-row").style.display = mitAbschnitt.indexOf(typ) >= 0 ? "" : "none";
        document.getElementById("gruppe-row").style.display = mitGruppe.indexOf(typ) >= 0 ? "" : "none";
        document.getElementById("link-row").style.display = mitLink.indexOf(typ) >= 0 ? "" : "none";
        document.getElementById("pflicht-row").style.display = ohnePflicht.indexOf(typ) >= 0 ? "none" : "";

        var labelRow = document.getElementById("feld-label").closest(".mb-3");
        if (labelRow) labelRow.style.display = ohneLabel.indexOf(typ) >= 0 ? "none" : "";
        var hilfeRow = document.getElementById("feld-hilfetext").closest(".mb-3");
        if (hilfeRow) hilfeRow.style.display = ohneHilfe.indexOf(typ) >= 0 ? "none" : "";
    }

    function feldSpeichern() {
        var typ = document.getElementById("feld-typ").value;
        var label = document.getElementById("feld-label").value.trim();
        var ohneLabel = ["trennlinie", "leerblock", "zusammenfassung"];
        if (!label && ohneLabel.indexOf(typ) === -1) {
            document.getElementById("feld-label").classList.add("is-invalid");
            return;
        }
        document.getElementById("feld-label").classList.remove("is-invalid");

        var feld = {
            typ: typ,
            label: label,
            pflicht: document.getElementById("feld-pflicht").checked,
        };
        var hilfetext = document.getElementById("feld-hilfetext").value.trim();
        if (hilfetext) feld.hilfetext = hilfetext;
        if (typ === "auswahl" || typ === "radio" || typ === "checkboxen") {
            feld.optionen = leseOptionen();
        }
        if (typ === "link") {
            feld.url = document.getElementById("feld-link-url").value.trim();
            feld.ziel = document.getElementById("feld-link-ziel").value;
        }
        if (typ === "berechnung") {
            feld.formel = document.getElementById("feld-formel").value.trim();
            var einheit = document.getElementById("feld-einheit").value.trim();
            if (einheit) feld.einheit = einheit;
        }
        if (typ === "datei") {
            var akz = document.getElementById("feld-akzeptieren").value.trim();
            if (akz) feld.akzeptieren = akz;
        }
        if (typ === "textblock") {
            feld.text = document.getElementById("feld-textblock-inhalt").value;
        }
        if (typ === "abschnitt") {
            feld.text = document.getElementById("feld-label").value.trim();
            feld.groesse = document.getElementById("feld-abschnitt-groesse").value;
            feld.ausrichtung = document.getElementById("feld-abschnitt-ausrichtung").value;
            feld.stil = document.getElementById("feld-abschnitt-stil").value;
        }
        if (typ === "trennlinie" || typ === "leerblock" || typ === "zusammenfassung") {
            feld.label = "";
        }
        if (typ === "gruppe") {
            feld.singular = document.getElementById("feld-singular").value.trim() || "Eintrag";
            // Unterfeld-IDs aus Label ableiten (falls noch keine vorhanden)
            var vorhandeneUfIds = [];
            feld.unterfelder = gruppeUnterfelder.map(function (uf, ufIdx) {
                var uf2 = JSON.parse(JSON.stringify(uf));
                if (!uf2.id) {
                    var basis = labelZuId(uf2.label || ("uf" + ufIdx), uf2.typ);
                    var ufId = basis; var z = 2;
                    while (vorhandeneUfIds.indexOf(ufId) !== -1) { ufId = basis + "_" + z++; }
                    uf2.id = ufId;
                }
                vorhandeneUfIds.push(uf2.id);
                return uf2;
            });
        }

        if (editFeldIndex !== null) {
            feld.id = schritteFelder[editFeldIndex].id || labelZuId(label, typ);
            schritteFelder[editFeldIndex] = feld;
        } else {
            var id = labelZuId(label, typ);
            var basis = id; var z = 2;
            var alleIds = [];
            Object.values(schritte).forEach(function (s) {
                (s.felder_json || []).forEach(function (f) { alleIds.push(f.id); });
            });
            schritteFelder.forEach(function (f) { alleIds.push(f.id); });
            while (alleIds.indexOf(id) !== -1) { id = basis + "_" + z++; }
            feld.id = id;
            schritteFelder.push(feld);
        }

        feldModal.hide();
        schrittModal.show();
        renderFelderListe();
    }

    // -----------------------------------------------------------------------
    // Gruppe: Unterfelder-Editor (im Feld-Modal)
    // -----------------------------------------------------------------------

    var UNTERFELD_TYPEN = [
        ["text", "Text"],
        ["mehrzeil", "Mehrzeilig"],
        ["zahl", "Zahl"],
        ["datum", "Datum"],
        ["uhrzeit", "Uhrzeit"],
        ["bool", "Ja/Nein"],
        ["auswahl", "Auswahl (Dropdown)"],
        ["radio", "Multiple Choice"],
        ["checkboxen", "Checkboxen"],
    ];

    function renderGruppeUnterfelder() {
        var container = document.getElementById("gruppe-unterfelder-liste");
        if (!container) return;
        if (gruppeUnterfelder.length === 0) {
            container.innerHTML = '<p class="text-muted small mb-0" id="gruppe-unterfelder-leer">Noch keine Unterfelder.</p>';
            return;
        }
        var typOptionen = UNTERFELD_TYPEN.map(function (t) {
            return '<option value="' + t[0] + '">' + t[1] + '</option>';
        }).join("");
        var html = "";
        gruppeUnterfelder.forEach(function (uf, idx) {
            var mitOptionen = ["auswahl", "radio", "checkboxen"].indexOf(uf.typ) >= 0;
            html += '<div class="border rounded p-2 mb-1 bg-white">';
            html += '<div class="d-flex gap-2 align-items-start">';
            // Typ-Auswahl
            html += '<select class="form-select form-select-sm" style="width:160px; flex-shrink:0;" data-uf-action="typ" data-uf-idx="' + idx + '">';
            UNTERFELD_TYPEN.forEach(function (t) {
                html += '<option value="' + t[0] + '"' + (uf.typ === t[0] ? " selected" : "") + '>' + t[1] + '</option>';
            });
            html += '</select>';
            // Label
            html += '<input type="text" class="form-control form-control-sm" placeholder="Bezeichnung *"';
            html += ' value="' + esc(uf.label || "") + '" data-uf-action="label" data-uf-idx="' + idx + '">';
            // Pflicht
            html += '<div class="form-check mt-1 flex-shrink-0">';
            html += '<input class="form-check-input" type="checkbox" title="Pflichtfeld"';
            html += ' data-uf-action="pflicht" data-uf-idx="' + idx + '"' + (uf.pflicht ? " checked" : "") + '>';
            html += '<label class="form-check-label small">Pflicht</label></div>';
            // Loeschen
            html += '<button type="button" class="btn btn-xs btn-outline-danger px-1 py-0 flex-shrink-0"';
            html += ' style="font-size:0.75rem;" data-uf-action="loeschen" data-uf-idx="' + idx + '">&#10005;</button>';
            html += '</div>';
            // Optionen (nur bei auswahl/radio/checkboxen)
            html += '<div class="mt-1"' + (mitOptionen ? "" : ' style="display:none;"') + ' data-uf-optionen-idx="' + idx + '">';
            html += '<textarea class="form-control form-control-sm" rows="2" placeholder="Eine Option pro Zeile"';
            html += ' data-uf-action="optionen" data-uf-idx="' + idx + '">' + esc((uf.optionen || []).join("\n")) + '</textarea>';
            html += '</div>';
            html += '</div>';
        });
        container.innerHTML = html;
    }

    // Event-Delegation fuer Unterfeld-Aktionen
    document.addEventListener("DOMContentLoaded", function () {
        var gruppeContainer = document.getElementById("gruppe-unterfelder-liste");
        if (gruppeContainer) {
            gruppeContainer.addEventListener("input", function (e) {
                var el = e.target;
                var idx = parseInt(el.dataset.ufIdx);
                if (isNaN(idx)) return;
                var action = el.dataset.ufAction;
                if (action === "label") {
                    gruppeUnterfelder[idx].label = el.value;
                } else if (action === "optionen") {
                    gruppeUnterfelder[idx].optionen = el.value.split("\n").map(function (o) { return o.trim(); }).filter(Boolean);
                }
            });
            gruppeContainer.addEventListener("change", function (e) {
                var el = e.target;
                var idx = parseInt(el.dataset.ufIdx);
                if (isNaN(idx)) return;
                var action = el.dataset.ufAction;
                if (action === "typ") {
                    gruppeUnterfelder[idx].typ = el.value;
                    var mitOptionen = ["auswahl", "radio", "checkboxen"].indexOf(el.value) >= 0;
                    var optDiv = gruppeContainer.querySelector('[data-uf-optionen-idx="' + idx + '"]');
                    if (optDiv) optDiv.style.display = mitOptionen ? "" : "none";
                } else if (action === "pflicht") {
                    gruppeUnterfelder[idx].pflicht = el.checked;
                }
            });
            gruppeContainer.addEventListener("click", function (e) {
                var btn = e.target.closest("[data-uf-action='loeschen']");
                if (!btn) return;
                var idx = parseInt(btn.dataset.ufIdx);
                if (isNaN(idx)) return;
                gruppeUnterfelder.splice(idx, 1);
                renderGruppeUnterfelder();
            });
        }
        var btnUnterfeldHinzu = document.getElementById("btn-unterfeld-hinzu");
        if (btnUnterfeldHinzu) {
            btnUnterfeldHinzu.addEventListener("click", function () {
                gruppeUnterfelder.push({ typ: "text", id: "", label: "", pflicht: false });
                renderGruppeUnterfelder();
            });
        }
    });

    // -----------------------------------------------------------------------
    // Kante hinzufuegen
    // -----------------------------------------------------------------------

    function kanteHinzufuegen(von, zu) {
        var edgeId = "e" + Date.now();
        var transition = { id: edgeId, von: von, zu: zu, bedingung: "", label: "", reihenfolge: 0 };
        transitionen.push(transition);
        edges.add({ id: edgeId, from: von, to: zu, label: "" });
        // Direkt Transition-Modal oeffnen
        oeffneTransitionModal(edgeId);
    }

    // -----------------------------------------------------------------------
    // Transition Modal – Visueller Bedingungsbuilder
    // -----------------------------------------------------------------------

    var OPERATOREN_TYPEN = {
        text:        [["==","gleich"], ["!=","ungleich"]],
        mehrzeil:    [["==","gleich"], ["!=","ungleich"]],
        email:       [["==","gleich"], ["!=","ungleich"]],
        iban:        [["==","gleich"], ["!=","ungleich"]],
        zahl:        [["==","gleich"], ["!=","ungleich"], [">","größer als"], ["<","kleiner als"], [">=","größer gleich"], ["<=","kleiner gleich"]],
        berechnung:  [["==","gleich"], ["!=","ungleich"], [">","größer als"], ["<","kleiner als"], [">=","größer gleich"], ["<=","kleiner gleich"]],
        datum:       [["==","gleich"], ["<","vor dem Datum"], [">","nach dem Datum"]],
        bool:        [["==\"True\"","ist aktiv (Ja)"], ["==\"False\"","ist nicht aktiv (Nein)"]],
        auswahl:     [["==","gleich"], ["!=","ungleich"]],
        radio:       [["==","gleich"], ["!=","ungleich"]],
        checkboxen:  [["==","enthält"], ["!=","enthält nicht"]],
        uhrzeit:     [["==","gleich"], [">","nach"], ["<","vor"]],
    };

    // -----------------------------------------------------------------------
    // Feld-Bausteine (vorgefertigte Feldgruppen)
    // -----------------------------------------------------------------------

    var FELD_BAUSTEINE = {
        personalien: [
            { typ: "text",  label: "Familienname",  pflicht: true  },
            { typ: "text",  label: "Geburtsname",   pflicht: false },
            { typ: "text",  label: "Vorname",        pflicht: true  },
            { typ: "datum", label: "Geburtsdatum",   pflicht: true  },
            { typ: "text",  label: "Geburtsort",     pflicht: false },
        ],
        adresse: [
            { typ: "text", label: "Straße und Hausnummer", pflicht: true  },
            { typ: "text", label: "PLZ",                   pflicht: true  },
            { typ: "text", label: "Wohnort",               pflicht: true  },
        ],
        kontakt: [
            { typ: "text",  label: "Telefonnummer",  pflicht: false },
            { typ: "email", label: "E-Mail-Adresse", pflicht: false },
        ],
        antragsteller: [
            { typ: "text",  label: "Familienname",          pflicht: true  },
            { typ: "text",  label: "Geburtsname",           pflicht: false },
            { typ: "text",  label: "Vorname",               pflicht: true  },
            { typ: "datum", label: "Geburtsdatum",          pflicht: true  },
            { typ: "text",  label: "Geburtsort",            pflicht: false },
            { typ: "text",  label: "Straße und Hausnummer", pflicht: true  },
            { typ: "text",  label: "PLZ",                   pflicht: true  },
            { typ: "text",  label: "Wohnort",               pflicht: true  },
            { typ: "text",  label: "Telefonnummer",         pflicht: false },
            { typ: "email", label: "E-Mail-Adresse",        pflicht: false },
        ],
    };

    function _alleInputFelder() {
        var felder = [];
        var KEINE = ["textblock", "abschnitt", "trennlinie", "leerblock", "zusammenfassung", "link", "signatur"];
        Object.values(schritte).forEach(function (s) {
            (s.felder_json || []).forEach(function (f) {
                if (f.id && KEINE.indexOf(f.typ) === -1) felder.push(f);
            });
        });
        return felder;
    }

    function _feldById(feld_id) {
        return _alleInputFelder().find(function (f) { return f.id === feld_id; }) || null;
    }

    function _renderRegelZeile(feld_id, op_raw, wert) {
        var felder = _alleInputFelder();
        var feldOpts = '<option value="">— Feld wählen —</option>';
        felder.forEach(function (f) {
            feldOpts += '<option value="' + esc(f.id) + '"' + (f.id === feld_id ? ' selected' : '') + '>' + esc(f.label || f.id) + '</option>';
        });

        var feld = _feldById(feld_id);
        var opListe = (feld && OPERATOREN_TYPEN[feld.typ]) ? OPERATOREN_TYPEN[feld.typ] : OPERATOREN_TYPEN.text;
        var opOpts = opListe.map(function (o) {
            return '<option value="' + esc(o[0]) + '"' + (o[0] === op_raw ? ' selected' : '') + '>' + esc(o[1]) + '</option>';
        }).join("");

        // Wert-Input: bei auswahl/radio Dropdown, bei bool versteckt
        var istBool = feld && feld.typ === "bool";
        var hatOptionen = feld && (feld.typ === "auswahl" || feld.typ === "radio" || feld.typ === "checkboxen") && feld.optionen && feld.optionen.length;
        var wertHtml = "";
        if (istBool) {
            wertHtml = '<input type="hidden" class="regel-wert" value="">';
        } else if (hatOptionen) {
            var selOpts = '<option value="">— wählen —</option>';
            feld.optionen.forEach(function (o) {
                selOpts += '<option value="' + esc(o) + '"' + (o === wert ? ' selected' : '') + '>' + esc(o) + '</option>';
            });
            wertHtml = '<select class="form-select form-select-sm regel-wert" style="min-width:140px;">' + selOpts + '</select>';
        } else {
            var inputTyp = (feld && (feld.typ === "zahl" || feld.typ === "berechnung")) ? "number" : (feld && feld.typ === "datum" ? "date" : "text");
            wertHtml = '<input type="' + inputTyp + '" class="form-control form-control-sm regel-wert" style="min-width:120px;" placeholder="Wert" value="' + esc(wert) + '">';
        }

        return '<div class="d-flex align-items-center gap-2 mb-2 regel-zeile">'
            + '<select class="form-select form-select-sm regel-feld" style="max-width:200px;">' + feldOpts + '</select>'
            + '<select class="form-select form-select-sm regel-op" style="max-width:160px;">' + opOpts + '</select>'
            + wertHtml
            + '<button type="button" class="btn btn-sm btn-outline-danger regel-loeschen" title="Entfernen">&times;</button>'
            + '</div>';
    }

    function _builderNeuzeichnen(regeln) {
        var container = document.getElementById("builder-regeln");
        container.innerHTML = "";
        if (!regeln || regeln.length === 0) {
            container.innerHTML = '<div class="text-muted small mb-2">Noch keine Bedingung. Klicke "+ Bedingung hinzufügen".</div>';
            document.getElementById("verbinder-auswahl").style.display = "none";
            return;
        }
        regeln.forEach(function (r) {
            container.insertAdjacentHTML("beforeend", _renderRegelZeile(r.feld_id || "", r.op || "==", r.wert || ""));
        });
        document.getElementById("verbinder-auswahl").style.display = regeln.length > 1 ? "" : "none";

        // Events
        container.querySelectorAll(".regel-feld").forEach(function (sel) {
            sel.addEventListener("change", function () {
                var zeile = sel.closest(".regel-zeile");
                var neu = _renderRegelZeile(sel.value, "==", "");
                zeile.outerHTML = neu;
                // re-attach events
                _reattachRegelEvents(container);
                document.getElementById("verbinder-auswahl").style.display =
                    container.querySelectorAll(".regel-zeile").length > 1 ? "" : "none";
            });
        });
        _reattachRegelEvents(container);
    }

    function _reattachRegelEvents(container) {
        container.querySelectorAll(".regel-loeschen").forEach(function (btn) {
            btn.onclick = function () {
                btn.closest(".regel-zeile").remove();
                document.getElementById("verbinder-auswahl").style.display =
                    container.querySelectorAll(".regel-zeile").length > 1 ? "" : "none";
                if (container.querySelectorAll(".regel-zeile").length === 0) {
                    container.innerHTML = '<div class="text-muted small mb-2">Noch keine Bedingung. Klicke "+ Bedingung hinzufügen".</div>';
                }
            };
        });
        container.querySelectorAll(".regel-feld").forEach(function (sel) {
            if (!sel._hasEvent) {
                sel._hasEvent = true;
                sel.addEventListener("change", function () {
                    var zeile = sel.closest(".regel-zeile");
                    zeile.outerHTML = _renderRegelZeile(sel.value, "==", "");
                    _reattachRegelEvents(container);
                    document.getElementById("verbinder-auswahl").style.display =
                        container.querySelectorAll(".regel-zeile").length > 1 ? "" : "none";
                });
            }
        });
    }

    function _leseRegeln() {
        var regeln = [];
        document.querySelectorAll("#builder-regeln .regel-zeile").forEach(function (zeile) {
            var feld_id = zeile.querySelector(".regel-feld").value;
            var op = zeile.querySelector(".regel-op").value;
            var wertEl = zeile.querySelector(".regel-wert");
            var wert = wertEl ? wertEl.value : "";
            if (feld_id) regeln.push({ feld_id: feld_id, op: op, wert: wert });
        });
        return regeln;
    }

    function _generiereFormel(regeln, verbinder) {
        if (!regeln || regeln.length === 0) return "";
        var teile = regeln.map(function (r) {
            var feld = _feldById(r.feld_id);
            var istBool = feld && feld.typ === "bool";
            var istZahl = feld && (feld.typ === "zahl" || feld.typ === "berechnung");
            if (istBool) {
                // Op ist z.B. =="True" oder =="False"
                return "{{" + r.feld_id + "}}" + r.op;
            }
            if (r.op.startsWith("==") || r.op.startsWith("!=")) {
                // == oder !=
                var op2 = r.op.length === 2 ? r.op : "==";
                if (istZahl) return "{{" + r.feld_id + "}} " + op2 + " " + (parseFloat(r.wert) || 0);
                return "{{" + r.feld_id + "}} " + op2 + " \"" + r.wert.replace(/"/g, '\\"') + "\"";
            }
            // >, <, >=, <=
            return "{{" + r.feld_id + "}} " + r.op + " " + (parseFloat(r.wert) || 0);
        });
        return teile.join(" " + (verbinder || "and") + " ");
    }

    function _parseFormelZuRegeln(formel) {
        if (!formel || !formel.trim()) return { modus: "immer", regeln: [], verbinder: "and" };
        var verbinder = "and";
        var teile;
        if (/\bor\b/.test(formel) && !/\band\b/.test(formel)) {
            verbinder = "or";
            teile = formel.split(/\bor\b/);
        } else {
            teile = formel.split(/\band\b/);
        }
        var regeln = [];
        for (var i = 0; i < teile.length; i++) {
            var teil = teile[i].trim();
            // Bool: {{feld}}=="True" oder {{feld}}=="False"
            var boolMatch = teil.match(/^\{\{(\w+)\}\}(==\"True\"|==\"False\")$/);
            if (boolMatch) {
                regeln.push({ feld_id: boolMatch[1], op: boolMatch[2], wert: "" });
                continue;
            }
            // Zahl oder Text: {{feld}} op wert
            var m = teil.match(/^\{\{(\w+)\}\}\s*(==|!=|>=|<=|>|<)\s*(.+)$/);
            if (!m) return null; // nicht parsierbar
            var wert = m[3].trim();
            if (wert.startsWith('"') && wert.endsWith('"')) wert = wert.slice(1, -1);
            regeln.push({ feld_id: m[1], op: m[2], wert: wert });
        }
        return { modus: "visuell", regeln: regeln, verbinder: verbinder };
    }

    function _setzeModus(modus) {
        document.getElementById("builder-visuell").style.display = modus === "visuell" ? "" : "none";
        document.getElementById("builder-experte").style.display = modus === "experte" ? "" : "none";
        var radio = document.querySelector('input[name="bedingung-modus"][value="' + modus + '"]');
        if (radio) radio.checked = true;
    }

    function oeffneTransitionModal(edgeId) {
        editEdgeId = edgeId;
        var t = transitionen.find(function (x) { return x.id === edgeId; });
        if (!t) return;

        document.getElementById("transition-label").value = t.label || "";
        document.getElementById("transition-reihenfolge").value = t.reihenfolge || 0;

        // Formel parsen und Modus bestimmen
        var geparst = _parseFormelZuRegeln(t.bedingung || "");
        if (!geparst) {
            // Nicht parsierbar → Experte
            _setzeModus("experte");
            document.getElementById("transition-bedingung").value = t.bedingung || "";
        } else if (geparst.modus === "immer") {
            _setzeModus("immer");
            _builderNeuzeichnen([]);
        } else {
            _setzeModus("visuell");
            document.getElementById("regel-verbinder").value = geparst.verbinder;
            _builderNeuzeichnen(geparst.regeln);
        }

        // Verfuegbare Felder fuer Experten-Modus
        var felder = _alleInputFelder();
        var html = felder.length === 0
            ? '<span class="text-muted small">Noch keine Felder definiert.</span>'
            : felder.map(function (f) {
                return '<button type="button" class="btn btn-sm btn-outline-secondary me-1 mb-1" data-feld-id="' + esc(f.id) + '">'
                    + esc(f.label || f.id) + ' <code class="small">{{' + esc(f.id) + '}}</code></button>';
            }).join("");
        document.getElementById("verfuegbare-felder-inhalt").innerHTML = html;

        transitionModal.show();
    }

    // Modus-Radio Listener
    document.querySelectorAll('input[name="bedingung-modus"]').forEach(function (radio) {
        radio.addEventListener("change", function () { _setzeModus(this.value); });
    });

    // + Bedingung hinzufügen
    document.getElementById("btn-regel-hinzu").addEventListener("click", function () {
        var container = document.getElementById("builder-regeln");
        var leer = container.querySelector(".text-muted");
        if (leer) leer.remove();
        container.insertAdjacentHTML("beforeend", _renderRegelZeile("", "==", ""));
        _reattachRegelEvents(container);
        document.getElementById("verbinder-auswahl").style.display =
            container.querySelectorAll(".regel-zeile").length > 1 ? "" : "none";
    });

    function transitionSpeichern() {
        var t = transitionen.find(function (x) { return x.id === editEdgeId; });
        if (!t) { transitionModal.hide(); return; }

        var modus = document.querySelector('input[name="bedingung-modus"]:checked');
        modus = modus ? modus.value : "immer";

        if (modus === "immer") {
            t.bedingung = "";
        } else if (modus === "visuell") {
            var regeln = _leseRegeln();
            var verbinder = document.getElementById("regel-verbinder").value;
            t.bedingung = _generiereFormel(regeln, verbinder);
        } else {
            t.bedingung = document.getElementById("transition-bedingung").value.trim();
        }

        t.label = document.getElementById("transition-label").value.trim();
        t.reihenfolge = parseInt(document.getElementById("transition-reihenfolge").value, 10) || 0;

        // Automatisches Label wenn leer
        if (!t.label && t.bedingung) {
            var m = t.bedingung.match(/"\s*(.*?)\s*"/);
            t.label = m ? m[1] : (t.bedingung.length <= 20 ? t.bedingung : "?");
        }

        edges.update({ id: editEdgeId, label: t.label || (t.bedingung ? "…" : "") });
        transitionModal.hide();
    }

    // -----------------------------------------------------------------------
    // Loeschen
    // -----------------------------------------------------------------------

    function knotenLoeschen(nodeId) {
        if (!confirm("Schritt \"" + (schritte[nodeId] ? schritte[nodeId].titel : nodeId) + "\" loeschen?")) return;
        // Alle verbundenen Kanten entfernen
        transitionen = transitionen.filter(function (t) {
            if (t.von === nodeId || t.zu === nodeId) {
                edges.remove(t.id);
                return false;
            }
            return true;
        });
        nodes.remove(nodeId);
        delete schritte[nodeId];
    }

    function kanteLoeschen(edgeId) {
        transitionen = transitionen.filter(function (t) { return t.id !== edgeId; });
        edges.remove(edgeId);
    }

    // -----------------------------------------------------------------------
    // Pfad laden
    // -----------------------------------------------------------------------

    function ladePfad(pk) {
        fetch("/antraege/editor/laden/" + pk + "/", {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
        .then(function (r) { return r.json(); })
        .then(function (daten) {
            document.getElementById("pfad-name").value = daten.name || "";
            document.getElementById("pfad-beschreibung").value = daten.beschreibung || "";
            document.getElementById("pfad-aktiv").checked = !!daten.aktiv;
            document.getElementById("pfad-workflow-template").value = daten.workflow_template_id || "";

            // Schritte aufbauen
            (daten.schritte || []).forEach(function (s) {
                schritte[s.node_id] = {
                    node_id: s.node_id,
                    titel: s.titel,
                    felder_json: s.felder_json || [],
                    ist_start: s.ist_start,
                    ist_ende: s.ist_ende,
                    pos_x: s.pos_x,
                    pos_y: s.pos_y,
                };
                nodes.add({
                    id: s.node_id,
                    label: knotenLabel(schritte[s.node_id]),
                    x: s.pos_x,
                    y: s.pos_y,
                    color: knotenFarbe(schritte[s.node_id]),
                    font: { color: "#ffffff" },
                });
            });

            // Kanten aufbauen
            (daten.transitionen || []).forEach(function (t) {
                var edgeId = "e" + t.von + "_" + t.zu + "_" + Date.now();
                transitionen.push({ id: edgeId, von: t.von, zu: t.zu, bedingung: t.bedingung, label: t.label, reihenfolge: t.reihenfolge });
                edges.add({ id: edgeId, from: t.von, to: t.zu, label: t.label || (t.bedingung ? "?" : "") });
            });

            if (nodes.length > 0) {
                document.getElementById("canvas-hinweis").style.display = "none";
                network.fit();
            }
            document.getElementById("speicher-status").textContent = "Geladen";
        })
        .catch(function () {
            document.getElementById("speicher-status").textContent = "Fehler beim Laden";
        });
    }

    // -----------------------------------------------------------------------
    // Speichern
    // -----------------------------------------------------------------------

    function speichern() {
        var name = document.getElementById("pfad-name").value.trim();
        if (!name) {
            document.getElementById("pfad-name").classList.add("is-invalid");
            document.getElementById("pfad-name").focus();
            return;
        }
        document.getElementById("pfad-name").classList.remove("is-invalid");

        // Aktuelle Positionen aus vis.js lesen
        var positionen = network.getPositions();
        Object.keys(schritte).forEach(function (nodeId) {
            if (positionen[nodeId]) {
                schritte[nodeId].pos_x = Math.round(positionen[nodeId].x);
                schritte[nodeId].pos_y = Math.round(positionen[nodeId].y);
            }
        });

        var payload = {
            pk: pfadPk,
            name: name,
            beschreibung: document.getElementById("pfad-beschreibung").value.trim(),
            aktiv: document.getElementById("pfad-aktiv").checked,
            workflow_template_id: document.getElementById("pfad-workflow-template").value || null,
            schritte: Object.values(schritte),
            transitionen: transitionen,
        };

        document.getElementById("speicher-status").textContent = "Speichert...";
        document.getElementById("btn-speichern").disabled = true;

        fetch("/antraege/editor/speichern/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken(),
            },
            body: JSON.stringify(payload),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            document.getElementById("btn-speichern").disabled = false;
            if (data.ok) {
                pfadPk = data.pk;
                document.getElementById("speicher-status").textContent = "Gespeichert (" + data.name + ")";
                // URL aktualisieren ohne Reload
                history.replaceState(null, "", "/antraege/editor/" + pfadPk + "/");
            } else {
                document.getElementById("speicher-status").textContent = "Fehler: " + (data.fehler || "Unbekannt");
            }
        })
        .catch(function () {
            document.getElementById("btn-speichern").disabled = false;
            document.getElementById("speicher-status").textContent = "Netzwerkfehler";
        });
    }

    // -----------------------------------------------------------------------
    // Hilfsfunktionen
    // -----------------------------------------------------------------------

    function knotenLabel(schritt) {
        var prefix = schritt.ist_start ? "[S] " : (schritt.ist_ende ? "[E] " : "");
        var KEINE_EINGABE = ["textblock", "abschnitt", "trennlinie", "leerblock", "zusammenfassung", "link"];
        var anzahl = (schritt.felder_json || []).filter(function (f) {
            return KEINE_EINGABE.indexOf(f.typ) === -1;
        }).length;
        var suffix = anzahl > 0 ? "\n(" + anzahl + " Feld" + (anzahl !== 1 ? "er" : "") + ")" : "";
        return prefix + schritt.titel + suffix;
    }

    function knotenFarbe(schritt) {
        if (schritt.ist_start) return { background: "#198754", border: "#145c32" };
        if (schritt.ist_ende)  return { background: "#dc3545", border: "#a12030" };
        return { background: "#1a4d2e", border: "#12341f" };
    }

    function labelZuId(label, typ) {
        var basis = label.toLowerCase()
            .replace(/ae/g, "ae").replace(/oe/g, "oe").replace(/ue/g, "ue")
            .replace(/[^\w]/g, "_").replace(/_+/g, "_").replace(/^_|_$/g, "");
        if (!basis) basis = "feld";
        var typSuffix = {
            zahl: "_zahl", datum: "_datum", uhrzeit: "_uhrzeit", bool: "_bool", email: "_email"
        };
        return basis + (typSuffix[typ] || "");
    }

    function csrfToken() {
        var meta = document.querySelector("meta[name='csrf-token']");
        return meta ? meta.content : "";
    }

    function esc(str) {
        return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

}());
