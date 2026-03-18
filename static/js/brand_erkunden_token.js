/**
 * brand_erkunden_token.js
 * Interaktionen auf der Branderkunder-Rueckmeldeseite.
 */
document.addEventListener("DOMContentLoaded", function () {

    // Lage-Buttons: data-notiz ins versteckte Feld schreiben
    var lageBtns = document.querySelectorAll(".btn-lage");
    var lageNotizFeld = document.getElementById("id-lage-notiz");
    lageBtns.forEach(function (btn) {
        btn.addEventListener("click", function () {
            lageNotizFeld.value = btn.dataset.notiz || "";
        });
    });

    // Freitext: Senden-Button erst anzeigen wenn etwas getippt wird
    var notizFeld = document.getElementById("id-notiz");
    var btnNachricht = document.getElementById("btn-nachricht");
    if (notizFeld && btnNachricht) {
        notizFeld.addEventListener("input", function () {
            btnNachricht.style.display = notizFeld.value.trim() ? "" : "none";
        });
    }
});
