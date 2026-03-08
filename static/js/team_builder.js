/* Team-Builder Logik – ausgelagert aus team_builder.html fuer CSP-Kompatibilitaet */

// ALL_USERS aus json_script-Element lesen
var ALL_USERS = (function() {
    var el = document.getElementById('all-users-data');
    return el ? JSON.parse(el.textContent) : [];
})();

var csrftoken = document.querySelector('meta[name="csrf-token"]')
    ? document.querySelector('meta[name="csrf-token"]').content
    : '';

// ---------------------------------------------------------------------------
// Hilfsfunktionen Antragstyp-Checkboxen
// ---------------------------------------------------------------------------
function _resetTypCheckboxes() {
    document.querySelectorAll('.antragstyp-cb').forEach(function(cb) { cb.checked = false; });
}

function _setTypCheckboxes(typen) {
    _resetTypCheckboxes();
    (typen || []).forEach(function(typ) {
        var cb = document.querySelector('.antragstyp-cb[value="' + typ + '"]');
        if (cb) { cb.checked = true; }
    });
}

function _getTypCheckboxes() {
    return Array.from(document.querySelectorAll('.antragstyp-cb:checked')).map(function(cb) { return cb.value; });
}

// ---------------------------------------------------------------------------
// Team Modal
// ---------------------------------------------------------------------------
function openTeamModal() {
    document.getElementById('team-id').value = '';
    document.getElementById('team-name').value = '';
    document.getElementById('team-beschreibung').value = '';
    document.getElementById('teamModalTitle').textContent = 'Neues Team erstellen';
    _resetTypCheckboxes();
    new bootstrap.Modal(document.getElementById('teamModal')).show();
}

async function editTeam(teamId) {
    try {
        var response = await fetch('/formulare/team-builder/team/' + teamId + '/');
        var data = await response.json();

        document.getElementById('team-id').value = data.id;
        document.getElementById('team-name').value = data.name;
        document.getElementById('team-beschreibung').value = data.beschreibung || '';
        document.getElementById('teamModalTitle').textContent = 'Team bearbeiten';
        _setTypCheckboxes(data.antragstypen || []);

        new bootstrap.Modal(document.getElementById('teamModal')).show();
    } catch (error) {
        alert('Fehler beim Laden: ' + error);
    }
}

async function saveTeam() {
    var teamId = document.getElementById('team-id').value;
    var name = document.getElementById('team-name').value;
    var beschreibung = document.getElementById('team-beschreibung').value;
    var antragstypen = _getTypCheckboxes();

    if (!name) { alert('Bitte einen Namen eingeben!'); return; }

    var url = teamId
        ? '/formulare/team-builder/team/' + teamId + '/update/'
        : '/formulare/team-builder/team/create/';

    try {
        var response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ name: name, beschreibung: beschreibung, antragstypen: antragstypen })
        });

        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('teamModal')).hide();
            location.reload();
        } else {
            var error = await response.json();
            alert('Fehler: ' + (error.error || 'Unbekannter Fehler'));
        }
    } catch (error) {
        alert('Fehler beim Speichern: ' + error);
    }
}

async function deleteTeam(teamId, teamName) {
    if (!confirm('Team "' + teamName + '" wirklich loeschen?')) { return; }

    try {
        var response = await fetch('/formulare/team-builder/team/' + teamId + '/delete/', {
            method: 'POST',
            headers: { 'X-CSRFToken': csrftoken }
        });

        if (response.ok) {
            var el = document.getElementById('team-' + teamId);
            if (el) { el.remove(); }
            location.reload();
        } else {
            var data = await response.json().catch(function() { return {}; });
            alert('Loeschen nicht moeglich:\n' + (data.error || 'Unbekannter Fehler'));
        }
    } catch (error) {
        alert('Fehler: ' + error);
    }
}

// ---------------------------------------------------------------------------
// Mitglied hinzufuegen Modal (Team-Queue)
// ---------------------------------------------------------------------------
var _currentUsers = [];

