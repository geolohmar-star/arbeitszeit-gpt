/**
 * schema_editor.js – Formular-Builder Editor
 * Unterstuetzt normale Felder, Textblöcke mit Inline-Feldern, Abschnitte, Trennlinien.
 * CSP-konform: kein Inline-JS, Event-Delegation via data-action.
 */
(function () {
    "use strict";

    var felder = [];
    var editIndex = null;
    var modal = null;
    var bausteinModal = null;

    var NORMALE_TYPEN = ["text", "mehrzeil", "zahl", "datum", "uhrzeit", "email", "iban", "bool", "auswahl", "radio", "checkboxen"];
    var STRUKTUR_TYPEN = ["textblock", "abschnitt", "trennlinie", "link", "leerblock", "berechnung"];

    var TYP_LABEL = {
        text: "Text", mehrzeil: "Mehrzeilig", zahl: "Zahl",
        datum: "Datum", uhrzeit: "Uhrzeit", email: "E-Mail", iban: "IBAN", bool: "Ja/Nein", auswahl: "Auswahl",
        radio: "Multiple Choice", checkboxen: "Kontrollkästchen",
        textblock: "Fließtext", abschnitt: "Abschnitt", trennlinie: "Trennlinie", leerblock: "Leerblock",
        berechnung: "Berechnungsfeld"
    };
    var BREITE_LABEL = { 25: "¼", 50: "½", 75: "¾", 100: "Voll" };

    // Inline-Input-Breiten je Typ (px)
    var INLINE_BREITE = { datum: 160, zahl: 70, bool: 20, auswahl: 160 };

    // -----------------------------------------------------------------------
    // Init
    // -----------------------------------------------------------------------

    document.addEventListener("DOMContentLoaded", function () {
        var feldModalEl = document.getElementById("feld-modal");
        modal = new bootstrap.Modal(feldModalEl, { backdrop: true, keyboard: true });

        // Fokus erst setzen wenn Modal vollständig geöffnet – verhindert Backdrop-Bug
        feldModalEl.addEventListener("shown.bs.modal", function () {
            var typ = document.getElementById("feld-typ").value;
            if (["text", "mehrzeil", "zahl", "datum", "uhrzeit", "email", "iban", "bool", "auswahl", "radio", "checkboxen"].indexOf(typ) !== -1) {
                document.getElementById("feld-label").focus();
            }
        });

        // Backdrop-Cleanup: Bootstrap lässt den Backdrop manchmal hängen
        // wenn show() programmatisch ohne Trigger-Element aufgerufen wird.
        feldModalEl.addEventListener("hidden.bs.modal", function () {
            document.querySelectorAll(".modal-backdrop").forEach(function (el) { el.remove(); });
            document.body.classList.remove("modal-open");
            document.body.style.removeProperty("overflow");
            document.body.style.removeProperty("padding-right");
        });

        var bausteinModalEl = document.getElementById("baustein-modal");
        if (bausteinModalEl) {
            bausteinModal = new bootstrap.Modal(bausteinModalEl, { backdrop: true, keyboard: true });
            bausteinModalEl.addEventListener("hidden.bs.modal", function () {
                document.querySelectorAll(".modal-backdrop").forEach(function (el) { el.remove(); });
                document.body.classList.remove("modal-open");
                document.body.style.removeProperty("overflow");
                document.body.style.removeProperty("padding-right");
            });
        }

        var input = document.getElementById("schema-json-input");
        try {
            var parsed = JSON.parse(input.value || "{}");
            felder = parsed.felder || [];
        } catch (e) {
            felder = [];
        }

        renderFelderListe();
        updateVorschau();

        document.getElementById("btn-feld-hinzufuegen").addEventListener("click", function () {
            oeffneModal(null);
        });

        var btnBaustein = document.getElementById("btn-baustein-einfuegen");
        if (btnBaustein) {
            btnBaustein.addEventListener("click", oeffneBausteinModal);
        }

        document.getElementById("btn-feld-speichern").addEventListener("click", speichereFeld);

        document.getElementById("feld-typ").addEventListener("change", function () {
            toggleModalFelder(this.value);
        });

        document.getElementById("feld-label").addEventListener("input", function () {
            var typ = document.getElementById("feld-typ").value;
            document.getElementById("feld-id-preview").textContent = labelZuId(this.value, typ);
        });

        // Event-Delegation: Feld-Liste
        document.getElementById("felder-liste").addEventListener("click", function (e) {
            var btn = e.target.closest("[data-action]");
            if (!btn) return;
            var action = btn.dataset.action;
            var idx = parseInt(btn.dataset.index, 10);

            if (action === "feld-bearbeiten") {
                oeffneModal(idx);
            } else if (action === "feld-loeschen") {
                if (confirm('Element "' + (felder[idx].label || felder[idx].text || TYP_LABEL[felder[idx].typ]) + '" wirklich entfernen?')) {
                    felder.splice(idx, 1);
                    renderFelderListe();
                    updateVorschau();
                }
            } else if (action === "feld-hoch" && idx > 0) {
                var tmp = felder[idx - 1]; felder[idx - 1] = felder[idx]; felder[idx] = tmp;
                renderFelderListe(); updateVorschau();
            } else if (action === "feld-runter" && idx < felder.length - 1) {
                var tmp2 = felder[idx + 1]; felder[idx + 1] = felder[idx]; felder[idx] = tmp2;
                renderFelderListe(); updateVorschau();
            }
        });

        // Event-Delegation: Felder in Textblock einfügen
        document.getElementById("verfuegbare-felder-liste").addEventListener("click", function (e) {
            e.stopPropagation();
            var btn = e.target.closest("[data-action='insert-feld']");
            if (!btn || btn.disabled) return;
            var feldId = btn.dataset.feldId;
            var ta = document.getElementById("feld-textblock-inhalt");
            // Bereits enthalten? Nicht nochmals einfügen.
            if (ta.value.indexOf("{{" + feldId + "}}") !== -1) return;
            var start = ta.selectionStart;
            var end = ta.selectionEnd;
            var insertion = "{{" + feldId + "}}";
            ta.value = ta.value.slice(0, start) + insertion + ta.value.slice(end);
            ta.selectionStart = ta.selectionEnd = start + insertion.length;
            ta.focus();
            // Button sofort deaktivieren – verhindert Doppel-Einfügen auch bei Event-Anomalien
            btn.disabled = true;
            btn.classList.add("disabled");
        });

        // Felder-Buttons reaktivieren wenn Placeholder manuell entfernt wird
        document.getElementById("feld-textblock-inhalt").addEventListener("input", function () {
            syncFeldButtonZustand();
        });

        // Event-Delegation: Felder in Formel einfügen
        document.getElementById("berechnung-felder-liste").addEventListener("click", function (e) {
            e.stopPropagation();
            var btn = e.target.closest("[data-action='insert-berechnung-feld']");
            if (!btn) return;
            var feldId = btn.dataset.feldId;
            var ta = document.getElementById("feld-formel");
            var start = ta.selectionStart;
            var end = ta.selectionEnd;
            var insertion = "{{" + feldId + "}}";
            ta.value = ta.value.slice(0, start) + insertion + ta.value.slice(end);
            ta.selectionStart = ta.selectionEnd = start + insertion.length;
            ta.focus();
        });

        // Berechnungs-Label → ID-Vorschau
        document.getElementById("feld-berechnung-label").addEventListener("input", function () {
            document.getElementById("feld-berechnung-id-preview").textContent = labelZuId(this.value, "berechnung");
        });

        document.getElementById("schema-form").addEventListener("submit", syncHiddenInput);
    });

    // -----------------------------------------------------------------------
    // Hilfsfunktionen
    // -----------------------------------------------------------------------

    function labelZuId(label, typ) {
        var basis = label.toLowerCase()
            .replace(/ä/g, "ae").replace(/ö/g, "oe").replace(/ü/g, "ue").replace(/ß/g, "ss")
            .replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "feld";
        return basis + "_" + (typ || "text");
    }

    function syncHiddenInput() {
        document.getElementById("schema-json-input").value = JSON.stringify({ felder: felder }, null, 2);
    }

    function breiteZuCol(breite) {
        return { 25: "col-3", 50: "col-6", 75: "col-9", 100: "col-12" }[breite] || "col-12";
    }

    function istNormalerTyp(typ) {
        return NORMALE_TYPEN.indexOf(typ) !== -1;
    }

    // Feld-Map der normalen Felder (fuer Inline-Referenzen)
    function buildFeldMap() {
        var map = {};
        felder.forEach(function (f) {
            if (istNormalerTyp(f.typ)) map[f.id] = f;
        });
        return map;
    }

    // IDs die in Textblöcken eingebettet sind (nicht standalone rendern)
    function inlineFeldIds() {
        var ids = {};
        felder.forEach(function (f) {
            if (f.typ === "textblock" && f.text) {
                var matches = f.text.match(/\{\{(\w+)\}\}/g) || [];
                matches.forEach(function (m) { ids[m.replace(/\{\{|\}\}/g, "")] = true; });
            }
        });
        return ids;
    }

    // -----------------------------------------------------------------------
    // Modal
    // -----------------------------------------------------------------------

    function toggleModalFelder(typ) {
        var istNormal = istNormalerTyp(typ);
        var istTextblock = typ === "textblock";
        var istAbschnitt = typ === "abschnitt";
        var istLink = typ === "link";
        var istBerechnung = typ === "berechnung";

        // Normale Felder-Zeilen
        document.querySelectorAll(".feld-normal-row").forEach(function (el) {
            el.style.display = istNormal ? "" : "none";
        });

        // Auswahl-Optionen (bei auswahl, radio, checkboxen)
        document.getElementById("auswahl-optionen-row").style.display =
            (typ === "auswahl" || typ === "radio" || typ === "checkboxen") ? "" : "none";

        // Textblock
        document.getElementById("textblock-row").style.display = istTextblock ? "" : "none";

        // Abschnitt
        document.getElementById("abschnitt-row").style.display = istAbschnitt ? "" : "none";

        // Link
        document.getElementById("link-row").style.display = istLink ? "" : "none";

        // Berechnungsfeld
        document.getElementById("berechnung-row").style.display = istBerechnung ? "" : "none";

        // Verfügbare Felder Liste aktualisieren
        if (istTextblock) updateVerfuegbareFelderListe();
        if (istBerechnung) updateBerechnungFelderListe();
    }

    function updateVerfuegbareFelderListe() {
        var container = document.getElementById("verfuegbare-felder-liste");
        var normaleFelder = felder.filter(function (f) { return istNormalerTyp(f.typ); });

        if (normaleFelder.length === 0) {
            container.innerHTML = '<span class="text-muted small">Zuerst Eingabefelder definieren.</span>';
            return;
        }
        var html = "";
        normaleFelder.forEach(function (f) {
            html += '<button type="button" class="btn btn-sm btn-outline-secondary me-1 mb-1" ';
            html += 'data-action="insert-feld" data-feld-id="' + esc(f.id) + '">';
            html += esc(f.label) + ' <code class="small">{{' + esc(f.id) + '}}</code>';
            html += '</button>';
        });
        container.innerHTML = html;
        // Button-Zustand sofort synchronisieren (falls Textblock bearbeitet wird)
        syncFeldButtonZustand();
    }

    function updateBerechnungFelderListe() {
        var container = document.getElementById("berechnung-felder-liste");
        var normaleFelder = felder.filter(function (f) { return istNormalerTyp(f.typ); });
        if (normaleFelder.length === 0) {
            container.innerHTML = '<span class="text-muted small">Zuerst Eingabefelder definieren.</span>';
            return;
        }
        var html = "";
        normaleFelder.forEach(function (f) {
            html += '<button type="button" class="btn btn-sm btn-outline-secondary me-1 mb-1" ';
            html += 'data-action="insert-berechnung-feld" data-feld-id="' + esc(f.id) + '">';
            html += esc(f.label) + ' <code class="small">{{' + esc(f.id) + '}}</code>';
            html += '</button>';
        });
        container.innerHTML = html;
    }

    // Deaktiviert Buttons fuer Felder die bereits im Textblock-Text stehen
    function syncFeldButtonZustand() {
        var ta = document.getElementById("feld-textblock-inhalt");
        var text = ta ? ta.value : "";
        var container = document.getElementById("verfuegbare-felder-liste");
        container.querySelectorAll("[data-action='insert-feld']").forEach(function (btn) {
            var feldId = btn.dataset.feldId;
            var bereits = text.indexOf("{{" + feldId + "}}") !== -1;
            btn.disabled = bereits;
            if (bereits) {
                btn.classList.add("disabled");
            } else {
                btn.classList.remove("disabled");
            }
        });
    }

    function oeffneModal(idx) {
        editIndex = idx;
        var feld = (idx !== null) ? felder[idx] : null;

        document.getElementById("feld-modal-titel").textContent =
            feld ? "Element bearbeiten" : "Neues Element";

        var typ = feld ? feld.typ : "text";
        document.getElementById("feld-typ").value = typ;
        document.getElementById("feld-label").value = feld && feld.label ? feld.label : "";
        document.getElementById("feld-hilfetext").value = feld && feld.hilfetext ? feld.hilfetext : "";
        document.getElementById("feld-pflicht").checked = feld ? !!feld.pflicht : false;
        document.getElementById("feld-optionen").value = (feld && feld.optionen) ? feld.optionen.join("\n") : "";
        document.getElementById("feld-textblock-inhalt").value = feld && feld.text ? feld.text : "";
        document.getElementById("feld-abschnitt-text").value = feld && feld.text ? feld.text : "";
        document.getElementById("feld-abschnitt-groesse").value = (feld && feld.groesse) ? feld.groesse : "mittel";
        document.getElementById("feld-link-text").value = (feld && feld.link_text) ? feld.link_text : "";
        document.getElementById("feld-link-url").value = (feld && feld.url) ? feld.url : "";
        document.getElementById("feld-link-newtab").checked = feld ? (feld.newtab !== false) : true;
        document.getElementById("feld-abschnitt-ausrichtung").value = (feld && feld.ausrichtung) ? feld.ausrichtung : "links";
        document.getElementById("feld-abschnitt-stil").value = (feld && feld.stil) ? feld.stil : "normal";
        var vorEl = document.getElementById("feld-vorausfuellen");
        if (vorEl) vorEl.value = (feld && feld.vorausfuellen) ? feld.vorausfuellen : "";

        var breite = feld ? (feld.breite || 100) : 100;
        document.querySelectorAll("input[name='feld-breite']").forEach(function (inp) {
            inp.checked = (parseInt(inp.value, 10) === breite);
        });

        document.getElementById("feld-id-preview").textContent =
            feld ? (feld.id || "") : labelZuId("", typ);

        // Berechnungsfeld
        document.getElementById("feld-berechnung-label").value = (feld && typ === "berechnung" && feld.label) ? feld.label : "";
        document.getElementById("feld-berechnung-id-preview").textContent = (feld && feld.id) ? feld.id : "";
        document.getElementById("feld-formel").value = (feld && feld.formel) ? feld.formel : "";
        document.getElementById("feld-einheit").value = (feld && feld.einheit) ? feld.einheit : "";
        document.getElementById("feld-dezimalstellen").value = (feld && feld.dezimalstellen !== undefined) ? String(feld.dezimalstellen) : "2";

        toggleModalFelder(typ);
        modal.show();
    }

    function speichereFeld() {
        var typ = document.getElementById("feld-typ").value;
        var breiteInput = document.querySelector("input[name='feld-breite']:checked");
        var breite = breiteInput ? parseInt(breiteInput.value, 10) : 100;

        var feld = { typ: typ, breite: breite };

        if (istNormalerTyp(typ)) {
            var label = document.getElementById("feld-label").value.trim();
            if (!label) {
                document.getElementById("feld-label").classList.add("is-invalid");
                return;
            }
            document.getElementById("feld-label").classList.remove("is-invalid");

            var hilfetext = document.getElementById("feld-hilfetext").value.trim();
            var pflicht = document.getElementById("feld-pflicht").checked;
            var optionenRaw = document.getElementById("feld-optionen").value;
            var optionen = optionenRaw.split("\n").map(function (o) { return o.trim(); }).filter(Boolean);

            // ID: beibehalten bei Bearbeitung, neu generieren bei neuem Feld
            var id;
            if (editIndex !== null) {
                id = felder[editIndex].id;
            } else {
                id = labelZuId(label, typ);
                var basis = id; var zaehler = 2;
                while (felder.some(function (f) { return f.id === id; })) {
                    id = basis + "_" + zaehler++;
                }
            }

            feld.id = id;
            feld.label = label;
            feld.pflicht = pflicht;
            if (hilfetext) feld.hilfetext = hilfetext;
            if (typ === "auswahl" || typ === "radio" || typ === "checkboxen") feld.optionen = optionen;
            var vorEl = document.getElementById("feld-vorausfuellen");
            if (vorEl && vorEl.value) feld.vorausfuellen = vorEl.value;

        } else if (typ === "textblock") {
            feld.id = editIndex !== null ? felder[editIndex].id : ("textblock_" + Date.now());
            feld.text = document.getElementById("feld-textblock-inhalt").value;

        } else if (typ === "abschnitt") {
            feld.id = editIndex !== null ? felder[editIndex].id : ("abschnitt_" + Date.now());
            feld.text = document.getElementById("feld-abschnitt-text").value.trim();
            feld.groesse = document.getElementById("feld-abschnitt-groesse").value;
            feld.ausrichtung = document.getElementById("feld-abschnitt-ausrichtung").value;
            feld.stil = document.getElementById("feld-abschnitt-stil").value;

        } else if (typ === "trennlinie") {
            feld.id = editIndex !== null ? felder[editIndex].id : ("trennlinie_" + Date.now());

        } else if (typ === "leerblock") {
            feld.id = editIndex !== null ? felder[editIndex].id : ("leerblock_" + Date.now());

        } else if (typ === "link") {
            feld.id = editIndex !== null ? felder[editIndex].id : ("link_" + Date.now());
            feld.link_text = document.getElementById("feld-link-text").value.trim();
            feld.url = document.getElementById("feld-link-url").value.trim();
            feld.newtab = document.getElementById("feld-link-newtab").checked;

        } else if (typ === "berechnung") {
            var bLabel = document.getElementById("feld-berechnung-label").value.trim();
            if (!bLabel) {
                document.getElementById("feld-berechnung-label").classList.add("is-invalid");
                return;
            }
            document.getElementById("feld-berechnung-label").classList.remove("is-invalid");
            feld.label = bLabel;
            if (editIndex !== null) {
                feld.id = felder[editIndex].id;
            } else {
                feld.id = labelZuId(bLabel, "berechnung");
                var bBasis = feld.id; var bZ = 2;
                while (felder.some(function (f) { return f.id === feld.id; })) {
                    feld.id = bBasis + "_" + bZ++;
                }
            }
            feld.formel = document.getElementById("feld-formel").value.trim();
            feld.einheit = document.getElementById("feld-einheit").value.trim();
            feld.dezimalstellen = parseInt(document.getElementById("feld-dezimalstellen").value, 10);
        }

        if (editIndex !== null) {
            felder[editIndex] = feld;
        } else {
            felder.push(feld);
        }

        renderFelderListe();
        updateVorschau();
        modal.hide();
    }

    // -----------------------------------------------------------------------
    // Feld-Liste rendern
    // -----------------------------------------------------------------------

    function renderFelderListe() {
        var container = document.getElementById("felder-liste");
        var leer = document.getElementById("felder-leer");

        if (felder.length === 0) {
            container.innerHTML = "";
            leer.style.display = "";
            return;
        }
        leer.style.display = "none";

        var inlineIds = inlineFeldIds();

        var html = '<ul class="list-group list-group-flush">';
        felder.forEach(function (feld, idx) {
            var breite = feld.breite || 100;
            var istStruktur = STRUKTUR_TYPEN.indexOf(feld.typ) !== -1;
            var istEingebettet = istNormalerTyp(feld.typ) && inlineIds[feld.id];

            html += '<li class="list-group-item px-3 py-2' + (istStruktur ? ' bg-light' : '') + '">';
            html += '<div class="d-flex justify-content-between align-items-center">';
            html += '<div style="max-width:70%">';

            if (feld.typ === "leerblock") {
                html += '<span class="text-muted small">&#9617; Leerblock (' + (BREITE_LABEL[breite] || breite + "%") + ')</span>';
            } else if (feld.typ === "link") {
                html += '<span class="badge bg-info text-dark small mb-1">Link</span> ';
                html += '<span class="small">' + esc(feld.link_text || "(kein Text)") + '</span>';
                html += '<br><code class="text-muted" style="font-size:0.7rem;">' + esc(feld.url || "") + '</code>';
            } else if (feld.typ === "trennlinie") {
                html += '<span class="text-muted small">— Trennlinie —</span>';
            } else if (feld.typ === "abschnitt") {
                html += '<span class="fw-semibold">' + esc(feld.text || "(kein Text)") + '</span>';
                html += ' <span class="badge bg-info text-dark ms-1 small">Abschnitt</span>';
            } else if (feld.typ === "textblock") {
                html += '<span class="badge bg-primary ms-1 small mb-1">Fließtext</span><br>';
                html += '<span class="small text-muted">' + esc((feld.text || "").substring(0, 80)) + (feld.text && feld.text.length > 80 ? "…" : "") + '</span>';
            } else if (feld.typ === "berechnung") {
                html += '<span class="fw-semibold">' + esc(feld.label || "") + '</span>';
                html += ' <span class="badge bg-warning text-dark ms-1 small">Formel</span>';
                if (feld.einheit) html += ' <span class="badge bg-light text-dark border ms-1 small">' + esc(feld.einheit) + '</span>';
                html += '<br><code class="text-muted" style="font-size:0.7rem;">' + esc((feld.formel || "").substring(0, 60)) + (feld.formel && feld.formel.length > 60 ? "…" : "") + '</code>';
            } else {
                html += '<span class="fw-semibold">' + esc(feld.label || "") + '</span>';
                if (feld.pflicht) html += ' <span class="text-danger small">*</span>';
                html += ' <span class="badge bg-light text-dark border ms-1 small">' + (TYP_LABEL[feld.typ] || feld.typ) + '</span>';
                html += ' <span class="badge bg-secondary ms-1 small">' + (BREITE_LABEL[breite] || breite + "%") + '</span>';
                if (istEingebettet) {
                    html += ' <span class="badge bg-info text-dark ms-1 small" title="Wird im Fließtext eingebettet, nicht als eigenstaendiges Feld angezeigt">Eingebettet</span>';
                }
                html += '<br><code class="text-muted" style="font-size:0.7rem;">' + esc(feld.id || "") + '</code>';
            }

            html += '</div>';
            html += '<div class="d-flex gap-1 flex-shrink-0">';
            html += '<button type="button" class="btn btn-sm btn-outline-secondary px-1 py-0" data-action="feld-hoch" data-index="' + idx + '" ' + (idx === 0 ? 'disabled' : '') + '>&#9650;</button>';
            html += '<button type="button" class="btn btn-sm btn-outline-secondary px-1 py-0" data-action="feld-runter" data-index="' + idx + '" ' + (idx === felder.length - 1 ? 'disabled' : '') + '>&#9660;</button>';
            html += '<button type="button" class="btn btn-sm btn-outline-primary px-2 py-0" data-action="feld-bearbeiten" data-index="' + idx + '">Bearb.</button>';
            html += '<button type="button" class="btn btn-sm btn-outline-danger px-2 py-0" data-action="feld-loeschen" data-index="' + idx + '">&#10005;</button>';
            html += '</div></div>';

            // Breiten-Balken
            if (feld.typ !== "trennlinie") {
                html += '<div class="mt-1" style="height:3px;background:#e9ecef;border-radius:2px;">';
                html += '<div style="width:' + breite + '%;height:100%;background:' + (istStruktur ? '#6c757d' : '#1a4d2e') + ';border-radius:2px;"></div>';
                html += '</div>';
            }
            html += '</li>';
        });
        html += '</ul>';
        container.innerHTML = html;
    }

    // -----------------------------------------------------------------------
    // Vorschau
    // -----------------------------------------------------------------------

    function updateVorschau() {
        var container = document.getElementById("vorschau-container");
        if (felder.length === 0) {
            container.innerHTML = '<div class="text-muted small text-center py-4">Noch keine Felder definiert.</div>';
            return;
        }

        var feldMap = buildFeldMap();
        var inlineIds = inlineFeldIds();

        var html = '<div class="border rounded p-3 bg-white"><p class="text-muted small fw-semibold mb-3 pb-2 border-bottom">Vorschau</p>';
        html += '<div class="row g-3">';

        felder.forEach(function (feld) {
            var col = breiteZuCol(feld.breite || 100);

            if (feld.typ === "leerblock") {
                html += '<div class="' + col + '"><div style="height:38px;border:1px dashed #dee2e6;border-radius:4px;background:#f8f9fa;"></div></div>';
            } else if (feld.typ === "link") {
                html += '<div class="' + col + '">';
                html += '<a href="' + esc(feld.url || "#") + '" target="' + (feld.newtab ? "_blank" : "_self") + '" class="small">';
                html += esc(feld.link_text || feld.url || "Link") + (feld.newtab ? ' &#8599;' : '');
                html += '</a></div>';
            } else if (feld.typ === "trennlinie") {
                html += '<div class="col-12"><hr class="my-1"></div>';

            } else if (feld.typ === "abschnitt") {
                html += '<div class="' + col + '">' + abschnittHtml(feld) + '</div>';

            } else if (feld.typ === "textblock") {
                html += '<div class="' + col + '">';
                html += '<p style="line-height:2.8;margin:0;">';
                html += textblockZuHtml(feld.text || "", feldMap, true);
                html += '</p></div>';

            } else if (!inlineIds[feld.id]) {
                // Normales Standalone-Feld
                html += '<div class="' + col + '">';
                html += '<label class="form-label fw-semibold small mb-1">' + esc(feld.label || "");
                if (feld.pflicht) html += ' <span class="text-danger">*</span>';
                html += '</label>';
                if (feld.typ === "radio" || feld.typ === "checkboxen") {
                    var inputTyp = feld.typ === "radio" ? "radio" : "checkbox";
                    html += '<div class="d-flex flex-column gap-1">';
                    (feld.optionen || []).forEach(function (o) {
                        html += '<div class="form-check">';
                        html += '<input class="form-check-input" type="' + inputTyp + '" disabled>';
                        html += '<label class="form-check-label small">' + esc(o) + '</label>';
                        html += '</div>';
                    });
                    html += '</div>';
                } else {
                    html += inlineInputHtml(feld, true, "w-100");
                }
                html += '</div>';
            }
        });

        html += '</div></div>';
        container.innerHTML = html;
    }

    // Textblock-Text in HTML mit Inline-Inputs umwandeln
    function textblockZuHtml(text, feldMap, disabled) {
        var parts = text.split(/\{\{(\w+)\}\}/);
        var html = "";
        parts.forEach(function (part, i) {
            if (i % 2 === 0) {
                html += esc(part);
            } else {
                var ref = feldMap[part];
                if (ref) {
                    html += inlineInputHtml(ref, disabled, "");
                } else {
                    html += '<span class="badge bg-danger">?' + esc(part) + '?</span>';
                }
            }
        });
        return html;
    }

    // Einzelnes Input-Element (inline oder standalone)
    function inlineInputHtml(feld, disabled, extraClass) {
        var d = disabled ? " disabled" : "";
        var inlineStyle = "border:none;border-bottom:2px solid #333;background:transparent;border-radius:0;padding:0 2px;display:inline-block;vertical-align:bottom;";
        var w = INLINE_BREITE[feld.typ] || 150;
        var style = extraClass ? "" : (inlineStyle + "width:" + w + "px;");
        var cls = "form-control form-control-sm " + (extraClass || "");

        if (feld.typ === "mehrzeil") {
            return '<textarea class="' + cls + '" style="' + style + '" rows="2"' + d + ' placeholder="' + esc(feld.hilfetext || "") + '"></textarea>';
        } else if (feld.typ === "auswahl") {
            var opts = '<option>— wählen —</option>';
            (feld.optionen || []).forEach(function (o) { opts += '<option>' + esc(o) + '</option>'; });
            return '<select class="form-select form-select-sm ' + extraClass + '" style="' + style + '"' + d + '>' + opts + '</select>';
        } else if (feld.typ === "radio") {
            // Kompakte Radio-Vorschau
            var rHtml = '<span class="d-inline-flex flex-wrap gap-2">';
            (feld.optionen || ["Option 1", "Option 2"]).forEach(function (o) {
                rHtml += '<span class="text-nowrap"><input type="radio"' + d + ' class="form-check-input me-1"><span class="small">' + esc(o) + '</span></span>';
            });
            return rHtml + '</span>';
        } else if (feld.typ === "checkboxen") {
            // Kompakte Checkbox-Vorschau
            var cHtml = '<span class="d-inline-flex flex-wrap gap-2">';
            (feld.optionen || ["Option 1", "Option 2"]).forEach(function (o) {
                cHtml += '<span class="text-nowrap"><input type="checkbox"' + d + ' class="form-check-input me-1"><span class="small">' + esc(o) + '</span></span>';
            });
            return cHtml + '</span>';
        } else if (feld.typ === "bool") {
            return '<input type="checkbox" class="form-check-input"' + d + '>';
        } else if (feld.typ === "email") {
            return '<input type="email" class="' + cls + '" style="' + style + '"' + d + ' placeholder="' + esc(feld.hilfetext || "name@beispiel.de") + '">';
        } else if (feld.typ === "iban") {
            return '<input type="text" class="' + cls + '" style="' + style + (extraClass ? "" : "width:220px;") + '"' + d + ' placeholder="DE00 0000 0000 0000 0000 00" maxlength="34">';
        } else if (feld.typ === "datum") {
            return '<input type="date" class="' + cls + '" style="' + style + '"' + d + '>';
        } else if (feld.typ === "uhrzeit") {
            return '<input type="text" class="' + cls + '" style="' + style + (extraClass ? "" : "width:90px;") + '"' + d + ' placeholder="HH:MM">';
        } else if (feld.typ === "berechnung") {
            var einheit = feld.einheit ? " " + esc(feld.einheit) : "";
            return '<span class="badge bg-secondary font-monospace">=Formel' + einheit + '</span>';
        } else if (feld.typ === "zahl") {
            return '<input type="number" class="' + cls + '" style="' + style + '"' + d + ' placeholder="' + esc(feld.hilfetext || "") + '">';
        } else {
            return '<input type="text" class="' + cls + '" style="' + style + '"' + d + ' placeholder="' + esc(feld.hilfetext || "") + '">';
        }
    }

    // Abschnitt-HTML generieren (Groesse, Ausrichtung, Stil)
    function abschnittHtml(feld) {
        var groesse = feld.groesse || "mittel";
        var ausrichtung = feld.ausrichtung || "links";
        var stil = feld.stil || "normal";

        var tag = groesse === "gross" ? "h4" : (groesse === "mittel" ? "h6" : "p");
        var textAlign = ausrichtung === "mitte" ? "center" : (ausrichtung === "rechts" ? "right" : "left");
        var fontWeight = (stil === "fett" || stil === "fett-kursiv") ? "bold" : "normal";
        var fontStyle = (stil === "kursiv" || stil === "fett-kursiv") ? "italic" : "normal";
        var color = groesse === "klein" ? "#6c757d" : "#1a4d2e";
        var borderBottom = groesse !== "klein" ? "border-bottom: 1px solid #dee2e6; padding-bottom: 4px;" : "";

        return '<' + tag + ' style="text-align:' + textAlign + ';font-weight:' + fontWeight +
               ';font-style:' + fontStyle + ';color:' + color + ';' + borderBottom + 'margin-bottom:0;">' +
               esc(feld.text || "") + '</' + tag + '>';
    }

    // -----------------------------------------------------------------------
    // Baustein-Modal
    // -----------------------------------------------------------------------

    function oeffneBausteinModal() {
        if (!bausteinModal) return;
        var body = document.getElementById("baustein-modal-body");
        body.innerHTML = '<div class="text-center text-muted py-3">Lade Bausteine\u2026</div>';
        bausteinModal.show();

        // URL aus data-Attribut oder Pfad ableiten
        var url = "/prozesse/bausteine/json/";
        fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (r) { return r.json(); })
            .then(function (data) { renderBausteinListe(data.bausteine || []); })
            .catch(function () {
                body.innerHTML = '<div class="text-danger small p-3">Fehler beim Laden der Bausteine.</div>';
            });
    }

    function renderBausteinListe(bausteine) {
        var body = document.getElementById("baustein-modal-body");
        if (bausteine.length === 0) {
            body.innerHTML = '<div class="text-muted small p-3">Noch keine Bausteine vorhanden. '
                + '<a href="/prozesse/bausteine/neu/" target="_blank">Ersten Baustein erstellen &rarr;</a></div>';
            return;
        }
        var html = '<div class="list-group list-group-flush">';
        bausteine.forEach(function (b) {
            html += '<button type="button" class="list-group-item list-group-item-action py-2 px-3" '
                + 'data-action="baustein-einfuegen" data-baustein-id="' + esc(String(b.id)) + '">';
            html += '<div class="d-flex justify-content-between align-items-start">';
            html += '<div>';
            html += '<div class="fw-semibold">' + esc(b.name) + '</div>';
            if (b.beschreibung) {
                html += '<div class="text-muted small">' + esc(b.beschreibung) + '</div>';
            }
            html += '<div class="mt-1">';
            (b.felder || []).forEach(function (f) {
                html += '<span class="badge bg-light text-dark border me-1 small">' + esc(f.label) + '</span>';
            });
            html += '</div>';
            html += '</div>';
            html += '<span class="badge bg-secondary ms-2 flex-shrink-0">' + (b.anzahl_felder || 0) + ' Felder</span>';
            html += '</div></button>';
        });
        html += '</div>';
        body.innerHTML = html;

        // Klick-Handler
        body.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-action='baustein-einfuegen']");
            if (!btn) return;
            var id = parseInt(btn.dataset.bausteinId, 10);
            var baustein = bausteine.find(function (b) { return b.id === id; });
            if (baustein) {
                fuegeBasusteinEin(baustein);
                bausteinModal.hide();
            }
        });
    }

    function fuegeBasusteinEin(baustein) {
        var neueFelder = baustein.felder || [];
        neueFelder.forEach(function (f) {
            // Kopie erstellen
            var kopie = JSON.parse(JSON.stringify(f));
            // ID deduplizieren falls bereits vorhanden
            var basis = kopie.id; var zaehler = 2;
            while (felder.some(function (x) { return x.id === kopie.id; })) {
                kopie.id = basis + "_" + zaehler++;
            }
            felder.push(kopie);
        });
        renderFelderListe();
        updateVorschau();
    }

    // XSS-Schutz
    function esc(str) {
        return String(str)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;")
            .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

})();
