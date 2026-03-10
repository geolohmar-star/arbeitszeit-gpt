/* Workflow-Editor Logik – ausgelagert aus workflow_editor.html fuer CSP-Kompatibilitaet */

// Globale Variablen
var network;
var nodes, edges;
var modus = 'normal';
var verbindungStart = null;
var nextNodeId = 1;
var currentEditNode = null;
var currentTemplateId = null;
var currentTemplateName = '';
var currentTemplateAktiv = false;

// Schritt-Daten (wird beim Speichern ans Backend geschickt)
var schritte = [];

// Edge-Konfigurationen (fuer Graph-Workflows)
var edgeConfigs = [];

// Aktionstyp zu Farbe
var aktionColors = {
    'genehmigen': '#66b3ff',
    'pruefen': '#66d9ef',
    'informieren': '#ffe066',
    'bearbeiten': '#66cc99',
    'freigeben': '#b3b3b3',
    'verteilen': '#fd7e14'
};

// Netzwerk initialisieren
function init() {
    var container = document.getElementById('workflow-network');

    nodes = new vis.DataSet([]);
    edges = new vis.DataSet([]);

    var options = {
        nodes: {
            shape: 'diamond',
            size: 30,
            font: { size: 16, color: '#000', face: 'Arial' },
            borderWidth: 2,
            shadow: true
        },
        edges: {
            width: 2,
            shadow: true,
            arrows: 'to',
            smooth: { type: 'cubicBezier', forceDirection: 'horizontal' }
        },
        layout: { hierarchical: false },
        physics: { enabled: false },
        interaction: { dragNodes: true, dragView: true, zoomView: true }
    };

    network = new vis.Network(container, { nodes: nodes, edges: edges }, options);

    network.on('click', handleClick);
    network.on('doubleClick', handleDoubleClick);

    createAntragNode();
}

// Erstelle den "Antrag" Start-Knoten
function createAntragNode() {
    if (nodes.get('antrag_start')) { return; }

    nodes.add({
        id: 'antrag_start',
        label: 'Antrag\n(Antragsteller)',
        shape: 'box',
        color: {
            background: '#e3f2fd',
            border: '#1976d2',
            highlight: { background: '#bbdefb', border: '#0d47a1' }
        },
        font: { size: 14, color: '#0d47a1', bold: true },
        fixed: false,
        x: -300,
        y: 0,
        borderWidth: 3,
        margin: 10
    });
}

// Klick-Handler
function handleClick(params) {
    if (modus === 'schritt') {
        if (params.nodes.length === 0) {
            createNewSchritt(params.pointer.canvas);
        }
    } else if (modus === 'verbinden') {
        if (params.nodes.length > 0) {
            var clickedNode = params.nodes[0];
            if (verbindungStart === null) {
                verbindungStart = clickedNode;
            } else {
                createEdge(verbindungStart, clickedNode);
                verbindungStart = null;
            }
        }
    } else if (modus === 'schere') {
        if (params.nodes.length > 0) {
            deleteNode(params.nodes[0]);
        } else if (params.edges.length > 0) {
            deleteEdge(params.edges[0]);
        }
    } else if (modus === 'bearbeiten') {
        if (params.nodes.length > 0) {
            editSchritt(params.nodes[0]);
        }
    }
}

// Neuen Schritt erstellen
function createNewSchritt(position) {
    currentEditNode = null;
    document.getElementById('schritt-id').value = '';
    document.getElementById('schritt-titel').value = '';
    document.getElementById('schritt-beschreibung').value = '';
    document.getElementById('schritt-aktion').value = 'genehmigen';
    document.getElementById('schritt-rolle').value = 'direkte_fuehrungskraft';
    document.getElementById('schritt-team').value = '';
    document.getElementById('schritt-frist').value = '3';
    document.getElementById('schritt-parallel').checked = false;
    document.getElementById('schritt-eskalation').value = '0';

    // Verteiler-Panel leeren
    document.getElementById('verteiler-kanaele-liste').innerHTML = '';

    toggleAktionFelder();

    document.getElementById('schritt-loeschen-btn').style.display = 'none';
    document.getElementById('schrittModalTitle').textContent = 'Neuen Schritt erstellen';

    var modal = new bootstrap.Modal(document.getElementById('schrittModal'));
    modal.show();
}

