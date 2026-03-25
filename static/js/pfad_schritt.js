// pfad_schritt.js – Berechnungsfelder und Textblock-Variablen im Antrags-Player

document.addEventListener("DOMContentLoaded", function () {
    // Gesammelte Daten aus vorherigen Schritten (vom Server als JSON eingebettet)
    var gesammelteDaten = {};
    var gesammelteEl = document.getElementById("gesammelte-daten");
    if (gesammelteEl) {
        try { gesammelteDaten = JSON.parse(gesammelteEl.textContent); } catch (e) {}
    }

    // ---------------------------------------------------------------------------
    // Berechnungsfelder
    // ---------------------------------------------------------------------------

    function feldWerteAktuell() {
        // Alle Eingabewerte der aktuellen Seite sammeln
        var werte = Object.assign({}, gesammelteDaten);
        var form = document.querySelector("form");
        if (!form) return werte;
        var inputs = form.querySelectorAll("input, select, textarea");
        inputs.forEach(function (el) {
            if (!el.name || el.dataset.berechnungId) return;
            if (el.type === "checkbox") {
                if (el.checked) werte[el.name] = el.value || "1";
            } else if (el.type === "radio") {
                if (el.checked) werte[el.name] = el.value;
            } else {
                werte[el.name] = el.value;
            }
        });
        return werte;
    }

    function berechneFormel(formel, werte) {
        try {
            // {{feld_id}} durch Wert ersetzen
            var ausdruck = formel.replace(/\{\{(\w+)\}\}/g, function (_, id) {
                var v = werte[id];
                if (v === undefined || v === "") return "0";
                var n = parseFloat(String(v).replace(",", "."));
                return isNaN(n) ? "0" : String(n);
            });
            // Nur Zahlen und Operatoren erlaubt
            if (!/^[\d\s\.\+\-\*\/\(\)]+$/.test(ausdruck)) return null;
            // eslint-disable-next-line no-new-func
            var ergebnis = Function('"use strict"; return (' + ausdruck + ')')();
            if (!isFinite(ergebnis)) return null;
            return Math.round(ergebnis * 100) / 100;
        } catch (e) {
            return null;
        }
    }

    function aktualisiereBerechnung() {
        var werte = feldWerteAktuell();
        document.querySelectorAll("[data-berechnung-id]").forEach(function (anzeige) {
            var id = anzeige.dataset.berechnungId;
            var formel = anzeige.dataset.formel;
            if (!formel) return;
            var ergebnis = berechneFormel(formel, werte);
            if (ergebnis !== null) {
                anzeige.value = ergebnis;
                var hidden = document.getElementById("berechnung-hidden-" + id);
                if (hidden) hidden.value = ergebnis;
            } else {
                anzeige.value = "";
            }
        });
    }

    // Bei jeder Aenderung neu berechnen
    var form = document.querySelector("form");
    if (form) {
        form.addEventListener("input", aktualisiereBerechnung);
        form.addEventListener("change", aktualisiereBerechnung);
        aktualisiereBerechnung(); // Initialberechnung
    }

    // ---------------------------------------------------------------------------
    // Textblock-Variablen ersetzen
    // ---------------------------------------------------------------------------

    document.querySelectorAll("[id^='textblock-']").forEach(function (el) {
        var text = el.textContent;
        text = text.replace(/\{\{(\w+)\}\}/g, function (_, id) {
            return gesammelteDaten[id] !== undefined ? gesammelteDaten[id] : "…";
        });
        el.textContent = text;
    });

    // ---------------------------------------------------------------------------
    // Wiederholungsgruppen (1+n Eintraege – HTML wird per JS aus JSON gebaut)
    // ---------------------------------------------------------------------------

    // Schritt-Felder aus JSON laden (enthaelt gruppe.unterfelder)
    var schrittFelder = {};
    var schrittFelderEl = document.getElementById("schritt-felder");
    if (schrittFelderEl) {
        try {
            JSON.parse(schrittFelderEl.textContent).forEach(function (f) {
                schrittFelder[f.id] = f;
            });
        } catch (e) {}
    }

    function escHtml(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

    function bauEintragHtml(gruppeId, idx, unterfelder, singular) {
        var felderHtml = "";
        unterfelder.forEach(function (uf) {
            var ufId   = uf.id  || "";
            var ufTyp  = uf.typ || "text";
            var lbl    = escHtml(uf.label || "");
            var pfl    = uf.pflicht ? ' <span class="text-danger">*</span>' : "";
            var name   = gruppeId + "__" + idx + "__" + ufId;
            var elId   = "f-" + gruppeId + "-" + idx + "-" + ufId;
            var inner  = "";

            if (ufTyp === "bool") {
                inner = '<div class="form-check mt-2">' +
                    '<input class="form-check-input" type="checkbox" name="' + name + '" id="' + elId + '" value="1">' +
                    '<label class="form-check-label small" for="' + elId + '">' + lbl + pfl + '</label></div>';
            } else if (ufTyp === "mehrzeil") {
                inner = '<label class="form-label small fw-semibold mb-1">' + lbl + pfl + '</label>' +
                    '<textarea class="form-control form-control-sm" rows="2" name="' + name + '"></textarea>';
            } else if (ufTyp === "datum") {
                inner = '<label class="form-label small fw-semibold mb-1">' + lbl + pfl + '</label>' +
                    '<input type="date" class="form-control form-control-sm" name="' + name + '">';
            } else if (ufTyp === "zahl") {
                inner = '<label class="form-label small fw-semibold mb-1">' + lbl + pfl + '</label>' +
                    '<input type="number" step="any" class="form-control form-control-sm" name="' + name + '">';
            } else if (ufTyp === "uhrzeit") {
                inner = '<label class="form-label small fw-semibold mb-1">' + lbl + pfl + '</label>' +
                    '<input type="text" class="form-control form-control-sm" placeholder="14:30" maxlength="5" name="' + name + '">';
            } else if (ufTyp === "auswahl") {
                var opts = '<option value="">— bitte wählen —</option>';
                (uf.optionen || []).forEach(function (o) {
                    opts += '<option value="' + escHtml(o) + '">' + escHtml(o) + '</option>';
                });
                inner = '<label class="form-label small fw-semibold mb-1">' + lbl + pfl + '</label>' +
                    '<select class="form-select form-select-sm" name="' + name + '">' + opts + '</select>';
            } else if (ufTyp === "radio" || ufTyp === "checkboxen") {
                var typ2 = ufTyp === "radio" ? "radio" : "checkbox";
                var items = "";
                (uf.optionen || []).forEach(function (o, i) {
                    var oId = elId + "-" + i;
                    items += '<div class="form-check"><input class="form-check-input" type="' + typ2 + '" name="' + name +
                        '" id="' + oId + '" value="' + escHtml(o) + '">' +
                        '<label class="form-check-label small" for="' + oId + '">' + escHtml(o) + '</label></div>';
                });
                inner = '<label class="form-label small fw-semibold mb-1">' + lbl + pfl + '</label>' + items;
            } else {
                inner = '<label class="form-label small fw-semibold mb-1">' + lbl + pfl + '</label>' +
                    '<input type="text" class="form-control form-control-sm" name="' + name + '">';
            }
            felderHtml += '<div class="col-md-6">' + inner + '</div>';
        });

        return '<div class="card mb-2 gruppe-eintrag">' +
            '<div class="card-body py-2 px-3">' +
            '<div class="d-flex justify-content-between align-items-center mb-2">' +
            '<small class="fw-semibold text-muted gruppe-eintrag-titel">' +
            escHtml(singular) + ' ' + (idx + 1) + '</small>' +
            '<button type="button" class="btn btn-sm btn-outline-danger py-0 px-2" ' +
            'style="font-size:0.75rem;" data-gruppe-remove="' + gruppeId + '">&#10005; Entfernen</button>' +
            '</div><div class="row g-2">' + felderHtml + '</div></div></div>';
    }

    function reindexGruppe(gruppeId, container, singular, unterfelder) {
        var eintraege = container.querySelectorAll(".gruppe-eintrag");
        eintraege.forEach(function (entry, newIdx) {
            entry.querySelectorAll("[name]").forEach(function (el) {
                el.name = el.name.replace(
                    new RegExp(gruppeId + "__\\d+__"),
                    gruppeId + "__" + newIdx + "__"
                );
            });
            entry.querySelectorAll("[id]").forEach(function (el) {
                el.id = el.id.replace(
                    new RegExp("f-" + gruppeId + "-\\d+-"),
                    "f-" + gruppeId + "-" + newIdx + "-"
                );
            });
            entry.querySelectorAll("[for]").forEach(function (el) {
                el.htmlFor = el.htmlFor.replace(
                    new RegExp("f-" + gruppeId + "-\\d+-"),
                    "f-" + gruppeId + "-" + newIdx + "-"
                );
            });
            var titelEl = entry.querySelector(".gruppe-eintrag-titel");
            if (titelEl) titelEl.textContent = singular + " " + (newIdx + 1);
        });
        var countInput = document.getElementById("gruppe-count-" + gruppeId);
        if (countInput) countInput.value = eintraege.length;
    }

    function gruppeEintragHinzufuegen(gruppeId) {
        var singular   = (document.querySelector("[data-gruppe-add='" + gruppeId + "']") || {}).dataset.singular || "Eintrag";
        var container  = document.getElementById("gruppe-eintraege-" + gruppeId);
        var countInput = document.getElementById("gruppe-count-" + gruppeId);
        if (!container || !countInput) return;
        var unterfelder = (schrittFelder[gruppeId] && schrittFelder[gruppeId].unterfelder) || [];
        var idx = parseInt(countInput.value) || 0;
        container.insertAdjacentHTML("beforeend", bauEintragHtml(gruppeId, idx, unterfelder, singular));
        countInput.value = idx + 1;
    }

    // Direkte Listener auf alle statischen Hinzufuegen-Buttons (kein Event Delegation)
    document.querySelectorAll("[data-gruppe-add]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            e.stopImmediatePropagation();
            gruppeEintragHinzufuegen(btn.dataset.gruppeAdd);
        });
    });

    // Event Delegation nur fuer dynamisch erzeugte Entfernen-Buttons
    document.body.addEventListener("click", function (e) {
        var removeBtn = e.target.closest("[data-gruppe-remove]");
        if (removeBtn) {
            var gruppeId2    = removeBtn.dataset.gruppeRemove;
            var eintrag      = removeBtn.closest(".gruppe-eintrag");
            var container2   = document.getElementById("gruppe-eintraege-" + gruppeId2);
            var addBtnRef    = document.querySelector("[data-gruppe-add='" + gruppeId2 + "']");
            var singular2    = addBtnRef ? addBtnRef.dataset.singular : "Eintrag";
            var unterfelder2 = (schrittFelder[gruppeId2] && schrittFelder[gruppeId2].unterfelder) || [];
            if (eintrag && container2) {
                eintrag.remove();
                reindexGruppe(gruppeId2, container2, singular2, unterfelder2);
            }
        }
    });

    // ---------------------------------------------------------------------------
    // Signatur-Pad (Handschrift-Canvas)
    // ---------------------------------------------------------------------------

    document.querySelectorAll("[data-sig-id]").forEach(function (canvas) {
        var id = canvas.dataset.sigId;
        var hidden = document.getElementById("sig-input-" + id);
        var ctx = canvas.getContext("2d");
        var zeichnet = false;
        var letzterX = 0, letzterY = 0;

        ctx.strokeStyle = "#1a1a1a";
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";

        function pos(e) {
            var r = canvas.getBoundingClientRect();
            var scaleX = canvas.width / r.width;
            var scaleY = canvas.height / r.height;
            var src = e.touches ? e.touches[0] : e;
            return {
                x: (src.clientX - r.left) * scaleX,
                y: (src.clientY - r.top) * scaleY
            };
        }

        function startZeichnen(e) {
            e.preventDefault();
            zeichnet = true;
            var p = pos(e);
            letzterX = p.x;
            letzterY = p.y;
            ctx.beginPath();
            ctx.arc(p.x, p.y, 1, 0, Math.PI * 2);
            ctx.fillStyle = "#1a1a1a";
            ctx.fill();
        }

        function weiterZeichnen(e) {
            if (!zeichnet) return;
            e.preventDefault();
            var p = pos(e);
            ctx.beginPath();
            ctx.moveTo(letzterX, letzterY);
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
            letzterX = p.x;
            letzterY = p.y;
        }

        function stopZeichnen(e) {
            if (!zeichnet) return;
            zeichnet = false;
            // PNG als base64 in Hidden-Input schreiben
            if (hidden) hidden.value = canvas.toDataURL("image/png");
        }

        canvas.addEventListener("mousedown", startZeichnen);
        canvas.addEventListener("mousemove", weiterZeichnen);
        canvas.addEventListener("mouseup", stopZeichnen);
        canvas.addEventListener("mouseleave", stopZeichnen);
        canvas.addEventListener("touchstart", startZeichnen, { passive: false });
        canvas.addEventListener("touchmove", weiterZeichnen, { passive: false });
        canvas.addEventListener("touchend", stopZeichnen);

        // Loeschen-Button
        var clearBtn = document.querySelector("[data-sig-clear='" + id + "']");
        if (clearBtn) {
            clearBtn.addEventListener("click", function () {
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                if (hidden) hidden.value = "";
            });
        }
    });
});
