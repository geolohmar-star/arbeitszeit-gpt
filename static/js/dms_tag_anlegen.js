/**
 * DMS – Inline-Tag-Anlegen
 * CSP-konform: kein Inline-JS, alle Events per addEventListener
 */

document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("tag-anlegen-btn");
    var panel = document.getElementById("tag-anlegen-panel");
    var abbrechen = document.getElementById("tag-anlegen-abbrechen");
    var speichern = document.getElementById("tag-anlegen-speichern");
    var nameInput = document.getElementById("tag-neu-name");
    var farbeInput = document.getElementById("tag-neu-farbe");
    var fehlerDiv = document.getElementById("tag-anlegen-fehler");
    var tagSelect = document.getElementById("id_tags");

    if (!btn) return;

    btn.addEventListener("click", function () {
        panel.style.display = "block";
        btn.style.display = "none";
        nameInput.focus();
    });

    abbrechen.addEventListener("click", function () {
        panel.style.display = "none";
        btn.style.display = "inline-block";
        nameInput.value = "";
        farbeInput.value = "#6c757d";
        fehlerDiv.textContent = "";
        fehlerDiv.style.display = "none";
    });

    speichern.addEventListener("click", function () {
        var name = nameInput.value.trim();
        if (!name) {
            fehlerDiv.textContent = "Name darf nicht leer sein.";
            fehlerDiv.style.display = "block";
            nameInput.focus();
            return;
        }

        var csrfInput = document.querySelector("[name=csrfmiddlewaretoken]");
        var csrf = csrfInput ? csrfInput.value : "";

        var url = btn.dataset.url;
        var formData = new FormData();
        formData.append("name", name);
        formData.append("farbe", farbeInput.value);

        speichern.disabled = true;
        speichern.textContent = "...";

        fetch(url, {
            method: "POST",
            headers: { "X-CSRFToken": csrf },
            body: formData,
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            speichern.disabled = false;
            speichern.textContent = "Anlegen";

            if (!data.ok) {
                fehlerDiv.textContent = data.fehler || "Fehler beim Anlegen.";
                fehlerDiv.style.display = "block";
                return;
            }

            // Option in Select einfuegen (falls nicht vorhanden)
            var vorhanden = false;
            for (var i = 0; i < tagSelect.options.length; i++) {
                if (parseInt(tagSelect.options[i].value) === data.id) {
                    vorhanden = true;
                    tagSelect.options[i].selected = true;
                    break;
                }
            }
            if (!vorhanden) {
                var opt = document.createElement("option");
                opt.value = data.id;
                opt.textContent = data.name;
                opt.selected = true;
                // Farbiges Label als data-Attribut speichern (optional fuer spaeteren Badge)
                opt.dataset.farbe = data.farbe;
                // Alphabetisch einsortieren
                var eingefuegt = false;
                for (var j = 0; j < tagSelect.options.length; j++) {
                    if (tagSelect.options[j].textContent.localeCompare(data.name) > 0) {
                        tagSelect.insertBefore(opt, tagSelect.options[j]);
                        eingefuegt = true;
                        break;
                    }
                }
                if (!eingefuegt) {
                    tagSelect.appendChild(opt);
                }
            }

            // Badge-Vorschau aktualisieren
            vorschauAktualisieren();

            // Panel schliessen
            panel.style.display = "none";
            btn.style.display = "inline-block";
            nameInput.value = "";
            farbeInput.value = "#6c757d";
            fehlerDiv.style.display = "none";

            var hinweis = data.neu
                ? "Tag \"" + data.name + "\" angelegt und ausgewaehlt."
                : "Tag \"" + data.name + "\" bereits vorhanden – ausgewaehlt.";
            var toast = document.getElementById("tag-toast-text");
            if (toast) {
                toast.textContent = hinweis;
                document.getElementById("tag-toast").style.display = "block";
                setTimeout(function () {
                    document.getElementById("tag-toast").style.display = "none";
                }, 3000);
            }
        })
        .catch(function () {
            speichern.disabled = false;
            speichern.textContent = "Anlegen";
            fehlerDiv.textContent = "Netzwerkfehler.";
            fehlerDiv.style.display = "block";
        });
    });

    // Enter im Namensfeld loest Speichern aus
    nameInput.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
            e.preventDefault();
            speichern.click();
        }
    });

    // Ausgewaehlte Tags als Badges anzeigen
    tagSelect.addEventListener("change", vorschauAktualisieren);

    function vorschauAktualisieren() {
        var container = document.getElementById("tag-vorschau");
        if (!container) return;
        container.innerHTML = "";
        for (var i = 0; i < tagSelect.options.length; i++) {
            var opt = tagSelect.options[i];
            if (opt.selected) {
                var farbe = opt.dataset.farbe || "#6c757d";
                var badge = document.createElement("span");
                badge.className = "badge me-1";
                badge.style.background = farbe;
                badge.style.color = "#fff";
                badge.textContent = opt.textContent;
                container.appendChild(badge);
            }
        }
    }

    // Initiale Vorschau aufbauen (bei Edit-Seiten mit vorausgewaehlten Tags)
    vorschauAktualisieren();
});
