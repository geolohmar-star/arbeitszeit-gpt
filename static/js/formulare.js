// formulare.js – Vanilla JS für die formulare-App

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
