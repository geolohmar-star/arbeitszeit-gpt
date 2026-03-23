/**
 * workflow_regel_form.js
 * Steuert das Formular fuer Paperless-Workflow-Regeln:
 * - Zeigt/versteckt Felder je nach Treffer-Typ
 * - Live-Tester: Regex gegen Testtext pruefen (clientseitig)
 * - Regex-Ableiter: generiert Muster aus Beispiel-Strings
 */
document.addEventListener("DOMContentLoaded", function () {

    var select       = document.getElementById("id_treffer_typ");
    var zeileName    = document.getElementById("zeile-paperless-name");
    var zeileMuster  = document.getElementById("zeile-muster");
    var hinweisName  = document.getElementById("hinweis-paperless");
    var hinweisMust  = document.getElementById("hinweis-muster");

    // ---------------------------------------------------------------
    // Felder ein-/ausblenden je nach Treffer-Typ
    // ---------------------------------------------------------------
    function aktualisiereFelder() {
        var typ = select ? select.value : "";
        var istMuster = typ === "muster";

        if (zeileName)   zeileName.style.display   = istMuster ? "none" : "";
        if (zeileMuster) zeileMuster.style.display  = istMuster ? "" : "none";
        if (hinweisName) hinweisName.style.display  = istMuster ? "none" : "";
        if (hinweisMust) hinweisMust.style.display  = istMuster ? "" : "none";
    }

    if (select) {
        select.addEventListener("change", aktualisiereFelder);
        aktualisiereFelder(); // Initialzustand
    }

    // ---------------------------------------------------------------
    // Live-Tester: "Testen"-Button oeffnet Testtext-Box
    // ---------------------------------------------------------------
    var btnTesten    = document.getElementById("btn-muster-testen");
    var testerBox    = document.getElementById("muster-tester-box");
    var testText     = document.getElementById("muster-testtext");
    var testErgebnis = document.getElementById("muster-test-ergebnis");
    var regexInput   = document.getElementById("id_muster_regex");

    if (btnTesten) {
        btnTesten.addEventListener("click", function () {
            if (!testerBox) return;
            testerBox.style.display = testerBox.style.display === "none" ? "" : "none";
        });
    }

    // Regex-Test ausfuehren sobald Text oder Regex sich aendert
    function fuehreTestAus() {
        if (!testErgebnis || !regexInput || !testText) return;
        if (!testerBox || testerBox.style.display === "none") return;

        var muster = (regexInput.value || "").trim();
        var text   = testText.value;

        if (!muster) {
            testErgebnis.innerHTML = "<span class='text-muted'>Kein Muster eingegeben.</span>";
            return;
        }

        try {
            var re = new RegExp(muster, "g");
            var treffer = [];
            var m;
            while ((m = re.exec(text)) !== null) {
                treffer.push(escapeHtml(m[0]));
                // Schutz vor unendlicher Schleife bei Zero-Length-Match
                if (m[0].length === 0) { re.lastIndex++; }
                if (treffer.length >= 20) break;
            }
            if (treffer.length > 0) {
                testErgebnis.innerHTML =
                    "<span class='text-success fw-semibold'>" + treffer.length + " Treffer:</span> " +
                    treffer.map(function (t) { return "<code>" + t + "</code>"; }).join("  ");
            } else {
                testErgebnis.innerHTML = "<span class='text-warning'>Kein Treffer im Text.</span>";
            }
        } catch (e) {
            testErgebnis.innerHTML = "<span class='text-danger'>Ungueltige Regex: " + escapeHtml(e.message) + "</span>";
        }
    }

    if (regexInput) { regexInput.addEventListener("input", fuehreTestAus); }
    if (testText)   { testText.addEventListener("input", fuehreTestAus); }

    // ---------------------------------------------------------------
    // Regex-Ableiter: Muster aus Beispiel-Strings generieren
    // ---------------------------------------------------------------
    var btnAbleiten   = document.getElementById("btn-muster-ableiten");
    var beispielArea  = document.getElementById("muster-beispiele");
    var ableitErgebnis = document.getElementById("muster-ableiten-ergebnis");

    if (btnAbleiten) {
        btnAbleiten.addEventListener("click", function () {
            if (!beispielArea || !ableitErgebnis) return;

            var zeilen = beispielArea.value.split("\n")
                .map(function (z) { return z.trim(); })
                .filter(function (z) { return z.length > 0; });

            if (zeilen.length === 0) {
                ableitErgebnis.style.display = "";
                ableitErgebnis.innerHTML = "<span class='text-muted'>Bitte mindestens einen Beispiel-String eingeben.</span>";
                return;
            }

            var muster = leiteMusterAb(zeilen);
            ableitErgebnis.style.display = "";
            ableitErgebnis.innerHTML =
                "<strong>Abgeleitetes Muster:</strong> <code id='abgeleitetes-muster'>" +
                escapeHtml(muster) + "</code>" +
                " <button type='button' class='btn btn-xs btn-outline-secondary ms-2' " +
                "style='font-size:0.72rem;padding:1px 8px;' id='btn-muster-uebernehmen'>" +
                "Uebernehmen</button>";

            var btnUebernehmen = document.getElementById("btn-muster-uebernehmen");
            if (btnUebernehmen && regexInput) {
                btnUebernehmen.addEventListener("click", function () {
                    regexInput.value = muster;
                    fuehreTestAus();
                });
            }
        });
    }

    // ---------------------------------------------------------------
    // Kern: Regex aus Beispiel-Liste ableiten
    // Strategie: Zeichenklassen-Segmente bestimmen, Laengen-Range angeben
    // ---------------------------------------------------------------
    function leiteMusterAb(beispiele) {
        // Jeden String in Segmente zerlegen: Trennzeichen vs. Zeichenklasse
        var segmente = beispiele.map(zerlege);

        // Laengsten gemeinsamen Strukturpfad finden
        var maxLen = segmente.reduce(function (mx, s) { return Math.max(mx, s.length); }, 0);

        var ergebnis = [];
        for (var i = 0; i < maxLen; i++) {
            var teile = segmente
                .filter(function (s) { return i < s.length; })
                .map(function (s) { return s[i]; });

            if (teile.length === 0) break;

            // Alle Typen in dieser Position sammeln
            var typen = {};
            teile.forEach(function (t) { typen[t.typ] = true; });

            var laengen = teile.map(function (t) { return t.len; });
            var minLen  = Math.min.apply(null, laengen);
            var maxL    = Math.max.apply(null, laengen);

            if (typen["trenner"]) {
                // Trennzeichen – nimm den haeufigsten
                var haeufig = haeufigsterWert(teile.map(function (t) { return t.val; }));
                ergebnis.push(escapeRegex(haeufig));
            } else if (typen["gross"] && !typen["ziffer"] && !typen["klein"]) {
                ergebnis.push(laengenKlasse("[A-Z]", minLen, maxL));
            } else if (typen["klein"] && !typen["ziffer"] && !typen["gross"]) {
                ergebnis.push(laengenKlasse("[a-z]", minLen, maxL));
            } else if (typen["ziffer"] && !typen["gross"] && !typen["klein"]) {
                ergebnis.push(laengenKlasse("\\d", minLen, maxL));
            } else if ((typen["gross"] || typen["klein"]) && !typen["ziffer"]) {
                ergebnis.push(laengenKlasse("[A-Za-z]", minLen, maxL));
            } else if (typen["ziffer"] && (typen["gross"] || typen["klein"])) {
                ergebnis.push(laengenKlasse("[A-Z0-9]", minLen, maxL));
            } else {
                // Gemischt – generische Wortgruppe
                ergebnis.push(laengenKlasse("\\w", minLen, maxL));
            }
        }

        return ergebnis.join("");
    }

    /**
     * Zerlegt einen String in Segmente:
     * [{typ: "gross"|"klein"|"ziffer"|"trenner", len: N, val: "..."}]
     * Trennzeichen sind alle Nicht-Alphanumerics.
     */
    function zerlege(str) {
        var segs = [];
        var i = 0;
        while (i < str.length) {
            var c = str[i];
            var typ = zeichenTyp(c);

            if (typ === "trenner") {
                segs.push({ typ: "trenner", len: 1, val: c });
                i++;
            } else {
                // Aufeinander folgende gleiche Klasse zusammenfassen
                var start = i;
                while (i < str.length && zeichenTyp(str[i]) === typ) { i++; }
                segs.push({ typ: typ, len: i - start, val: str.slice(start, i) });
            }
        }
        return segs;
    }

    function zeichenTyp(c) {
        if (c >= "A" && c <= "Z") return "gross";
        if (c >= "a" && c <= "z") return "klein";
        if (c >= "0" && c <= "9") return "ziffer";
        return "trenner";
    }

    function laengenKlasse(klasse, min, max) {
        if (min === max) {
            if (min === 1) return klasse;
            return klasse + "{" + min + "}";
        }
        return klasse + "{" + min + "," + max + "}";
    }

    function escapeRegex(s) {
        return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }

    function haeufigsterWert(arr) {
        var z = {};
        var best = arr[0];
        var bestN = 0;
        arr.forEach(function (v) {
            z[v] = (z[v] || 0) + 1;
            if (z[v] > bestN) { bestN = z[v]; best = v; }
        });
        return best;
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }

});
