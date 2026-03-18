/**
 * Laufzettel-Builder – dynamische Schritt-Tabelle mit Stelle-Autocomplete
 * CSP-konform: kein Inline-JS, alle Event-Handler per addEventListener
 */

var AKTION_KUERZEL = {
    pruefen: "PR",
    genehmigen: "GEN",
    bearbeiten: "BE",
    informieren: "KEN",
    entscheiden: "ENT"
};

var STELLE_AUTOCOMPLETE_URL = "/dms/api/stellen/";
var LAUFZETTEL_VORLAGEN_URL = "/dms/api/laufzettel-vorlagen/";
var LAUFZETTEL_STARTEN_URL = null;
var dokId = null;
var zeilenZaehler = 0;

document.addEventListener("DOMContentLoaded", function () {
    // Konfiguration aus json_script-Element lesen (falls vorhanden)
    var cfgEl = document.getElementById("laufzettel-config");
    if (cfgEl) {
        var cfg = JSON.parse(cfgEl.textContent);
        if (cfg.stelle_url)   STELLE_AUTOCOMPLETE_URL  = cfg.stelle_url;
        if (cfg.vorlagen_url) LAUFZETTEL_VORLAGEN_URL  = cfg.vorlagen_url;
        if (cfg.starten_url)  LAUFZETTEL_STARTEN_URL   = cfg.starten_url;
    }
    dokId = JSON.parse(document.getElementById("laufzettel-dok-id").textContent);

    // Erste Zeile beim Laden
    zeilenHinzufuegen();

    document.getElementById("laufzettel-zeile-hinzufuegen")
        .addEventListener("click", zeilenHinzufuegen);

    document.getElementById("laufzettel-starten-btn")
        .addEventListener("click", laufzettelStarten);

    document.getElementById("laufzettel-als-vorlage")
        .addEventListener("change", function () {
            document.getElementById("vorlage-name-container").style.display =
                this.checked ? "block" : "none";
        });

    // Vorlagen laden wenn Tab gewechselt wird (nur wenn Tab vorhanden)
    var tabVorlagen = document.querySelector("[data-bs-target='#tab-vorlagen']");
    var tabLaufzettel = document.querySelector("[data-bs-target='#tab-laufzettel']");
    var footer = document.getElementById("laufzettel-footer");

    if (tabVorlagen) {
        tabVorlagen.addEventListener("shown.bs.tab", vorlagenLaden);
        if (footer) {
            tabVorlagen.addEventListener("shown.bs.tab", function () {
                footer.style.display = "none";
            });
        }
    }
    if (tabLaufzettel && footer) {
        tabLaufzettel.addEventListener("shown.bs.tab", function () {
            footer.style.display = "flex";
        });
    }
});

function zeilenHinzufuegen() {
    zeilenZaehler++;
    var tbody = document.getElementById("laufzettel-zeilen");
    var nr = tbody.rows.length + 1;
    var tr = document.createElement("tr");
    tr.dataset.zeile = zeilenZaehler;

    tr.innerHTML =
        "<td class='text-muted small'>" + nr + "</td>" +
        "<td>" +
            "<div class='position-relative'>" +
                "<input type='text' class='form-control form-control-sm stelle-input'" +
                "       placeholder='Kürzel oder Name eingeben...'" +
                "       autocomplete='off' data-zeile='" + zeilenZaehler + "'>" +
                "<input type='hidden' class='stelle-id-input'>" +
                "<div class='stelle-dropdown list-group position-absolute w-100'" +
                "     style='z-index:1055; display:none; max-height:200px; overflow-y:auto;'>" +
                "</div>" +
            "</div>" +
        "</td>" +
        "<td>" +
            "<select class='form-select form-select-sm aktion-select'>" +
                "<option value='pruefen'>Prüfen</option>" +
                "<option value='genehmigen'>Genehmigen</option>" +
                "<option value='bearbeiten'>Bearbeiten</option>" +
                "<option value='informieren'>Zur Kenntnisnahme</option>" +
                "<option value='entscheiden'>Entscheiden</option>" +
            "</select>" +
        "</td>" +
        "<td>" +
            "<button type='button' class='btn btn-sm btn-outline-danger zeile-loeschen'" +
            "        data-zeile='" + zeilenZaehler + "'>×</button>" +
        "</td>";

    tbody.appendChild(tr);

    // Events verdrahten
    tr.querySelector(".stelle-input").addEventListener("input", stelleEingabe);
    tr.querySelector(".stelle-input").addEventListener("blur", autocompleteSchliessen);
    tr.querySelector(".aktion-select").addEventListener("change", autoNameAktualisieren);
    tr.querySelector(".zeile-loeschen").addEventListener("click", zeileLoeschen);

    nummerierungAktualisieren();
    autoNameAktualisieren();
}

