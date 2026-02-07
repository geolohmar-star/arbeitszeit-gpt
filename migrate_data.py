import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core import serializers
from django.apps import apps

# Alle Models außer ContentType und Permission
excluded_models = ['contenttypes.contenttype', 'auth.permission']
all_models = []

for model in apps.get_models():
    label = f"{model._meta.app_label}.{model._meta.model_name}"
    if label not in excluded_models:
        all_models.append(model)

# Exportiere Daten
data = serializers.serialize('json', 
    [obj for model in all_models for obj in model.objects.all()],
    indent=2,
    use_natural_foreign_keys=True,
    use_natural_primary_keys=True
)

# Speichere als UTF-8
with open('data_clean.json', 'w', encoding='utf-8') as f:
    f.write(data)

print("Export erfolgreich!")