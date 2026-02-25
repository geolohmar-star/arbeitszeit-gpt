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
