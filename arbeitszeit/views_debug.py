"""
Debug-View fuer Railway: Zeigt User-Berechtigungen im Browser
"""
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.contrib.auth.models import User, Group
from arbeitszeit.models import Mitarbeiter


@staff_member_required
def debug_berechtigungen(request):
    """Zeigt Debug-Infos fuer Berechtigungen (nur fuer Staff/Admin)."""
    output = []
    output.append("=" * 70)
    output.append("RAILWAY DEBUG: USER & BERECHTIGUNGEN")
    output.append("=" * 70)

    # 1. Alle User
    output.append("\n### ALLE USER ###\n")
    users = User.objects.all().order_by('username')
    for user in users:
        output.append(f"\nUser: {user.username}")
        output.append(f"  - ID: {user.id}")
        output.append(f"  - Staff: {user.is_staff}")
        output.append(f"  - Superuser: {user.is_superuser}")

        gruppen = list(user.groups.values_list('name', flat=True))
        output.append(f"  - Gruppen: {gruppen if gruppen else 'Keine'}")
        output.append(f"  - hasattr('mitarbeiter'): {hasattr(user, 'mitarbeiter')}")

        if hasattr(user, 'mitarbeiter'):
            try:
                ma = user.mitarbeiter
                output.append(f"  - Mitarbeiter-ID: {ma.id}")
                output.append(f"  - Name: {ma.vorname} {ma.nachname}")
                output.append(f"  - Rolle: '{ma.rolle}'")
                output.append(f"  - Abteilung: '{ma.abteilung}'")

                if ma.rolle:
                    rolle_lower = ma.rolle.strip().lower()
                    ist_sp = rolle_lower == 'schichtplaner'
                    output.append(f"  - Rolle normalisiert: '{rolle_lower}'")
                    output.append(f"  - Match 'schichtplaner': {ist_sp}")

                if ma.abteilung:
                    abt_lower = ma.abteilung.strip().lower()
                    ist_kongos = abt_lower == 'kongos'
                    output.append(f"  - Abteilung normalisiert: '{abt_lower}'")
                    output.append(f"  - Match 'kongos': {ist_kongos}")

            except Exception as e:
                output.append(f"  - FEHLER: {e}")
        else:
            output.append("  - >>> KEIN Mitarbeiter-Objekt! <<<")

    # 2. Mitarbeiter ohne User
    output.append("\n" + "=" * 70)
    output.append("### MITARBEITER OHNE USER ###\n")
    ohne_user = Mitarbeiter.objects.filter(user__isnull=True)
    if ohne_user.exists():
        for ma in ohne_user:
            output.append(f"- {ma.vorname} {ma.nachname} (PN: {ma.personalnummer})")
    else:
        output.append("Keine.")

    # 3. Gruppen
    output.append("\n" + "=" * 70)
    output.append("### DJANGO GRUPPEN ###\n")
    gruppen = Group.objects.all()
    if gruppen.exists():
        for gruppe in gruppen:
            members = gruppe.user_set.all()
            usernames = [u.username for u in members]
            output.append(f"\nGruppe: {gruppe.name}")
            output.append(f"  Mitglieder: {usernames}")
    else:
        output.append("Keine Gruppen.")

    # 4. Zusammenfassung
    output.append("\n" + "=" * 70)
    output.append("### ZUSAMMENFASSUNG ###\n")
    output.append(f"Total User: {users.count()}")
    output.append(f"Mit Mitarbeiter-Objekt: {sum(1 for u in users if hasattr(u, 'mitarbeiter'))}")
    output.append(f"Schichtplaner (Rolle): {Mitarbeiter.objects.filter(rolle__iexact='schichtplaner').count()}")
    output.append(f"Kongos (Abteilung): {Mitarbeiter.objects.filter(abteilung__iexact='kongos').count()}")

    # Als Plain Text zurückgeben
    html = "<html><body><pre>" + "\n".join(output) + "</pre></body></html>"
    return HttpResponse(html, content_type="text/html; charset=utf-8")


@staff_member_required
def fix_schichtplan_permission(request):
    """Vergibt fehlende schichtplan_zugang Permission."""
    from django.contrib.contenttypes.models import ContentType
    from django.contrib.auth.models import Permission
    from schichtplan.models import Schichtplan

    output = []
    output.append("=" * 70)
    output.append("FIX: Schichtplan-Zugang Permission")
    output.append("=" * 70)

    # Permission holen/erstellen
    content_type = ContentType.objects.get_for_model(Schichtplan)
    permission, created = Permission.objects.get_or_create(
        codename='schichtplan_zugang',
        name='Kann Schichtplan-Bereich nutzen',
        content_type=content_type,
    )

    if created:
        output.append("\nPermission erstellt!")
    else:
        output.append("\nPermission existiert bereits.")

    # User finden
    users_to_grant = []

    # Gruppe "Schichtplaner"
    users_in_gruppe = User.objects.filter(groups__name='Schichtplaner')
    for user in users_in_gruppe:
        users_to_grant.append(user)
        output.append(f"  - {user.username} (Gruppe)")

    # Rolle "schichtplaner"
    mitarbeiter_sp = Mitarbeiter.objects.filter(rolle__iexact='schichtplaner')
    for ma in mitarbeiter_sp:
        if ma.user and ma.user not in users_to_grant:
            users_to_grant.append(ma.user)
            output.append(f"  - {ma.user.username} (Rolle)")

    output.append(f"\nGefunden: {len(users_to_grant)} User")

    # Permission vergeben
    for user in users_to_grant:
        if not user.has_perm('schichtplan.schichtplan_zugang'):
            user.user_permissions.add(permission)
            output.append(f"OK: Permission vergeben an {user.username}")
        else:
            output.append(f"  {user.username} hat Permission bereits")

    output.append("\n" + "=" * 70)
    output.append("FERTIG! Testen Sie jetzt den Schichtplan-Zugang.")
    output.append("=" * 70)

    html = "<html><body><pre>" + "\n".join(output) + "</pre></body></html>"
    return HttpResponse(html, content_type="text/html; charset=utf-8")