// Verteiler-Kanaele aus dem DOM auslesen
function leseVerteilerKanaele() {
    var kanaele = [];
    document.querySelectorAll('#verteiler-kanaele-liste .kanal-eintrag').forEach(function(el) {
        var typ = el.querySelector('.kanal-typ').value;
        var kanal = { typ: typ };
        if (typ === 'email') {
            kanal.empfaenger = el.querySelector('.kanal-email-empfaenger').value;
            kanal.betreff = el.querySelector('.kanal-email-betreff').value;
            kanal.nachricht = el.querySelector('.kanal-email-nachricht').value;
        } else if (typ === 'matrix') {
            kanal.room_id = el.querySelector('.kanal-matrix-room').value;
            kanal.nachricht = el.querySelector('.kanal-matrix-nachricht').value;
        } else if (typ === 'intern') {
            kanal.nachricht = el.querySelector('.kanal-intern-nachricht').value;
        }
        kanaele.push(kanal);
    });
    return kanaele;
}

// Schritt speichern
function saveSchritt() {
    var id = document.getElementById('schritt-id').value;
    var titel = document.getElementById('schritt-titel').value;
    var beschreibung = document.getElementById('schritt-beschreibung').value;
    var aktion = document.getElementById('schritt-aktion').value;
    var rolle = document.getElementById('schritt-rolle').value;
    var teamId = document.getElementById('schritt-team').value;
    var frist = parseInt(document.getElementById('schritt-frist').value);
    var parallel = document.getElementById('schritt-parallel').checked;
    var eskalation = parseInt(document.getElementById('schritt-eskalation').value);
    var verteilerKanaele = aktion === 'verteilen' ? leseVerteilerKanaele() : [];

    if (!titel) { alert('Bitte einen Titel eingeben!'); return; }

    if (aktion !== 'verteilen' && rolle === 'team_queue' && !teamId) {
        alert('Bitte ein Team auswaehlen!');
        return;
    }

    var color = aktionColors[aktion] || '#6c757d';

    var displayRolle = aktion === 'verteilen' ? 'auto' : rolle;
    if (rolle === 'team_queue' && teamId) {
        var teamSelect = document.getElementById('schritt-team');
        var teamOption = teamSelect.options[teamSelect.selectedIndex];
        displayRolle = 'Team: ' + teamOption.text;
    }

    var nodeData = {
        titel: titel, beschreibung: beschreibung, aktion: aktion,
        rolle: rolle, teamId: teamId, frist: frist, parallel: parallel,
        eskalation: eskalation, verteilerKanaele: verteilerKanaele
    };

    if (id) {
        nodes.update({
            id: id,
            label: titel,
            title: titel + '\n' + aktion + '\n' + displayRolle,
            color: {
                background: color,
                border: color,
                highlight: { background: color, border: color }
            },
            data: nodeData
        });

        var idx = schritte.findIndex(function(s) { return s.id === id; });
        if (idx >= 0) {
            schritte[idx] = Object.assign({ id: id }, nodeData);
        }
    } else {
        var nodeId = 'node_' + (nextNodeId++);
        nodes.add({
            id: nodeId,
            label: titel,
            title: titel + '\n' + aktion + '\n' + displayRolle,
            color: {
                background: color,
                border: color,
                highlight: { background: color, border: color }
            },
            data: nodeData
        });

        schritte.push(Object.assign({ id: nodeId }, nodeData));
    }

    bootstrap.Modal.getInstance(document.getElementById('schrittModal')).hide();
}

// Verteiler-Kanaele ins DOM schreiben (beim Bearbeiten / Laden)
function setzeVerteilerKanaele(kanaele) {
    var liste = document.getElementById('verteiler-kanaele-liste');
    liste.innerHTML = '';
    if (!kanaele || kanaele.length === 0) { return; }
    kanaele.forEach(function(kanal) { fuegeKanalHinzu(kanal); });
}

// Schritt bearbeiten
function editSchritt(nodeId) {
    var node = nodes.get(nodeId);
    if (!node) { return; }

    var data = node.data || {};

    currentEditNode = nodeId;
    document.getElementById('schritt-id').value = nodeId;
    document.getElementById('schritt-titel').value = data.titel || node.label;
    document.getElementById('schritt-beschreibung').value = data.beschreibung || '';
    document.getElementById('schritt-aktion').value = data.aktion || 'genehmigen';
    document.getElementById('schritt-rolle').value = data.rolle || 'direkte_fuehrungskraft';
    document.getElementById('schritt-team').value = data.teamId || '';
    document.getElementById('schritt-frist').value = data.frist || 3;
    document.getElementById('schritt-parallel').checked = data.parallel || false;
    document.getElementById('schritt-eskalation').value = data.eskalation || 0;

    // Verteiler-Kanaele wiederherstellen
    setzeVerteilerKanaele(data.verteilerKanaele || []);

    toggleAktionFelder();

    document.getElementById('schritt-loeschen-btn').style.display = 'block';
    document.getElementById('schrittModalTitle').textContent = 'Schritt bearbeiten';

    var modal = new bootstrap.Modal(document.getElementById('schrittModal'));
    modal.show();
}

