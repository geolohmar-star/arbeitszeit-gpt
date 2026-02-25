# Debugging Script für Railway
from django.contrib.auth.models import User, Group
from arbeitszeit.models import Mitarbeiter

print("=== GRUPPEN CHECK ===")
schichtplaner_gruppe = Group.objects.filter(name='Schichtplaner')
if schichtplaner_gruppe.exists():
    print(f"OK: Gruppe 'Schichtplaner' existiert")
    gruppe = schichtplaner_gruppe.first()
    members = gruppe.user_set.all()
    print(f"Mitglieder ({members.count()}): {[u.username for u in members]}")
else:
    print("FEHLER: Gruppe 'Schichtplaner' existiert NICHT!")

print("\n=== USER CHECK ===")
users = User.objects.filter(is_active=True).exclude(is_superuser=True)
for user in users:
    print(f"\nUser: {user.username}")
    print(f"  - Staff: {user.is_staff}")
    print(f"  - Gruppen: {[g.name for g in user.groups.all()]}")
    
    # Check Mitarbeiter
    if hasattr(user, 'mitarbeiter'):
        ma = user.mitarbeiter
        print(f"  - Mitarbeiter: {ma.vorname} {ma.nachname}")
        print(f"  - Abteilung: '{ma.abteilung}'")
    else:
        print(f"  - Mitarbeiter: KEIN Mitarbeiter-Objekt!")

print("\n=== KONGOS MITARBEITER ===")
kongos_mas = Mitarbeiter.objects.filter(abteilung__icontains='kongos')
print(f"Gefunden: {kongos_mas.count()}")
for ma in kongos_mas:
    print(f"  - {ma.vorname} {ma.nachname} (User: {ma.user.username if ma.user else 'KEIN USER'})")
