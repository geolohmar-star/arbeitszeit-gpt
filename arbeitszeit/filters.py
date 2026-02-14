"""
Django-Filter fuer Arbeitszeitverwaltung
"""
import django_filters
from django.db import models
from .models import Arbeitszeitvereinbarung


class ArbeitszeitvereinbarungFilter(django_filters.FilterSet):
    """Filter fuer die Admin-Vereinbarungsuebersicht."""

    suche = django_filters.CharFilter(
        method="filter_suche",
        label="Mitarbeiter suchen",
    )
    status = django_filters.ChoiceFilter(
        choices=Arbeitszeitvereinbarung.STATUS_CHOICES,
        empty_label="Alle Status",
        label="Status",
    )
    antragsart = django_filters.ChoiceFilter(
        choices=Arbeitszeitvereinbarung.ANTRAGSART_CHOICES,
        empty_label="Alle Antragsarten",
        label="Antragsart",
    )

    class Meta:
        model = Arbeitszeitvereinbarung
        fields = ["status", "antragsart"]

    def filter_suche(self, queryset, name, value):
        """Volltextsuche ueber Mitarbeiter-Felder."""
        if not value:
            return queryset
        return queryset.filter(
            models.Q(mitarbeiter__vorname__icontains=value)
            | models.Q(mitarbeiter__nachname__icontains=value)
            | models.Q(mitarbeiter__personalnummer__icontains=value)
        )