// Verbindung erstellen
function createEdge(fromId, toId) {
    if (fromId === toId) {
        alert('Ein Schritt kann nicht mit sich selbst verbunden werden!');
        return;
    }

    var existingEdges = edges.get({
        filter: function(edge) { return edge.from === fromId && edge.to === toId; }
    });

    if (existingEdges.length > 0) {
        alert('Diese Verbindung existiert bereits!');
        return;
    }

    edges.add({ id: 'edge_' + fromId + '_' + toId, from: fromId, to: toId });
}

// Node loeschen
function deleteNode(nodeId) {
    if (nodeId === 'antrag_start') {
        alert('Der Antrag-Startknoten kann nicht geloescht werden.');
        return;
    }

    if (confirm('Schritt "' + nodes.get(nodeId).label + '" wirklich loeschen?')) {
        schritte = schritte.filter(function(s) { return s.id !== nodeId; });

        var connectedEdges = edges.get({
            filter: function(edge) { return edge.from === nodeId || edge.to === nodeId; }
        });
        connectedEdges.forEach(function(edge) { edges.remove(edge.id); });

        nodes.remove(nodeId);
    }
}

// Aktuell bearbeiteten Schritt loeschen (aus Modal)
function deleteCurrentSchritt() {
    var nodeId = document.getElementById('schritt-id').value;

    if (!nodeId) { alert('Kein Schritt zum Loeschen ausgewaehlt.'); return; }

    if (nodeId === 'antrag_start') {
        alert('Der Antrag-Startknoten kann nicht geloescht werden.');
        return;
    }

    if (confirm('Schritt "' + nodes.get(nodeId).label + '" wirklich loeschen?')) {
        schritte = schritte.filter(function(s) { return s.id !== nodeId; });

        var connectedEdges = edges.get({
            filter: function(edge) { return edge.from === nodeId || edge.to === nodeId; }
        });
        connectedEdges.forEach(function(edge) { edges.remove(edge.id); });

        nodes.remove(nodeId);

        bootstrap.Modal.getInstance(document.getElementById('schrittModal')).hide();
    }
}

// Edge loeschen
function deleteEdge(edgeId) {
    if (confirm('Verbindung wirklich loeschen?')) {
        edges.remove(edgeId);
    }
}

// Zentrieren
function zentrieren() { network.fit(); }

// Modus-Anzeige aktualisieren
function updateModusAnzeige() {
    var modusTexte = {
        'normal': 'Normaler Modus',
        'schritt': 'Schritt hinzufuegen - Klick auf Canvas',
        'verbinden': 'Verbinden - Erst Start-, dann Ziel-Schritt klicken',
        'schere': 'Schere - Klick auf Schritt oder Verbindung zum Loeschen',
        'bearbeiten': 'Bearbeiten - Klick auf Schritt zum Bearbeiten'
    };

    document.getElementById('modus-text').textContent = modusTexte[modus] || 'Unbekannt';
    verbindungStart = null;
}

// Speichern-Dialog anzeigen
function showSaveDialog() {
    if (nodes.length === 0) { alert('Bitte erst Schritte erstellen!'); return; }

    if (currentTemplateId) {
        document.getElementById('current-template-info').style.display = 'block';
        document.getElementById('current-template-name-display').textContent = currentTemplateName;
        document.getElementById('save-mode-group').style.display = 'block';
        document.getElementById('template-name-input').value = currentTemplateName;
        document.getElementById('template-aktiv').checked = currentTemplateAktiv;
        document.getElementById('save-mode-update').checked = true;
    } else {
        document.getElementById('current-template-info').style.display = 'none';
        document.getElementById('save-mode-group').style.display = 'none';
        document.getElementById('template-name-input').value = '';
        document.getElementById('template-aktiv').checked = true;
    }

    var modal = new bootstrap.Modal(document.getElementById('saveModal'));
    modal.show();
}