function stelleEingabe(e) {
    var input = e.target;
    var q = input.value.trim();
    var dropdown = input.closest("div").querySelector(".stelle-dropdown");

    if (q.length < 1) {
        dropdown.style.display = "none";
        return;
    }

    fetch(STELLE_AUTOCOMPLETE_URL + "?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (daten) {
            dropdown.innerHTML = "";
            if (!daten.stellen.length) {
                dropdown.innerHTML = "<div class='list-group-item list-group-item-action disabled small'>Keine Treffer</div>";
                dropdown.style.display = "block";
                return;
            }
            daten.stellen.forEach(function (s) {
                var btn = document.createElement("button");
                btn.type = "button";
                btn.className = "list-group-item list-group-item-action small py-1";
                btn.innerHTML =
                    "<span class='fw-bold font-monospace'>" + s.kuerzel + "</span>" +
                    " – " + s.bezeichnung +
                    (s.org ? " <span class='text-muted'>(" + s.org + ")</span>" : "");
                btn.addEventListener("mousedown", function (ev) {
                    ev.preventDefault();
                    input.value = s.kuerzel;
                    input.closest("div").querySelector(".stelle-id-input").value = s.id;
                    input.dataset.kuerzel = s.kuerzel;
                    dropdown.style.display = "none";
                    autoNameAktualisieren();
                });
                dropdown.appendChild(btn);
            });
            dropdown.style.display = "block";
        });
}

function autocompleteSchliessen() {
    setTimeout(function () {
        document.querySelectorAll(".stelle-dropdown").forEach(function (d) {
            d.style.display = "none";
        });
    }, 150);
}

function zeileLoeschen(e) {
    var zeile = e.target.dataset.zeile;
    var tr = document.querySelector("tr[data-zeile='" + zeile + "']");
    if (tr) {
        tr.remove();
        nummerierungAktualisieren();
        autoNameAktualisieren();
    }
}

function nummerierungAktualisieren() {
    var zeilen = document.querySelectorAll("#laufzettel-zeilen tr");
    zeilen.forEach(function (tr, i) {
        tr.cells[0].textContent = i + 1;
    });
}

function autoNameAktualisieren() {
    var zeilen = document.querySelectorAll("#laufzettel-zeilen tr");
    var teile = [];
    zeilen.forEach(function (tr) {
        var kuerzel = tr.querySelector(".stelle-input").dataset.kuerzel || "";
        var aktion = tr.querySelector(".aktion-select").value;
        if (kuerzel) {
            teile.push(kuerzel + ":" + (AKTION_KUERZEL[aktion] || aktion.toUpperCase().substr(0, 3)));
        }
    });
    var container = document.getElementById("laufzettel-autoname");
    if (teile.length) {
        container.textContent = teile.join(" → ");
        container.classList.remove("text-muted");
        container.classList.add("text-dark");
    } else {
        container.textContent = "– noch keine Schritte –";
        container.classList.add("text-muted");
        container.classList.remove("text-dark");
    }
}

function laufzettelStarten() {
    var fehlerDiv = document.getElementById("laufzettel-fehler");
    fehlerDiv.classList.add("d-none");

    var zeilen = document.querySelectorAll("#laufzettel-zeilen tr");
    var schritte = [];
    var ok = true;

    zeilen.forEach(function (tr) {
        var stelleId = tr.querySelector(".stelle-id-input").value;
        var aktion = tr.querySelector(".aktion-select").value;
        if (!stelleId) {
            ok = false;
            return;
        }
        schritte.push({ stelle_id: parseInt(stelleId), aktion: aktion });
    });

    if (!ok || !schritte.length) {
        fehlerDiv.textContent = "Bitte für jeden Schritt eine gültige Stelle auswählen.";
        fehlerDiv.classList.remove("d-none");
        return;
    }

    var ablageId = document.getElementById("laufzettel-ablage").value;
    var alsVorlage = document.getElementById("laufzettel-als-vorlage").checked;
    var vorlageName = document.getElementById("laufzettel-vorlage-name").value.trim();

    var payload = {
        steps: schritte,
        ablage_kategorie_id: ablageId ? parseInt(ablageId) : null,
        vorlage_name: alsVorlage ? vorlageName : ""
    };

    var csrfToken = document.querySelector("[name=csrfmiddlewaretoken]");
    var csrf = csrfToken ? csrfToken.value :
        document.querySelector("meta[name='csrf-token']").content;

    var btn = document.getElementById("laufzettel-starten-btn");
    btn.disabled = true;
    btn.textContent = "Starten...";

    var startenUrl = LAUFZETTEL_STARTEN_URL || ("/dms/" + dokId + "/laufzettel/starten/");
    fetch(startenUrl, {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": csrf
        },
        body: JSON.stringify(payload)
    })
    .then(function (r) { return r.json(); })
    .then(function (daten) {
        if (daten.ok) {
            window.location.href = daten.redirect;
        } else {
            fehlerDiv.textContent = daten.fehler || "Unbekannter Fehler.";
            fehlerDiv.classList.remove("d-none");
            btn.disabled = false;
            btn.textContent = "Laufzettel starten";
        }
    })
    .catch(function () {
        fehlerDiv.textContent = "Netzwerkfehler – bitte Seite neu laden.";
        fehlerDiv.classList.remove("d-none");
        btn.disabled = false;
        btn.textContent = "Laufzettel starten";
    });
}

