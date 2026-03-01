// formulare.js – Vanilla JS für die formulare-App

// Stunden/Minuten-Felder bei Minus-Auswahl rot einfaerben
function vorzeichen_farbe_aktualisieren() {
    var minus = document.getElementById("vorzeichen_minus");
    if (!minus) return;
    var stunden = document.querySelector("[name='mehrarbeit_stunden']");
    var minuten = document.querySelector("[name='mehrarbeit_minuten']");
    if (!stunden || !minuten) return;

    if (minus.checked) {
        stunden.classList.add("border-danger", "text-danger");
        minuten.classList.add("border-danger", "text-danger");
    } else {
        stunden.classList.remove("border-danger", "text-danger");
        minuten.classList.remove("border-danger", "text-danger");
    }
}

// Nach HTMX-Swap: Listener neu setzen und Farbe pruefen
document.addEventListener("htmx:afterSwap", function () {
    var plus  = document.getElementById("vorzeichen_plus");
    var minus = document.getElementById("vorzeichen_minus");
    if (plus)  plus.addEventListener("change", vorzeichen_farbe_aktualisieren);
    if (minus) minus.addEventListener("change", vorzeichen_farbe_aktualisieren);
    vorzeichen_farbe_aktualisieren();
});

document.addEventListener("DOMContentLoaded", function () {

    // Kopieren in Zwischenablage via data-clipboard-text Attribut
    document.querySelectorAll("[data-clipboard-text]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var text = this.dataset.clipboardText;
            var original = this.textContent;
            navigator.clipboard.writeText(text).then(function () {
                btn.textContent = "Kopiert!";
                btn.classList.add("btn-success");
                btn.classList.remove("btn-outline-secondary");
                setTimeout(function () {
                    btn.textContent = original;
                    btn.classList.remove("btn-success");
                    btn.classList.add("btn-outline-secondary");
                }, 2000);
            });
        });
    });

});
