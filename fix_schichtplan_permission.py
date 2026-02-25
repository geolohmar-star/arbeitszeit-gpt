"""
Fix: Schichtplan-Zugang Permission für Railway

Vergebe die Permission "schichtplan.schichtplan_zugang" an alle User
die entweder:
- In der Gruppe "Schichtplaner" sind
- Oder die Rolle "schichtplaner" im Mitarbeiter-Objekt haben
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from arbeitszeit.models import Mitarbeiter

print("=" * 70)
print("FIX: Schichtplan-Zugang Permission")
print("=" * 70)

# 1. Permission holen oder erstellen
try:
    from schichtplan.models import Schichtplan
    content_type = ContentType.objects.get_for_model(Schichtplan)
    permission, created = Permission.objects.get_or_create(
        codename='schichtplan_zugang',
        name='Kann Schichtplan-Bereich nutzen',
        content_type=content_type,
    )
    if created:
        print(f"\n✓ Permission erstellt: {permission}")
    else:
        print(f"\n✓ Permission existiert: {permission}")
except Exception as e:
    print(f"\n✗ Fehler beim Erstellen der Permission: {e}")
    exit(1)

# 2. User finden die Schichtplaner sind
users_to_grant = []

# Alle User mit Gruppe "Schichtplaner"
users_in_gruppe = User.objects.filter(groups__name='Schichtplaner')
for user in users_in_gruppe:
    if user not in users_to_grant:
        users_to_grant.append(user)
        print(f"  - {user.username} (Gruppe)")

# Alle User mit Rolle "schichtplaner"
mitarbeiter_schichtplaner = Mitarbeiter.objects.filter(rolle__iexact='schichtplaner')
for ma in mitarbeiter_schichtplaner:
    if ma.user and ma.user not in users_to_grant:
        users_to_grant.append(ma.user)
        print(f"  - {ma.user.username} (Rolle)")

print(f"\nGefunden: {len(users_to_grant)} User die Permission brauchen")

# 3. Permission vergeben
for user in users_to_grant:
    if not user.has_perm('schichtplan.schichtplan_zugang'):
        user.user_permissions.add(permission)
        print(f"✓ Permission vergeben an: {user.username}")
    else:
        print(f"  {user.username} hat Permission bereits")

print("\n" + "=" * 70)
print("FERTIG!")
print("=" * 70)