// Workflow speichern
async function saveWorkflow() {
    var name = document.getElementById('template-name-input').value;
    var beschreibung = document.getElementById('template-beschreibung').value;
    var kategorie = document.getElementById('template-kategorie').value;
    var trigger = document.getElementById('template-trigger').value;
    var aktiv = document.getElementById('template-aktiv').checked;

    if (trigger === 'custom') {
        var customTrigger = document.getElementById('template-trigger-custom').value.trim();
        if (!customTrigger) { alert('Bitte ein benutzerdefiniertes Event eingeben!'); return; }
        trigger = customTrigger;
    }

    if (!trigger) { trigger = null; }

    if (!name) { alert('Bitte einen Template-Namen eingeben!'); return; }

    var saveMode = 'new';
    var templateIdToUpdate = null;

    if (currentTemplateId) {
        var saveModeRadio = document.querySelector('input[name="save-mode"]:checked');
        saveMode = saveModeRadio ? saveModeRadio.value : 'new';
        if (saveMode === 'update') { templateIdToUpdate = currentTemplateId; }
    }

    var schritteMitReihenfolge = calculateReihenfolge();

    var allEdges = edges.get().map(function(edge) {
        var config = edgeConfigs.find(function(c) { return c.edgeId === edge.id; });
        return { from: edge.from, to: edge.to, config: config || { bedingung_typ: 'immer' } };
    });

    var data = {
        template: {
            name: name,
            beschreibung: beschreibung,
            kategorie: kategorie,
            trigger_event: trigger,
            aktiv: aktiv,
            template_id: templateIdToUpdate
        },
        schritte: schritteMitReihenfolge,
        edges: allEdges,
        ist_graph_workflow: edgeConfigs.length > 0
    };

    try {
        var response = await fetch('/workflow/editor/save/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').content
            },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            var result = await response.json();
            document.getElementById('modus-text').innerHTML = '<span class="text-success">Workflow "' + name + '" erfolgreich gespeichert!</span>';
            bootstrap.Modal.getInstance(document.getElementById('saveModal')).hide();
            currentTemplateId = result.template_id;
            document.getElementById('template-name').textContent = name;
        } else {
            var error = await response.json();
            alert('Fehler beim Speichern: ' + (error.error || 'Unbekannter Fehler'));
        }
    } catch (error) {
        alert('Fehler beim Speichern: ' + error.message);
    }
}

// Reihenfolge berechnen
function calculateReihenfolge() {
    var allEdges = edges.get();
    var allNodes = nodes.get();

    var inDegree = {};
    allNodes.forEach(function(n) { inDegree[n.id] = 0; });
    allEdges.forEach(function(e) {
        if (inDegree[e.to] !== undefined) { inDegree[e.to]++; }
    });

    var queue = allNodes.filter(function(n) { return inDegree[n.id] === 0; });
    var sorted = [];
    var reihenfolge = 1;

    while (queue.length > 0) {
        var node = queue.shift();
        var schrittData = schritte.find(function(s) { return s.id === node.id; });
        if (schrittData) {
            sorted.push(Object.assign({}, schrittData, { reihenfolge: reihenfolge++ }));
        }

        allEdges.filter(function(e) { return e.from === node.id; }).forEach(function(e) {
            inDegree[e.to]--;
            if (inDegree[e.to] === 0) {
                var nextNode = allNodes.find(function(n) { return n.id === e.to; });
                if (nextNode) { queue.push(nextNode); }
            }
        });
    }

    schritte.forEach(function(s) {
        if (!sorted.find(function(x) { return x.id === s.id; })) {
            sorted.push(Object.assign({}, s, { reihenfolge: reihenfolge++ }));
        }
    });

    return sorted;
}