function vorlagenLaden() {
    var container = document.getElementById("laufzettel-vorlagen-liste");
    container.innerHTML = "<div class='text-muted small'>Lade Vorlagen...</div>";

    fetch(LAUFZETTEL_VORLAGEN_URL)
        .then(function (r) { return r.json(); })
        .then(function (daten) {
            if (!daten.vorlagen.length) {
                container.innerHTML = "<p class='text-muted small'>Noch keine gespeicherten Laufzettel-Vorlagen.</p>";
                return;
            }
            var html = "<p class='small fw-bold mb-2'>Gespeicherte Laufzettel-Vorlagen:</p><div class='list-group mb-3'>";
            daten.vorlagen.forEach(function (v) {
                var kette = v.steps.map(function (s) {
                    return s.kuerzel + ":" + (AKTION_KUERZEL[s.aktion] || s.aktion.toUpperCase().substr(0, 3));
                }).join(" → ");
                html +=
                    "<button type='button' class='list-group-item list-group-item-action py-2 vorlage-laden-btn'" +
                    "        data-vorlage='" + JSON.stringify(v).replace(/'/g, "&#39;") + "'>" +
                    "  <div class='fw-semibold'>" + v.name + "</div>" +
                    "  <div class='small font-monospace text-muted'>" + kette + "</div>" +
                    "</button>";
            });
            html += "</div>";
            container.innerHTML = html;

            container.querySelectorAll(".vorlage-laden-btn").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    var vorlage = JSON.parse(this.dataset.vorlage);
                    vorlageLaden(vorlage);
                    // Zum Laufzettel-Tab wechseln
                    var laufzettelTab = document.querySelector("[data-bs-target='#tab-laufzettel']");
                    bootstrap.Tab.getOrCreateInstance(laufzettelTab).show();
                });
            });
        });
}

function vorlageLaden(vorlage) {
    // Bestehende Zeilen entfernen
    document.getElementById("laufzettel-zeilen").innerHTML = "";
    zeilenZaehler = 0;

    // Zeilen aus Vorlage laden
    vorlage.steps.forEach(function (schritt) {
        zeilenZaehler++;
        var tbody = document.getElementById("laufzettel-zeilen");
        var nr = tbody.rows.length + 1;
        var tr = document.createElement("tr");
        tr.dataset.zeile = zeilenZaehler;

        tr.innerHTML =
            "<td class='text-muted small'>" + nr + "</td>" +
            "<td>" +
                "<div class='position-relative'>" +
                    "<input type='text' class='form-control form-control-sm stelle-input'" +
                    "       value='" + schritt.kuerzel + "'" +
                    "       data-kuerzel='" + schritt.kuerzel + "'" +
                    "       autocomplete='off' data-zeile='" + zeilenZaehler + "'>" +
                    "<input type='hidden' class='stelle-id-input' value='" + schritt.stelle_id + "'>" +
                    "<div class='stelle-dropdown list-group position-absolute w-100'" +
                    "     style='z-index:1055; display:none; max-height:200px; overflow-y:auto;'>" +
                    "</div>" +
                "</div>" +
            "</td>" +
            "<td>" +
                "<select class='form-select form-select-sm aktion-select'>" +
                    "<option value='pruefen'" + (schritt.aktion === "pruefen" ? " selected" : "") + ">Prüfen</option>" +
                    "<option value='genehmigen'" + (schritt.aktion === "genehmigen" ? " selected" : "") + ">Genehmigen</option>" +
                    "<option value='bearbeiten'" + (schritt.aktion === "bearbeiten" ? " selected" : "") + ">Bearbeiten</option>" +
                    "<option value='informieren'" + (schritt.aktion === "informieren" ? " selected" : "") + ">Zur Kenntnisnahme</option>" +
                    "<option value='entscheiden'" + (schritt.aktion === "entscheiden" ? " selected" : "") + ">Entscheiden</option>" +
                "</select>" +
            "</td>" +
            "<td>" +
                "<button type='button' class='btn btn-sm btn-outline-danger zeile-loeschen'" +
                "        data-zeile='" + zeilenZaehler + "'>×</button>" +
            "</td>";

        tbody.appendChild(tr);
        tr.querySelector(".stelle-input").addEventListener("input", stelleEingabe);
        tr.querySelector(".stelle-input").addEventListener("blur", autocompleteSchliessen);
        tr.querySelector(".aktion-select").addEventListener("change", autoNameAktualisieren);
        tr.querySelector(".zeile-loeschen").addEventListener("click", zeileLoeschen);
    });

    autoNameAktualisieren();
    // Vorlagen-Namen vorbelegen
    document.getElementById("laufzettel-als-vorlage").checked = false;
    document.getElementById("laufzettel-vorlage-name").value = vorlage.name;
}
