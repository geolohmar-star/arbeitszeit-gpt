// Hilfe-Modal: Tab-Wechsel via data-hilfe-tab Attribut (CSP-sicher, kein onclick)
document.addEventListener("DOMContentLoaded", function () {
    document.body.addEventListener("click", function (e) {
        var btn = e.target.closest("[data-hilfe-tab]");
        if (!btn) return;
        var tabId = btn.dataset.hilfeTab;
        var tabEl = document.getElementById(tabId);
        if (!tabEl) return;
        // Bootstrap Tab-API direkt aufrufen (kein data-bs-toggle auf Pane-Button noetig)
        bootstrap.Tab.getOrCreateInstance(tabEl).show();
    });
});