// Template laden Dialog anzeigen
async function showLoadDialog() {
    var modal = new bootstrap.Modal(document.getElementById('loadModal'));
    modal.show();

    try {
        var response = await fetch('/workflow/editor/templates/');
        var data = await response.json();

        var container = document.getElementById('template-liste');
        container.innerHTML = '';

        if (data.templates.length === 0) {
            container.innerHTML = '<div class="alert alert-info">Keine Templates vorhanden.</div>';
            return;
        }

        data.templates.forEach(function(t) {
            var item = document.createElement('a');
            item.href = '#';
            item.className = 'list-group-item list-group-item-action';
            item.innerHTML = '<div class="d-flex w-100 justify-content-between">'
                + '<h6 class="mb-1">' + t.name + '</h6>'
                + '<small>' + (t.ist_aktiv ? '<span class="badge bg-success">Aktiv</span>' : '<span class="badge bg-secondary">Inaktiv</span>') + '</small>'
                + '</div>'
                + '<p class="mb-1 small text-muted">Kategorie: ' + t.kategorie + ' | Schritte: ' + t.schritte_anzahl + '</p>';
            item.addEventListener('click', function(e) {
                e.preventDefault();
                loadTemplate(t.id);
                modal.hide();
            });
            container.appendChild(item);
        });
    } catch (error) {
        document.getElementById('template-liste').innerHTML =
            '<div class="alert alert-danger">Fehler beim Laden: ' + error.message + '</div>';
    }
}

// Template vom Server laden und visualisieren
// silent=true unterdrueckt den Alert (fuer Autoload beim Seitenstart)
async function loadTemplate(templateId, silent) {
    try {
        var response = await fetch('/workflow/editor/load/' + templateId + '/');
        var data = await response.json();

        currentTemplateId = templateId;
        currentTemplateName = data.template.name;
        currentTemplateAktiv = data.template.ist_aktiv || false;

        document.getElementById('template-name').textContent = data.template.name;

        nodes.clear();
        edges.clear();
        schritte = [];
        edgeConfigs = [];

        var startX = 200;
        var startY = 300;
        var spacingX = 350;
        var spacingY = 150;

        data.nodes.forEach(function(nodeData, index) {
            var nodeId = nodeData.id;
            var color = aktionColors[nodeData.aktion] || '#6c757d';
            var xPos = startX + (nodeData.reihenfolge - 1) * spacingX;
            var yPos = startY + (index % 3) * spacingY;

            nodes.add({
                id: nodeId,
                label: nodeData.titel,
                title: nodeData.titel + '\n' + nodeData.aktion + '\n' + nodeData.rolle,
                color: {
                    background: color,
                    border: color,
                    highlight: { background: color, border: color }
                },
                x: xPos,
                y: yPos,
                fixed: { x: false, y: false },
                physics: false,
                data: nodeData
            });

            schritte.push({
                id: nodeId,
                titel: nodeData.titel,
                beschreibung: nodeData.beschreibung,
                aktion: nodeData.aktion,
                rolle: nodeData.rolle,
                frist: nodeData.frist,
                parallel: nodeData.parallel,
                eskalation: nodeData.eskalation,
                reihenfolge: nodeData.reihenfolge,
                verteilerKanaele: nodeData.verteilerKanaele || []
            });
        });

        if (data.edges && data.edges.length > 0) {
            data.edges.forEach(function(edgeData) {
                var edgeId = 'edge_' + edgeData.from + '_' + edgeData.to;
                edges.add({
                    id: edgeId,
                    from: edgeData.from,
                    to: edgeData.to,
                    label: (edgeData.config && edgeData.config.label) ? edgeData.config.label : ''
                });
                if (edgeData.config) {
                    edgeConfigs.push(Object.assign({ edgeId: edgeId }, edgeData.config));
                }
            });
        } else {
            var sortedNodes = data.nodes.slice().sort(function(a, b) { return a.reihenfolge - b.reihenfolge; });

            for (var i = 0; i < sortedNodes.length - 1; i++) {
                edges.add({
                    id: 'edge_' + sortedNodes[i].id + '_' + sortedNodes[i + 1].id,
                    from: sortedNodes[i].id,
                    to: sortedNodes[i + 1].id
                });
            }

            if (sortedNodes.length > 0) {
                edges.add({
                    id: 'edge_antrag_start_' + sortedNodes[0].id,
                    from: 'antrag_start',
                    to: sortedNodes[0].id
                });
            }
        }

        var maxId = Math.max.apply(null, data.nodes.map(function(n) {
            var match = n.id.match(/node_(\d+)/);
            return match ? parseInt(match[1]) : 0;
        }).concat([0]));
        nextNodeId = maxId + 1;

        createAntragNode();

        setTimeout(function() { network.fit(); }, 100);

        if (!silent) {
            alert('Template "' + data.template.name + '" erfolgreich geladen!');
        }
    } catch (error) {
        alert('Fehler beim Laden: ' + error.message);
    }
}

