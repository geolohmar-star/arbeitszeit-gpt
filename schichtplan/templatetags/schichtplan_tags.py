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
    # Prueft die schichtplan_zugang Permission (nicht mehr nur Gruppe/is_staff)
    from schichtplan.views import hat_schichtplan_zugang
    return hat_schichtplan_zugang(user)
