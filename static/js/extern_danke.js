/**
 * extern_danke.js – Vorgangsnummer-Kopieren auf der Danke-Seite
 */
document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("btn-kopieren");
    var meldung = document.getElementById("kopiert-meldung");
    var text = document.getElementById("vorgangsnummer-text");
    if (!btn || !text) return;

    btn.addEventListener("click", function () {
        var nummer = text.textContent.trim();
        if (navigator.clipboard) {
            navigator.clipboard.writeText(nummer).then(function () {
                if (meldung) { meldung.style.display = ""; }
                setTimeout(function () { if (meldung) meldung.style.display = "none"; }, 2000);
            });
        }
    });
});
