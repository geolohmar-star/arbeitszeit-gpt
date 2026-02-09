"""
Template Tags für Schichtplan-App

Macht die ist_schichtplaner() Funktion in Templates verfügbar.
"""
from django import template

register = template.Library()

@register.filter(name='ist_schichtplaner')
def ist_schichtplaner_filter(user):
    """
    Template-Filter: Prüft ob User Schichtplaner ist
    
    Verwendung in Templates:
    {% load schichtplan_tags %}
    {% if user|ist_schichtplaner %}
        ...
    {% endif %}
    """
    # Importiere die bestehende Funktion aus views.py
    from schichtplan.views import ist_schichtplaner
    return ist_schichtplaner(user)
