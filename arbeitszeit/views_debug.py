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
def fix_schichtplan_permission_komplett(request):
    """Vergibt schichtplan_zugang Permission an Schichtplaner UND Kongos-Mitarbeiter."""
    output = []
    output.append("=" * 70)
    output.append("FIX: Schichtplan-Zugang fuer Schichtplaner + Kongos")
    output.append("=" * 70)

    try:
        from django.contrib.contenttypes.models import ContentType
        from django.contrib.auth.models import Permission
        from schichtplan.models import Schichtplan

        # Permission holen
        output.append("\n1. Permission laden...")
        content_type = ContentType.objects.get_for_model(Schichtplan)
        permission = Permission.objects.get(
            codename='schichtplan_zugang',
            content_type=content_type,
        )
        output.append(f"   -> Permission gefunden (ID: {permission.id}, Name: '{permission.name}')")

        # User sammeln
        output.append("\n2. User mit Schichtplan-Berechtigung suchen...")
        users_to_grant = []

        # A) Gruppe "Schichtplaner"
        users_in_gruppe = User.objects.filter(groups__name='Schichtplaner')
        output.append(f"\n   A) {users_in_gruppe.count()} User in Gruppe 'Schichtplaner'")
        for user in users_in_gruppe:
            if user not in users_to_grant:
                users_to_grant.append(user)
                output.append(f"      - {user.username} (Gruppe)")

        # B) Rolle "schichtplaner"
        mitarbeiter_sp = Mitarbeiter.objects.filter(rolle__iexact='schichtplaner')
        output.append(f"\n   B) {mitarbeiter_sp.count()} Mitarbeiter mit Rolle 'schichtplaner'")
        for ma in mitarbeiter_sp:
            try:
                if ma.user:
                    if ma.user not in users_to_grant:
                        users_to_grant.append(ma.user)
                        output.append(f"      - {ma.user.username} (Rolle)")
                else:
                    output.append(f"      - {ma.vorname} {ma.nachname} (kein User)")
            except Exception as e:
                output.append(f"      - FEHLER bei MA {ma.id}: {e}")

        # C) Abteilung "Kongos" (case-insensitive)
        mitarbeiter_kongos = Mitarbeiter.objects.filter(abteilung__iexact='kongos', aktiv=True)
        output.append(f"\n   C) {mitarbeiter_kongos.count()} aktive Mitarbeiter in Abteilung 'Kongos'")
        for ma in mitarbeiter_kongos:
            try:
                if ma.user:
                    if ma.user not in users_to_grant:
                        users_to_grant.append(ma.user)
                        output.append(f"      - {ma.user.username} (Kongos: {ma.vorname} {ma.nachname})")
                else:
                    output.append(f"      - {ma.vorname} {ma.nachname} (kein User)")
            except Exception as e:
                output.append(f"      - FEHLER bei MA {ma.id}: {e}")

        output.append(f"\n3. Gefunden: {len(users_to_grant)} User insgesamt")

        # Permission vergeben
        output.append("\n4. Permission vergeben...")
        granted_count = 0
        already_had_count = 0
        for user in users_to_grant:
            try:
                if not user.has_perm('schichtplan.schichtplan_zugang'):
                    user.user_permissions.add(permission)
                    output.append(f"   OK: Permission vergeben an {user.username}")
                    granted_count += 1
                else:
                    output.append(f"   --: {user.username} hat Permission bereits")
                    already_had_count += 1
            except Exception as e:
                output.append(f"   FEHLER bei {user.username}: {e}")

        output.append(f"\n   -> Neu vergeben: {granted_count}")
        output.append(f"   -> Hatten bereits: {already_had_count}")

        output.append("\n" + "=" * 70)
        output.append("FERTIG!")
        output.append("Schichtplaner + Kongos-Mitarbeiter koennen jetzt zugreifen:")
        output.append("https://arbeitszeit-gpt.up.railway.app/schichtplan/")
        output.append("=" * 70)

    except Exception as e:
        import traceback
        output.append("\n\n!!! KRITISCHER FEHLER !!!\n")
        output.append(f"Exception: {type(e).__name__}")
        output.append(f"Message: {str(e)}")
        output.append("\nTraceback:")
        output.append(traceback.format_exc())

    html = "<html><body><pre>" + "\n".join(output) + "</pre></body></html>"
    return HttpResponse(html, content_type="text/html; charset=utf-8")
