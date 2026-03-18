// Synapse-Raum-Erstellen-Button: ruft API auf und befüllt room_id + room_alias
document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("btn-synapse-erstellen");
    if (!btn) return;

    var urlEl = document.getElementById("synapse-raum-erstellen-url");
    var apiUrl = JSON.parse(urlEl.textContent);

    var csrfToken = document.querySelector("meta[name='csrf-token']").content;

    btn.addEventListener("click", function () {
        var name = document.querySelector("input[name='name']").value.trim();
        if (!name) {
            zeigeFehler("Bitte zuerst einen Namen eingeben.");
            return;
        }

        // Alias aus dem Namen ableiten (Kleinbuchstaben, Leerzeichen -> Bindestrich)
        var alias = name.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9\-]/g, "");

        btn.disabled = true;
        btn.textContent = "Wird erstellt...";
        versteckeFehler();

        var formData = new FormData();
        formData.append("name", name);
        formData.append("alias", alias);

        fetch(apiUrl, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken },
            body: formData,
        })
        .then(function (resp) { return resp.json(); })
        .then(function (data) {
            if (data.fehler) {
                zeigeFehler(data.fehler);
                return;
            }
            document.getElementById("id_room_id").value = data.room_id || "";
            document.getElementById("id_room_alias").value = data.room_alias || "";
            btn.textContent = "Erstellt";
            btn.classList.replace("btn-outline-primary", "btn-success");
        })
        .catch(function () {
            zeigeFehler("Netzwerkfehler – Synapse erreichbar?");
        })
        .finally(function () {
            btn.disabled = false;
        });
    });

    function zeigeFehler(msg) {
        var el = document.getElementById("synapse-fehler");
        el.textContent = msg;
        el.classList.remove("d-none");
    }

    function versteckeFehler() {
        document.getElementById("synapse-fehler").classList.add("d-none");
    }
});