// Canvas leeren
function clearCanvas() {
    if (confirm('Canvas wirklich leeren? Alle Schritte werden geloescht.')) {
        nodes.clear();
        edges.clear();
        schritte = [];
        edgeConfigs = [];
        nextNodeId = 1;
        document.getElementById('template-name').textContent = 'Neues Workflow-Template';
        createAntragNode();
    }
}

// Doppelklick-Handler fuer Edge-Konfiguration
function handleDoubleClick(params) {
    if (params.edges.length === 1) {
        var edgeId = params.edges[0];
        var edge = edges.get(edgeId);
        if (edge) { openEdgeConfigModal(edge); }
    }
}

// Edge-Konfigurations-Modal oeffnen
function openEdgeConfigModal(edge) {
    var fromNode = nodes.get(edge.from);
    var toNode = nodes.get(edge.to);

    document.getElementById('edge-id').value = edge.id;
    document.getElementById('edge-von').value = fromNode ? fromNode.label : 'Unbekannt';
    document.getElementById('edge-zu').value = toNode ? toNode.label : 'Unbekannt';

    var config = edgeConfigs.find(function(c) { return c.edgeId === edge.id; }) || {};
    document.getElementById('edge-bedingung-typ').value = config.bedingung_typ || 'immer';
    document.getElementById('edge-bedingung-entscheidung').value = config.bedingung_entscheidung || 'genehmigt';
    document.getElementById('edge-bedingung-feld').value = config.bedingung_feld || '';
    document.getElementById('edge-bedingung-operator').value = config.bedingung_operator || '==';
    document.getElementById('edge-bedingung-wert').value = config.bedingung_wert || '';
    document.getElementById('edge-bedingung-python-code').value = config.bedingung_python_code || '';
    document.getElementById('edge-label').value = config.label || '';
    document.getElementById('edge-prioritaet').value = config.prioritaet || 1;

    updateEdgeBedingungFelder();

    var modal = new bootstrap.Modal(document.getElementById('edgeConfigModal'));
    modal.show();
}

// Edge-Bedingungsfelder ein/ausblenden
function updateEdgeBedingungFelder() {
    var typ = document.getElementById('edge-bedingung-typ').value;

    document.getElementById('edge-bedingung-entscheidung-container').style.display =
        typ === 'entscheidung' ? 'block' : 'none';
    document.getElementById('edge-bedingung-feld-container').style.display =
        typ === 'feld_wert' ? 'block' : 'none';
    document.getElementById('edge-bedingung-python-container').style.display =
        typ === 'python' ? 'block' : 'none';
}

// Edge-Konfiguration speichern
function saveEdgeConfig() {
    var edgeId = document.getElementById('edge-id').value;
    var bedingung_typ = document.getElementById('edge-bedingung-typ').value;

    var config = {
        edgeId: edgeId,
        bedingung_typ: bedingung_typ,
        bedingung_entscheidung: document.getElementById('edge-bedingung-entscheidung').value,
        bedingung_feld: document.getElementById('edge-bedingung-feld').value,
        bedingung_operator: document.getElementById('edge-bedingung-operator').value,
        bedingung_wert: document.getElementById('edge-bedingung-wert').value,
        bedingung_python_code: document.getElementById('edge-bedingung-python-code').value,
        label: document.getElementById('edge-label').value,
        prioritaet: parseInt(document.getElementById('edge-prioritaet').value) || 1
    };

    var index = edgeConfigs.findIndex(function(c) { return c.edgeId === edgeId; });
    if (index >= 0) {
        edgeConfigs[index] = config;
    } else {
        edgeConfigs.push(config);
    }

    if (config.label) {
        edges.update({ id: edgeId, label: config.label });
    } else {
        edges.update({ id: edgeId, label: '' });
    }

    bootstrap.Modal.getInstance(document.getElementById('edgeConfigModal')).hide();
}

// Edge aus Modal loeschen
function deleteEdgeFromModal() {
    var edgeId = document.getElementById('edge-id').value;
    if (confirm('Verbindung wirklich loeschen?')) {
        edges.remove(edgeId);
        edgeConfigs = edgeConfigs.filter(function(c) { return c.edgeId !== edgeId; });
        bootstrap.Modal.getInstance(document.getElementById('edgeConfigModal')).hide();
    }
}