function renderMemberList(users) {
    var list = document.getElementById('member-list');
    if (!users.length) {
        list.innerHTML = '<p class="text-muted small p-3 mb-0">Keine Ergebnisse.</p>';
        return;
    }
    list.innerHTML = users.map(function(u) {
        var stelle = u.stelle || '';
        var stelleHtml = stelle
            ? '<small class="text-muted">' + stelle + '</small>'
            : '<small class="text-muted fst-italic">keine Stelle</small>';
        return '<div class="member-option d-flex align-items-center px-3 py-2 border-bottom"'
            + ' style="cursor:pointer;"'
            + ' data-id="' + u.id + '"'
            + ' data-name="' + u.name + '"'
            + ' data-stelle="' + stelle + '"'
            + ' data-action="select-member">'
            + '<div class="flex-grow-1">'
            + '<div class="fw-semibold">' + u.name + '</div>'
            + stelleHtml
            + '</div>'
            + '<small class="text-muted ms-2">' + u.username + '</small>'
            + '</div>';
    }).join('');
}

function filterMemberList(query) {
    var q = query.toLowerCase().trim();
    if (!q) { renderMemberList(_currentUsers); return; }
    var gefunden = _currentUsers.filter(function(u) {
        var suchtext = (u.name + ' ' + u.stelle + ' ' + u.username).toLowerCase();
        return suchtext.indexOf(q) !== -1;
    });
    renderMemberList(gefunden);
    document.getElementById('member-select').value = '';
    document.getElementById('member-selected').textContent = 'Noch niemanden ausgewaehlt.';
}

function selectMember(el) {
    document.querySelectorAll('.member-option').forEach(function(e) {
        e.classList.remove('bg-primary', 'text-white');
        e.querySelectorAll('small').forEach(function(s) { s.classList.remove('text-white'); });
    });
    el.classList.add('bg-primary', 'text-white');
    el.querySelectorAll('small').forEach(function(s) { s.classList.add('text-white'); });

    document.getElementById('member-select').value = el.dataset.id;
    var stelle = el.dataset.stelle;
    document.getElementById('member-selected').innerHTML =
        'Ausgewaehlt: <strong>' + el.dataset.name + '</strong>'
        + (stelle ? ' &ndash; ' + stelle : '');
}

function addMemberModal(teamId, teamName) {
    document.getElementById('member-team-id').value = teamId;
    document.getElementById('memberModalTitle').textContent = 'Mitglied zu "' + teamName + '" hinzufuegen';
    document.getElementById('member-select').value = '';
    document.getElementById('member-search').value = '';
    document.getElementById('member-selected').textContent = 'Noch niemanden ausgewaehlt.';

    _currentUsers = ALL_USERS;
    renderMemberList(_currentUsers);

    new bootstrap.Modal(document.getElementById('memberModal')).show();

    document.getElementById('memberModal').addEventListener('shown.bs.modal', function() {
        document.getElementById('member-search').focus();
    }, { once: true });
}

async function saveMember() {
    var teamId = document.getElementById('member-team-id').value;
    var userId = document.getElementById('member-select').value;

    if (!userId) { alert('Bitte einen User auswaehlen!'); return; }

    try {
        var response = await fetch('/formulare/team-builder/team/' + teamId + '/member/add/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ user_id: userId })
        });

        if (response.ok) {
            bootstrap.Modal.getInstance(document.getElementById('memberModal')).hide();
            location.reload();
        } else {
            var error = await response.json();
            alert('Fehler: ' + (error.error || 'Unbekannter Fehler'));
        }
    } catch (error) {
        alert('Fehler: ' + error);
    }
}

async function removeMember(teamId, userId, username) {
    if (!confirm('User "' + username + '" aus dem Team entfernen?')) { return; }

    try {
        var response = await fetch('/formulare/team-builder/team/' + teamId + '/member/remove/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ user_id: userId })
        });

        if (response.ok) {
            location.reload();
        } else {
            alert('Fehler beim Entfernen');
        }
    } catch (error) {
        alert('Fehler: ' + error);
    }
}

// ---------------------------------------------------------------------------
// Facility-Team Member-Management
// ---------------------------------------------------------------------------
var currentFacilityTeamId = null;

function facilityAddMemberModal(teamId, teamName) {
    currentFacilityTeamId = teamId;
    document.getElementById('facility-modal-teamname').textContent = teamName;
    document.getElementById('facility-member-search').value = '';
    renderFacilityUserList('');
    new bootstrap.Modal(document.getElementById('facilityMemberModal')).show();
}

