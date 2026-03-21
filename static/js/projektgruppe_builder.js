/**
 * Projektgruppen-Builder
 * Verwaltet CRUD fuer Projektgruppen und deren Mitglieder.
 */
(function () {
    "use strict";

    var mitarbeiterListe = [];

    // CSRF-Token aus Meta-Tag lesen
    function getCsrf() {
        var m = document.querySelector("meta[name='csrf-token']");
        return m ? m.content : "";
    }

    function api(url, body) {
        return fetch(url, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrf(),
            },
            body: JSON.stringify(body),
        }).then(function (r) { return r.json(); });
    }

    function zeigeModal(html) {
        document.getElementById("modal-content").innerHTML = html;
        document.getElementById("modal-overlay").style.display = "block";
    }

    function schliesseModal() {
        document.getElementById("modal-overlay").style.display = "none";
        document.getElementById("modal-content").innerHTML = "";
    }

    function reload() {
        location.reload();
    }

    // ------------------------------------------------------------------
    // Mitarbeiter-Optionen fuer Select-Felder
    // ------------------------------------------------------------------
    function maOptionen(ausgewaehlteId) {
        return mitarbeiterListe.map(function (ma) {
            var sel = String(ma.id) === String(ausgewaehlteId) ? " selected" : "";
            var info = ma.stelle ? " – " + ma.stelle : "";
            return "<option value=\"" + ma.id + "\"" + sel + ">" + ma.vollname + info + "</option>";
        }).join("");
    }

    // ------------------------------------------------------------------
    // Formular: Neue / Bestehende Projektgruppe
    // ------------------------------------------------------------------
    function projektFormHTML(proj) {
        var istNeu = !proj;
        var titel = istNeu ? "Neue Projektgruppe" : "Projektgruppe bearbeiten";
        var btnText = istNeu ? "Anlegen" : "Speichern";
        var p = proj || {};

        var statusOptionen = [
            ["aktiv", "Aktiv"],
            ["pausiert", "Pausiert"],
            ["abgeschlossen", "Abgeschlossen"],
            ["abgebrochen", "Abgebrochen"],
        ].map(function (s) {
            var sel = p.status === s[0] ? " selected" : "";
            return "<option value=\"" + s[0] + "\"" + sel + ">" + s[1] + "</option>";
        }).join("");

        return "<div class=\"modal-header bg-primary text-white\">"
            + "<h5 class=\"modal-title\">" + titel + "</h5>"
            + "<button type=\"button\" class=\"btn-close btn-close-white\" id=\"btn-modal-schliessen\"></button>"
            + "</div>"
            + "<div class=\"modal-body\">"
            + "<div id=\"form-fehler\" class=\"alert alert-danger d-none\"></div>"
            + "<div class=\"row g-3\">"
            + "<div class=\"col-md-8\">"
            + "<label class=\"form-label\">Projektname *</label>"
            + "<input type=\"text\" class=\"form-control\" id=\"f-name\" value=\"" + (p.name || "") + "\" required>"
            + "</div>"
            + "<div class=\"col-md-4\">"
            + "<label class=\"form-label\">Kuerzel *</label>"
            + "<input type=\"text\" class=\"form-control\" id=\"f-kuerzel\" value=\"" + (p.kuerzel || "") + "\""
            + (istNeu ? "" : " readonly") + " required maxlength=\"20\" style=\"text-transform:uppercase\">"
            + "</div>"
            + "<div class=\"col-12\">"
            + "<label class=\"form-label\">Beschreibung</label>"
            + "<textarea class=\"form-control\" id=\"f-beschreibung\" rows=\"2\">" + (p.beschreibung || "") + "</textarea>"
            + "</div>"
            + "<div class=\"col-md-6\">"
            + "<label class=\"form-label\">Startdatum *</label>"
            + "<input type=\"date\" class=\"form-control\" id=\"f-start\" value=\"" + (p.start_datum || "") + "\" required>"
            + "</div>"
            + "<div class=\"col-md-6\">"
            + "<label class=\"form-label\">Enddatum (geplant)</label>"
            + "<input type=\"date\" class=\"form-control\" id=\"f-ende\" value=\"" + (p.end_datum || "") + "\">"
            + "</div>"
            + "<div class=\"col-md-6\">"
            + "<label class=\"form-label\">Projektleiter/in *</label>"
            + "<select class=\"form-select\" id=\"f-leiter\"><option value=\"\">– bitte waehlen –</option>"
            + maOptionen(p.leiter_id) + "</select>"
            + "</div>"
            + "<div class=\"col-md-6\">"
            + "<label class=\"form-label\">Stellvertretung</label>"
            + "<select class=\"form-select\" id=\"f-stv\"><option value=\"\">– keine –</option>"
            + maOptionen(p.stellvertreter_id) + "</select>"
            + "</div>"
            + "<div class=\"col-md-6\">"
            + "<label class=\"form-label\">Status</label>"
            + "<select class=\"form-select\" id=\"f-status\">" + statusOptionen + "</select>"
            + "</div>"
            + "<div class=\"col-md-6\">"
            + "<label class=\"form-label\">Prioritaet (1=hoch, 10=niedrig)</label>"
            + "<input type=\"number\" class=\"form-control\" id=\"f-prioritaet\" min=\"1\" max=\"10\" value=\"" + (p.prioritaet || 5) + "\">"
            + "</div>"
            + "</div>"
            + "</div>"
            + "<div class=\"modal-footer\">"
            + "<button class=\"btn btn-secondary\" id=\"btn-modal-schliessen2\">Abbrechen</button>"
            + "<button class=\"btn btn-primary\" id=\"btn-form-speichern\" data-id=\"" + (p.id || "") + "\">" + btnText + "</button>"
            + "</div>";
    }

    function oeffneNeuForm() {
        zeigeModal(projektFormHTML(null));
        verdrahteFormHandlers(null);
    }

    function oeffneBearbeitenForm(id) {
        fetch("/hr/projektgruppen/" + id + "/")
            .then(function (r) { return r.json(); })
            .then(function (proj) {
                zeigeModal(projektFormHTML(proj));
                verdrahteFormHandlers(id);
            });
    }

    function verdrahteFormHandlers(projektId) {
        document.getElementById("btn-modal-schliessen").addEventListener("click", schliesseModal);
        document.getElementById("btn-modal-schliessen2").addEventListener("click", schliesseModal);

        document.getElementById("btn-form-speichern").addEventListener("click", function () {
            var name = document.getElementById("f-name").value.trim();
            var kuerzel = document.getElementById("f-kuerzel").value.trim().toUpperCase();
            var beschreibung = document.getElementById("f-beschreibung").value.trim();
            var startDatum = document.getElementById("f-start").value;
            var endDatum = document.getElementById("f-ende").value;
            var leiterId = document.getElementById("f-leiter").value;
            var stvId = document.getElementById("f-stv").value;
            var status = document.getElementById("f-status").value;
            var prioritaet = document.getElementById("f-prioritaet").value;

            var payload = {
                name: name,
                kuerzel: kuerzel,
                beschreibung: beschreibung,
                start_datum: startDatum,
                end_datum: endDatum,
                leiter_id: leiterId,
                stellvertreter_id: stvId,
                status: status,
                prioritaet: prioritaet,
            };

            var url = projektId
                ? "/hr/projektgruppen/" + projektId + "/bearbeiten/"
                : "/hr/projektgruppen/neu/";

            api(url, payload).then(function (data) {
                if (data.error) {
                    var box = document.getElementById("form-fehler");
                    box.textContent = data.error;
                    box.classList.remove("d-none");
                } else {
                    reload();
                }
            });
        });
    }

    // ------------------------------------------------------------------
    // Mitglied hinzufuegen
    // ------------------------------------------------------------------
    function oeffneMitgliedForm(projektId, projektName) {
        var optionen = mitarbeiterListe.map(function (ma) {
            var info = ma.stelle ? " – " + ma.stelle : "";
            return "<option value=\"" + ma.id + "\">" + ma.vollname + info + "</option>";
        }).join("");

        var html = "<div class=\"modal-header bg-success text-white\">"
            + "<h5 class=\"modal-title\">Mitglied hinzufuegen – " + projektName + "</h5>"
            + "<button type=\"button\" class=\"btn-close btn-close-white\" id=\"btn-modal-schliessen\"></button>"
            + "</div>"
            + "<div class=\"modal-body\">"
            + "<div id=\"form-fehler\" class=\"alert alert-danger d-none\"></div>"
            + "<label class=\"form-label\">Mitarbeiter/in</label>"
            + "<select class=\"form-select\" id=\"f-ma-select\"><option value=\"\">– bitte waehlen –</option>"
            + optionen + "</select>"
            + "</div>"
            + "<div class=\"modal-footer\">"
            + "<button class=\"btn btn-secondary\" id=\"btn-modal-schliessen2\">Abbrechen</button>"
            + "<button class=\"btn btn-success\" id=\"btn-mitglied-hinzufuegen\">Hinzufuegen</button>"
            + "</div>";

        zeigeModal(html);

        document.getElementById("btn-modal-schliessen").addEventListener("click", schliesseModal);
        document.getElementById("btn-modal-schliessen2").addEventListener("click", schliesseModal);
        document.getElementById("btn-mitglied-hinzufuegen").addEventListener("click", function () {
            var maId = document.getElementById("f-ma-select").value;
            if (!maId) { return; }
            api("/hr/projektgruppen/" + projektId + "/mitglied-hinzufuegen/", { ma_id: maId })
                .then(function (data) {
                    if (data.error) {
                        var box = document.getElementById("form-fehler");
                        box.textContent = data.error;
                        box.classList.remove("d-none");
                    } else {
                        reload();
                    }
                });
        });
    }

    // ------------------------------------------------------------------
    // Event-Delegation
    // ------------------------------------------------------------------
    document.addEventListener("DOMContentLoaded", function () {
        // Mitarbeiterliste aus json_script laden
        var raw = document.getElementById("mitarbeiter-data");
        if (raw) {
            mitarbeiterListe = JSON.parse(raw.textContent);
        }

        // Neue Projektgruppe
        document.getElementById("btn-neu").addEventListener("click", oeffneNeuForm);

        // Alle Button-Aktionen per Delegation
        document.body.addEventListener("click", function (e) {
            var btn = e.target.closest("[data-action]");
            if (!btn) { return; }
            var action = btn.dataset.action;

            if (action === "edit-projekt") {
                oeffneBearbeitenForm(btn.dataset.id);

            } else if (action === "delete-projekt") {
                if (!confirm("Projektgruppe \"" + btn.dataset.name + "\" wirklich loeschen?")) { return; }
                api("/hr/projektgruppen/" + btn.dataset.id + "/loeschen/", {})
                    .then(function (data) {
                        if (data.error) {
                            alert("Fehler: " + data.error);
                        } else {
                            reload();
                        }
                    });

            } else if (action === "add-member") {
                oeffneMitgliedForm(btn.dataset.projektId, btn.dataset.projektName);

            } else if (action === "remove-member") {
                if (!confirm(btn.dataset.name + " aus Projekt entfernen?")) { return; }
                api("/hr/projektgruppen/" + btn.dataset.projektId + "/mitglied-entfernen/", { ma_id: btn.dataset.maId })
                    .then(function (data) {
                        if (data.error) {
                            alert("Fehler: " + data.error);
                        } else {
                            reload();
                        }
                    });
            }
        });

        // Klick ausserhalb Modal schliesst es
        document.getElementById("modal-overlay").addEventListener("click", function (e) {
            if (e.target === this) { schliesseModal(); }
        });
    });
}());