// Felder abhaengig von Aktionstyp ein/ausblenden
function toggleAktionFelder() {
    var aktion = document.getElementById('schritt-aktion').value;
    var rolle = document.getElementById('schritt-rolle').value;
    var teamRow = document.getElementById('team-row');
    var verteilerRow = document.getElementById('verteiler-config-row');
    var rolleRow = document.getElementById('schritt-rolle').closest('.col-md-6');

    var istVerteilen = aktion === 'verteilen';

    // Rolle + Team nur bei normalen Aktionen anzeigen
    rolleRow.style.display = istVerteilen ? 'none' : '';

    if (istVerteilen) {
        teamRow.style.display = 'none';
        document.getElementById('schritt-team').required = false;
        verteilerRow.style.display = 'block';
    } else {
        verteilerRow.style.display = 'none';
        if (rolle === 'team_queue') {
            teamRow.style.display = 'block';
            document.getElementById('schritt-team').required = true;
        } else {
            teamRow.style.display = 'none';
            document.getElementById('schritt-team').required = false;
            document.getElementById('schritt-team').value = '';
        }
    }
}

// Rueckwaertskompatibilitaet (wird von rolleSelect.change aufgerufen)
function toggleTeamDropdown() { toggleAktionFelder(); }

// Neuen Kanal-Eintrag hinzufuegen (optional mit Vorbelegung)
function fuegeKanalHinzu(vorbelegung) {
    var vorlage = document.getElementById('kanal-vorlage');
    var klon = vorlage.content.cloneNode(true);
    var eintrag = klon.querySelector('.kanal-eintrag');

    if (vorbelegung) {
        eintrag.querySelector('.kanal-typ').value = vorbelegung.typ || 'email';
        if (vorbelegung.typ === 'email') {
            eintrag.querySelector('.kanal-email-empfaenger').value = vorbelegung.empfaenger || '';
            eintrag.querySelector('.kanal-email-betreff').value = vorbelegung.betreff || '';
            eintrag.querySelector('.kanal-email-nachricht').value = vorbelegung.nachricht || '';
        } else if (vorbelegung.typ === 'matrix') {
            eintrag.querySelector('.kanal-matrix-room').value = vorbelegung.room_id || '';
            eintrag.querySelector('.kanal-matrix-nachricht').value = vorbelegung.nachricht || '';
        } else if (vorbelegung.typ === 'intern') {
            eintrag.querySelector('.kanal-intern-nachricht').value = vorbelegung.nachricht || '';
        }
    }

    // Kanal-Typ-Toggle verdrahten
    var typSelect = eintrag.querySelector('.kanal-typ');
    toggleKanalFelder(eintrag, typSelect.value);
    typSelect.addEventListener('change', function() {
        toggleKanalFelder(eintrag, this.value);
    });

    // Loeschen-Button verdrahten
    eintrag.querySelector('.kanal-loeschen').addEventListener('click', function() {
        eintrag.remove();
    });

    document.getElementById('verteiler-kanaele-liste').appendChild(eintrag);
}

// Kanal-Felder je nach Typ ein/ausblenden
function toggleKanalFelder(eintrag, typ) {
    eintrag.querySelector('.kanal-felder-email').style.display = typ === 'email' ? '' : 'none';
    eintrag.querySelector('.kanal-felder-matrix').style.display = typ === 'matrix' ? '' : 'none';
    eintrag.querySelector('.kanal-felder-intern').style.display = typ === 'intern' ? '' : 'none';
}