function renderFacilityUserList(query) {
    var container = document.getElementById('facility-member-list');
    var filtered = ALL_USERS.filter(function(u) {
        return u.name.toLowerCase().indexOf(query.toLowerCase()) !== -1
            || u.username.toLowerCase().indexOf(query.toLowerCase()) !== -1;
    });
    if (filtered.length === 0) {
        container.innerHTML = '<p class="text-muted p-2">Keine Treffer</p>';
        return;
    }
    container.innerHTML = filtered.map(function(u) {
        return '<div class="d-flex justify-content-between align-items-center border-bottom py-2 px-1">'
            + '<div><strong>' + u.name + '</strong><br>'
            + '<small class="text-muted">' + u.username + (u.stelle ? ' – ' + u.stelle : '') + '</small></div>'
            + '<button class="btn btn-sm btn-success"'
            + ' data-action="facility-add-member"'
            + ' data-user-id="' + u.id + '">+</button>'
            + '</div>';
    }).join('');
}

async function facilityDoAddMember(userId) {
    try {
        var response = await fetch('/facility/teams/' + currentFacilityTeamId + '/mitglied/hinzufuegen/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ user_id: userId })
        });
        var data = await response.json();
        if (response.ok) {
            location.reload();
        } else {
            alert(data.error || 'Fehler');
        }
    } catch (error) {
        alert('Fehler: ' + error);
    }
}

async function facilityRemoveMember(teamId, userId, username) {
    if (!confirm('"' + username + '" aus dem Facility-Team entfernen?')) { return; }
    try {
        var response = await fetch('/facility/teams/' + teamId + '/mitglied/entfernen/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrftoken },
            body: JSON.stringify({ user_id: userId })
        });
        if (response.ok) {
            location.reload();
        } else {
            alert('Fehler beim Entfernen');
        }
    } catch (error) {
        alert('Fehler: ' + error);
    }
}

// ---------------------------------------------------------------------------
// Event-Wiring via addEventListener (kein onclick/oninput im HTML)
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', function() {

    // Statische Buttons
    var btnOpenTeam = document.getElementById('btn-open-team-modal');
    if (btnOpenTeam) { btnOpenTeam.addEventListener('click', openTeamModal); }

    var btnSaveTeam = document.getElementById('btn-save-team');
    if (btnSaveTeam) { btnSaveTeam.addEventListener('click', saveTeam); }

    var btnSaveMember = document.getElementById('btn-save-member');
    if (btnSaveMember) { btnSaveMember.addEventListener('click', saveMember); }

    // Member-Suche (oninput ersetzt)
    var memberSearch = document.getElementById('member-search');
    if (memberSearch) {
        memberSearch.addEventListener('input', function() { filterMemberList(this.value); });
    }

    // Facility-Member-Suche
    var facilitySearch = document.getElementById('facility-member-search');
    if (facilitySearch) {
        facilitySearch.addEventListener('input', function() { renderFacilityUserList(this.value); });
    }

    // Event-Delegation fuer dynamisch generierte Liste (selectMember)
    var memberList = document.getElementById('member-list');
    if (memberList) {
        memberList.addEventListener('click', function(e) {
            var el = e.target.closest('[data-action="select-member"]');
            if (el) { selectMember(el); }
        });
    }

    // Event-Delegation fuer Facility-User-Liste (facilityDoAddMember)
    var facilityMemberList = document.getElementById('facility-member-list');
    if (facilityMemberList) {
        facilityMemberList.addEventListener('click', function(e) {
            var btn = e.target.closest('[data-action="facility-add-member"]');
            if (btn) { facilityDoAddMember(btn.dataset.userId); }
        });
    }

    // Event-Delegation fuer Team-Karten (editTeam, deleteTeam, addMemberModal, removeMember)
    document.body.addEventListener('click', function(e) {
        var btn = e.target.closest('[data-action]');
        if (!btn) { return; }

        var action = btn.dataset.action;

        if (action === 'edit-team') {
            editTeam(btn.dataset.teamId);
        } else if (action === 'delete-team') {
            deleteTeam(btn.dataset.teamId, btn.dataset.teamName);
        } else if (action === 'add-member') {
            addMemberModal(btn.dataset.teamId, btn.dataset.teamName);
        } else if (action === 'remove-member') {
            removeMember(btn.dataset.teamId, btn.dataset.userId, btn.dataset.username);
        } else if (action === 'facility-add-member-modal') {
            facilityAddMemberModal(btn.dataset.teamId, btn.dataset.teamName);
        } else if (action === 'facility-remove-member') {
            facilityRemoveMember(btn.dataset.teamId, btn.dataset.userId, btn.dataset.username);
        }
    });
});
