/**
 * formular_ausfuellen.js – Live-Berechnung fuer Berechnungsfelder im Formular.
 *
 * CSP-konform: kein eval(), kein new Function().
 * Unterstuetzt: + - * / ( )  Vergleich: == != > < >= <=
 * Funktionen: WENN  RUNDEN  ABS  MIN  MAX  TAGE  STUNDEN  MINUTEN  HEUTE
 */
(function () {
    "use strict";

    // -----------------------------------------------------------------------
    // Tokenizer
    // -----------------------------------------------------------------------

    var TOKEN = {
        NUM: "NUM", STR: "STR", NAME: "NAME",
        PLUS: "+", MINUS: "-", MUL: "*", DIV: "/",
        LPAREN: "(", RPAREN: ")", COMMA: ",",
        EQ: "==", NEQ: "!=", GTE: ">=", LTE: "<=", GT: ">", LT: "<",
        EOF: "EOF"
    };

    function tokenisiere(input) {
        var tokens = [];
        var i = 0;
        while (i < input.length) {
            var c = input[i];

            // Leerzeichen
            if (c === " " || c === "\t" || c === "\n") { i++; continue; }

            // Zahl
            if (c >= "0" && c <= "9" || (c === "." && input[i + 1] >= "0" && input[i + 1] <= "9")) {
                var start = i;
                while (i < input.length && (input[i] >= "0" && input[i] <= "9" || input[i] === ".")) i++;
                tokens.push({ typ: TOKEN.NUM, wert: parseFloat(input.slice(start, i)) });
                continue;
            }

            // String (einfache oder doppelte Anfuehrungszeichen)
            if (c === '"' || c === "'") {
                var quote = c; i++;
                var sb = "";
                while (i < input.length && input[i] !== quote) { sb += input[i++]; }
                i++; // schliessende Anfuehrung
                tokens.push({ typ: TOKEN.STR, wert: sb });
                continue;
            }

            // Name / Funktionsname
            if ((c >= "a" && c <= "z") || (c >= "A" && c <= "Z") || c === "_") {
                var ns = i;
                while (i < input.length && /[\w]/.test(input[i])) i++;
                tokens.push({ typ: TOKEN.NAME, wert: input.slice(ns, i) });
                continue;
            }

            // Zwei-Zeichen-Operatoren
            var two = input.slice(i, i + 2);
            if (two === "==") { tokens.push({ typ: TOKEN.EQ }); i += 2; continue; }
            if (two === "!=") { tokens.push({ typ: TOKEN.NEQ }); i += 2; continue; }
            if (two === ">=") { tokens.push({ typ: TOKEN.GTE }); i += 2; continue; }
            if (two === "<=") { tokens.push({ typ: TOKEN.LTE }); i += 2; continue; }

            // Ein-Zeichen-Operatoren
            var einz = { "+": TOKEN.PLUS, "-": TOKEN.MINUS, "*": TOKEN.MUL, "/": TOKEN.DIV,
                          "(": TOKEN.LPAREN, ")": TOKEN.RPAREN, ",": TOKEN.COMMA,
                          ">": TOKEN.GT, "<": TOKEN.LT };
            if (einz[c]) { tokens.push({ typ: einz[c] }); i++; continue; }

            throw new Error("Unbekanntes Zeichen: " + c);
        }
        tokens.push({ typ: TOKEN.EOF });
        return tokens;
    }

    // -----------------------------------------------------------------------
    // Parser + Evaluator (Recursive Descent)
    // -----------------------------------------------------------------------

    function parse(tokens, feldWerte) {
        var pos = 0;

        function peek() { return tokens[pos]; }
        function consume() { return tokens[pos++]; }
        function expect(typ) {
            var t = consume();
            if (t.typ !== typ) throw new Error("Erwartet " + typ + ", erhalten " + t.typ);
            return t;
        }

        function parseExpr() { return parseVergleich(); }

        function parseVergleich() {
            var left = parseAddSub();
            var t = peek();
            if (t.typ === TOKEN.EQ || t.typ === TOKEN.NEQ ||
                t.typ === TOKEN.GT || t.typ === TOKEN.LT ||
                t.typ === TOKEN.GTE || t.typ === TOKEN.LTE) {
                consume();
                var right = parseAddSub();
                if (t.typ === TOKEN.EQ) return left == right ? 1 : 0;   // == (Wert-Vergleich)
                if (t.typ === TOKEN.NEQ) return left != right ? 1 : 0;
                var l = parseFloat(left), r = parseFloat(right);
                if (t.typ === TOKEN.GT) return l > r ? 1 : 0;
                if (t.typ === TOKEN.LT) return l < r ? 1 : 0;
                if (t.typ === TOKEN.GTE) return l >= r ? 1 : 0;
                if (t.typ === TOKEN.LTE) return l <= r ? 1 : 0;
            }
            return left;
        }

        function parseAddSub() {
            var left = parseMulDiv();
            while (peek().typ === TOKEN.PLUS || peek().typ === TOKEN.MINUS) {
                var op = consume().typ;
                var right = parseMulDiv();
                left = op === TOKEN.PLUS ? parseFloat(left) + parseFloat(right)
                                         : parseFloat(left) - parseFloat(right);
            }
            return left;
        }

        function parseMulDiv() {
            var left = parseUnary();
            while (peek().typ === TOKEN.MUL || peek().typ === TOKEN.DIV) {
                var op = consume().typ;
                var right = parseUnary();
                if (op === TOKEN.MUL) {
                    left = parseFloat(left) * parseFloat(right);
                } else {
                    var r = parseFloat(right);
                    if (r === 0) throw new Error("Division durch Null");
                    left = parseFloat(left) / r;
                }
            }
            return left;
        }

        function parseUnary() {
            if (peek().typ === TOKEN.MINUS) { consume(); return -parseFloat(parsePrimary()); }
            return parsePrimary();
        }

        function parsePrimary() {
            var t = peek();

            // Zahl
            if (t.typ === TOKEN.NUM) { consume(); return t.wert; }

            // String
            if (t.typ === TOKEN.STR) { consume(); return t.wert; }

            // Klammer
            if (t.typ === TOKEN.LPAREN) {
                consume();
                var v = parseExpr();
                expect(TOKEN.RPAREN);
                return v;
            }

            // Name: Feldvariable oder Funktion
            if (t.typ === TOKEN.NAME) {
                consume();
                var name = t.wert.toUpperCase();

                // Funktionsaufruf
                if (peek().typ === TOKEN.LPAREN) {
                    expect(TOKEN.LPAREN);
                    var args = [];
                    if (peek().typ !== TOKEN.RPAREN) {
                        args.push(parseExpr());
                        while (peek().typ === TOKEN.COMMA) { consume(); args.push(parseExpr()); }
                    }
                    expect(TOKEN.RPAREN);
                    return evalFunktion(name, args);
                }

                // Feld-Variable (Prefix _F_ wurde beim Vorbereiten gesetzt)
                var feldKey = "_F_" + t.wert;
                if (feldWerte.hasOwnProperty(feldKey)) {
                    var val = feldWerte[feldKey];
                    var num = parseFloat(String(val).replace(",", "."));
                    return isNaN(num) ? (val || "") : num;
                }
                throw new Error("Unbekanntes Feld: " + t.wert);
            }

            throw new Error("Unerwartetes Token: " + t.typ);
        }

        function evalFunktion(name, args) {
            if (name === "WENN") {
                if (args.length !== 3) throw new Error("WENN: 3 Argumente erwartet");
                return args[0] ? args[1] : args[2];
            }
            if (name === "RUNDEN") {
                if (args.length !== 2) throw new Error("RUNDEN: 2 Argumente erwartet");
                return parseFloat(parseFloat(args[0]).toFixed(parseInt(args[1])));
            }
            if (name === "ABS") { return Math.abs(parseFloat(args[0])); }
            if (name === "MIN") { return Math.min.apply(null, args.map(parseFloat)); }
            if (name === "MAX") { return Math.max.apply(null, args.map(parseFloat)); }
            if (name === "HEUTE") {
                var h = new Date();
                return h.getFullYear() + "-" + _pad(h.getMonth() + 1) + "-" + _pad(h.getDate());
            }
            if (name === "TAGE") {
                if (args.length !== 2) throw new Error("TAGE: 2 Argumente erwartet");
                var d1 = _parseDatum(String(args[0]));
                var d2 = _parseDatum(String(args[1]));
                return Math.round((d2 - d1) / 86400000);
            }
            if (name === "STUNDEN") {
                if (args.length !== 2) throw new Error("STUNDEN: 2 Argumente erwartet");
                var m1 = _parseZeitMinuten(String(args[0]));
                var m2 = _parseZeitMinuten(String(args[1]));
                var diff = m2 - m1;
                if (diff < 0) diff += 24 * 60;
                return Math.round(diff / 60 * 10000) / 10000;
            }
            if (name === "MINUTEN") {
                if (args.length !== 2) throw new Error("MINUTEN: 2 Argumente erwartet");
                var mm1 = _parseZeitMinuten(String(args[0]));
                var mm2 = _parseZeitMinuten(String(args[1]));
                var mdiff = mm2 - mm1;
                if (mdiff < 0) mdiff += 24 * 60;
                return mdiff;
            }
            throw new Error("Unbekannte Funktion: " + name);
        }

        return parseExpr();
    }

    // -----------------------------------------------------------------------
    // Hilfsfunktionen
    // -----------------------------------------------------------------------

    function _pad(n) { return n < 10 ? "0" + n : String(n); }

    function _parseDatum(s) {
        s = s.trim();
        // YYYY-MM-DD
        var m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
        if (m) return new Date(parseInt(m[1]), parseInt(m[2]) - 1, parseInt(m[3]));
        throw new Error("Kein gueltiges Datum: " + s);
    }

    function _parseZeitMinuten(s) {
        s = s.trim();
        // HH:MM oder HHMM
        if (/^\d{4}$/.test(s)) s = s.slice(0, 2) + ":" + s.slice(2);
        var m = s.match(/^(\d{1,2}):(\d{2})$/);
        if (!m) throw new Error("Keine gueltige Uhrzeit: " + s);
        return parseInt(m[1]) * 60 + parseInt(m[2]);
    }

    // Formel auswerten: {{feld_id}} → _F_feld_id, Semikolon → Komma
    function berechneFormel(formel, feldWerte) {
        try {
            // Semikolon → Komma (Funktionsargument-Trenner)
            var ausdruck = formel.replace(/;/g, ",");
            // {{feld_id}} → _F_feld_id
            ausdruck = ausdruck.replace(/\{\{(\w+)\}\}/g, "_F_$1");
            var tokens = tokenisiere(ausdruck);
            return parse(tokens, feldWerte);
        } catch (e) {
            return null;
        }
    }

    // Alle Formularfeldwerte als dict einlesen
    function holeFeldWerte(form) {
        var werte = {};
        form.querySelectorAll("input, select, textarea").forEach(function (el) {
            if (!el.name || el.dataset.berechnungId) return; // Berechnungsfelder ueberspringen
            if (el.type === "checkbox") {
                if (el.checked) {
                    var existing = werte["_F_" + el.name];
                    werte["_F_" + el.name] = existing ? existing + ", " + el.value : el.value;
                }
            } else if (el.type === "radio") {
                if (el.checked) werte["_F_" + el.name] = el.value;
            } else {
                werte["_F_" + el.name] = el.value;
            }
        });
        return werte;
    }

    // Ergebnis formatieren (Dezimalstellen)
    function formatiereErgebnis(wert, dezimalstellen) {
        if (wert === null || wert === undefined) return "";
        var num = parseFloat(wert);
        if (!isNaN(num)) {
            return num.toFixed(parseInt(dezimalstellen) || 0).replace(".", ",");
        }
        return String(wert);
    }

    // -----------------------------------------------------------------------
    // Initialisierung
    // -----------------------------------------------------------------------

    document.addEventListener("DOMContentLoaded", function () {
        var form = document.querySelector("form[method='post']");
        if (!form) return;

        var berechnungsFelder = form.querySelectorAll("[data-berechnung-id]");
        if (berechnungsFelder.length === 0) return;

        function alleBerechnen() {
            var feldWerte = holeFeldWerte(form);
            berechnungsFelder.forEach(function (anzeige) {
                var id = anzeige.dataset.berechnungId;
                var formel = anzeige.dataset.formel;
                var dez = anzeige.dataset.dezimalstellen || "2";
                var ergebnis = berechneFormel(formel, feldWerte);
                var anzeigeText = formatiereErgebnis(ergebnis, dez);
                anzeige.value = anzeigeText;
                // Verstecktes Feld fuer Submit befuellen
                var hidden = document.getElementById("berechnung-hidden-" + id);
                if (hidden) hidden.value = ergebnis !== null ? String(ergebnis) : "";
            });
        }

        // Jede Eingabeaenderung loest Neuberechnung aus
        form.addEventListener("input", alleBerechnen);
        form.addEventListener("change", alleBerechnen);

        // Einmal beim Laden berechnen (falls Felder vorbelegt sind)
        alleBerechnen();
    });

}());