async function loadTeamQueues() {
    try {
        var response = await fetch('/formulare/api/team-queues/');
        var data = await response.json();

        var select = document.getElementById('schritt-team');
        select.innerHTML = '<option value="">-- Team auswaehlen --</option>';

        data.teams.forEach(function(team) {
            var option = document.createElement('option');
            option.value = team.id;
            option.textContent = team.name;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Fehler beim Laden der Team-Queues:', error);
    }
}

// Trigger-Event Custom-Feld ein/ausblenden
function toggleTriggerCustom() {
    var triggerSelect = document.getElementById('template-trigger');
    var customInput = document.getElementById('template-trigger-custom');

    if (triggerSelect.value === 'custom') {
        customInput.style.display = 'block';
        customInput.required = true;
    } else {
        customInput.style.display = 'none';
        customInput.required = false;
        customInput.value = '';
    }
}

// Init beim Laden
document.addEventListener('DOMContentLoaded', function() {
    init();
    loadTeamQueues();

    // Autoload: URL-Parameter ?load=<id> direkt laden
    var autoloadEl = document.getElementById('autoload-template-id');
    if (autoloadEl) {
        var autoloadId = JSON.parse(autoloadEl.textContent);
        if (autoloadId) {
            // Kurzer Timeout damit vis.js vollstaendig gerendert ist
            setTimeout(function() { loadTemplate(autoloadId, true); }, 200);
        }
    }

    // Toolbar-Buttons
    var btnLoad = document.getElementById('btn-load-dialog');
    if (btnLoad) { btnLoad.addEventListener('click', showLoadDialog); }

    var btnModusSchritt = document.getElementById('btn-modus-schritt');
    if (btnModusSchritt) {
        btnModusSchritt.addEventListener('click', function() { modus = 'schritt'; updateModusAnzeige(); });
    }

    var btnModusVerbinden = document.getElementById('btn-modus-verbinden');
    if (btnModusVerbinden) {
        btnModusVerbinden.addEventListener('click', function() { modus = 'verbinden'; updateModusAnzeige(); });
    }

    var btnModusSchere = document.getElementById('btn-modus-schere');
    if (btnModusSchere) {
        btnModusSchere.addEventListener('click', function() { modus = 'schere'; updateModusAnzeige(); });
    }

    var btnModusBearbeiten = document.getElementById('btn-modus-bearbeiten');
    if (btnModusBearbeiten) {
        btnModusBearbeiten.addEventListener('click', function() { modus = 'bearbeiten'; updateModusAnzeige(); });
    }

    var btnZentrieren = document.getElementById('btn-zentrieren');
    if (btnZentrieren) { btnZentrieren.addEventListener('click', zentrieren); }

    var btnSaveDialog = document.getElementById('btn-save-dialog');
    if (btnSaveDialog) { btnSaveDialog.addEventListener('click', showSaveDialog); }

    var btnClearCanvas = document.getElementById('btn-clear-canvas');
    if (btnClearCanvas) { btnClearCanvas.addEventListener('click', clearCanvas); }

    // Modal-Schritt Buttons
    var btnLoeschen = document.getElementById('schritt-loeschen-btn');
    if (btnLoeschen) { btnLoeschen.addEventListener('click', deleteCurrentSchritt); }

    var btnSaveSchritt = document.getElementById('btn-save-schritt');
    if (btnSaveSchritt) { btnSaveSchritt.addEventListener('click', saveSchritt); }

    // Modal-Speichern Button
    var btnSaveWorkflow = document.getElementById('btn-save-workflow');
    if (btnSaveWorkflow) { btnSaveWorkflow.addEventListener('click', saveWorkflow); }

    // Modal-Edge Buttons
    var btnDeleteEdge = document.getElementById('btn-delete-edge');
    if (btnDeleteEdge) { btnDeleteEdge.addEventListener('click', deleteEdgeFromModal); }

    var btnSaveEdge = document.getElementById('btn-save-edge');
    if (btnSaveEdge) { btnSaveEdge.addEventListener('click', saveEdgeConfig); }

    // Selects
    var aktionSelect = document.getElementById('schritt-aktion');
    if (aktionSelect) { aktionSelect.addEventListener('change', toggleAktionFelder); }

    var rolleSelect = document.getElementById('schritt-rolle');
    if (rolleSelect) { rolleSelect.addEventListener('change', toggleAktionFelder); }

    // Kanal hinzufuegen Button
    var btnKanal = document.getElementById('btn-kanal-hinzufuegen');
    if (btnKanal) { btnKanal.addEventListener('click', function() { fuegeKanalHinzu(); }); }

    var edgeBedingungTyp = document.getElementById('edge-bedingung-typ');
    if (edgeBedingungTyp) { edgeBedingungTyp.addEventListener('change', updateEdgeBedingungFelder); }

    // Speichermodus-Radio-Buttons
    var saveModeUpdate = document.getElementById('save-mode-update');
    if (saveModeUpdate) {
        saveModeUpdate.addEventListener('change', function() {
            if (this.checked && currentTemplateName) {
                document.getElementById('template-name-input').value = currentTemplateName;
            }
        });
    }

    var saveModeNew = document.getElementById('save-mode-new');
    if (saveModeNew) {
        saveModeNew.addEventListener('change', function() {
            if (this.checked && currentTemplateName) {
                document.getElementById('template-name-input').value = currentTemplateName + ' (Kopie)';
            }
        });
    }

    // Trigger-Dropdown
    var triggerSelect = document.getElementById('template-trigger');
    if (triggerSelect) { triggerSelect.addEventListener('change', toggleTriggerCustom); }
});
