"""
SCHNELL-SETUP: Sachbearbeiter erstellen

Führe dieses Script in der Django Shell aus:
python manage.py shell
"""

from django.contrib.auth.models import User
from arbeitszeit.models import Mitarbeiter
from datetime import date

def sachbearbeiter_erstellen(
    username,
    email,
    vorname,
    nachname,
    personalnummer,
    abteilung='HR',
    standort='siegburg',
    password='SachbearbeiterTest123'
):
    """Erstellt einen neuen Sachbearbeiter"""
    
    # 1. User erstellen
    if User.objects.filter(username=username).exists():
        print(f"❌ User '{username}' existiert bereits!")
        return None
    
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=vorname,
        last_name=nachname
    )
    user.is_staff = True  # Zugriff auf /verwaltung/
    user.is_superuser = False  # KEIN Zugriff auf /admin/
    user.save()
    print(f"✓ User '{username}' erstellt")
    
    # 2. Mitarbeiter erstellen
    mitarbeiter = Mitarbeiter.objects.create(
        user=user,
        personalnummer=personalnummer,
        vorname=vorname,
        nachname=nachname,
        abteilung=abteilung,
        standort=standort,
        eintrittsdatum=date.today(),
        rolle='sachbearbeiter',
        aktiv=True
    )
    print(f"✓ Mitarbeiter-Profil erstellt")
    print(f"✓ Rolle: Sachbearbeiter")
    print(f"\n🎉 Sachbearbeiter erfolgreich erstellt!")
    print(f"   Username: {username}")
    print(f"   Passwort: {password}")
    print(f"   Zugriff: http://127.0.0.1:8000/verwaltung/")
    
    return user


def user_zu_sachbearbeiter_machen(username):
    """Macht einen bestehenden User zum Sachbearbeiter"""
    
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"❌ User '{username}' nicht gefunden!")
        return None
    
    # User-Berechtigung setzen
    user.is_staff = True
    user.is_superuser = False
    user.save()
    print(f"✓ User-Berechtigungen gesetzt")
    
    # Mitarbeiter-Rolle setzen
    try:
        mitarbeiter = user.mitarbeiter
        mitarbeiter.rolle = 'sachbearbeiter'
        mitarbeiter.save()
        print(f"✓ Rolle auf 'Sachbearbeiter' gesetzt")
        print(f"\n🎉 {user.get_full_name()} ist jetzt Sachbearbeiter!")
        print(f"   Zugriff: http://127.0.0.1:8000/verwaltung/")
        return user
    except Mitarbeiter.DoesNotExist:
        print(f"❌ Kein Mitarbeiter-Profil für User '{username}' gefunden!")
        return None


def sachbearbeiter_zurueckstufen(username):
    """Stuft Sachbearbeiter zurück zu normalem Mitarbeiter"""
    
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        print(f"❌ User '{username}' nicht gefunden!")
        return None
    
    user.is_staff = False
    user.save()
    
    try:
        mitarbeiter = user.mitarbeiter
        mitarbeiter.rolle = 'mitarbeiter'
        mitarbeiter.save()
        print(f"✓ {user.get_full_name()} ist jetzt normaler Mitarbeiter")
        return user
    except Mitarbeiter.DoesNotExist:
        print(f"❌ Kein Mitarbeiter-Profil gefunden!")
        return None


def alle_sachbearbeiter_anzeigen():
    """Zeigt alle Sachbearbeiter an"""
    
    sachbearbeiter = Mitarbeiter.objects.filter(rolle='sachbearbeiter', aktiv=True)
    
    if not sachbearbeiter.exists():
        print("Keine Sachbearbeiter gefunden.")
        return
    
    print(f"\n📋 Sachbearbeiter ({sachbearbeiter.count()}):")
    print("=" * 60)
    for sb in sachbearbeiter:
        print(f"  {sb.vollname}")
        print(f"    → Username: {sb.user.username}")
        print(f"    → Personal-Nr: {sb.personalnummer}")
        print(f"    → Abteilung: {sb.abteilung}")
        print(f"    → Standort: {sb.get_standort_display()}")
        print()


# ============================================
# BEISPIEL-VERWENDUNG:
# ============================================

# Neuen Sachbearbeiter erstellen:
# sachbearbeiter_erstellen(
#     username='anna.schmidt',
#     email='anna.schmidt@firma.de',
#     vorname='Anna',
#     nachname='Schmidt',
#     personalnummer='SB001',
#     abteilung='HR',
#     standort='siegburg'
# )

# Bestehenden User zum Sachbearbeiter machen:
# user_zu_sachbearbeiter_machen('max.mueller')

# Sachbearbeiter zurückstufen:
# sachbearbeiter_zurueckstufen('anna.schmidt')

# Alle Sachbearbeiter anzeigen:
# alle_sachbearbeiter_anzeigen()


print("\n" + "="*60)
print("SACHBEARBEITER MANAGEMENT - Funktionen geladen")
print("="*60)
print("\n📚 Verfügbare Funktionen:")
print("  1. sachbearbeiter_erstellen(username, email, vorname, nachname, personalnummer)")
print("  2. user_zu_sachbearbeiter_machen(username)")
print("  3. sachbearbeiter_zurueckstufen(username)")
print("  4. alle_sachbearbeiter_anzeigen()")
print("\n💡 Beispiel:")
print("  >>> sachbearbeiter_erstellen('anna.schmidt', 'anna@firma.de', 'Anna', 'Schmidt', 'SB001')")
print("="*60 + "\n")
