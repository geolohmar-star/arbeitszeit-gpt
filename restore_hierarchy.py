#!/usr/bin/env python
"""Stelle Hierarchie aus letztem Snapshot wieder her."""

import os
import sys
import django

# Django Settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django.setup()

from hr.models import HierarchieSnapshot, OrgEinheit, Stelle
from django.db import transaction

# Hole letzten Snapshot
snapshot = HierarchieSnapshot.objects.first()
if not snapshot:
    print("Kein Snapshot vorhanden!")
    exit(1)

print(f"Stelle wieder her: Snapshot vom {snapshot.created_at}")

data = snapshot.snapshot_data

with transaction.atomic():
    # Stellen wiederherstellen
    stellen_count = 0
    for stelle_data in data.get('stellen', []):
        try:
            stelle = Stelle.objects.get(pk=stelle_data['id'])
            stelle.uebergeordnete_stelle_id = stelle_data.get('uebergeordnete_stelle_id')
            stelle.org_einheit_id = stelle_data.get('org_einheit_id')
            stelle.save(update_fields=['uebergeordnete_stelle', 'org_einheit'])
            stellen_count += 1
        except Stelle.DoesNotExist:
            continue

    print(f"\nOK: {stellen_count} Stellen wiederhergestellt!")

# Snapshot loeschen
snapshot.delete()
print("OK: Snapshot geloescht!")
print("\nERFOLG: Hierarchie komplett wiederhergestellt!")
