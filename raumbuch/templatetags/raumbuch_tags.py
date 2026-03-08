from django import template

register = template.Library()

# Farben fuer Netzwerk-Komponenten-Typen
TYP_FARBEN = {
    "core_switch":          "#6366f1",   # Indigo
    "distribution_switch":  "#8b5cf6",   # Violett
    "access_switch":        "#a78bfa",   # Hellviolett
    "patch_panel":          "#64748b",   # Schiefergrau
    "glasfaser_verteiler":  "#f59e0b",   # Amber
    "firewall":             "#ef4444",   # Rot
    "router":               "#f97316",   # Orange
    "server":               "#10b981",   # Gruen
    "nas":                  "#059669",   # Dunkelgruen
    "ups":                  "#0ea5e9",   # Blau
    "kvm":                  "#6b7280",   # Grau
    "accesspoint":          "#06b6d4",   # Cyan
    "sonstiges":            "#374151",   # Dunkelgrau
}


@register.filter
def typ_farbe(typ):
    """Gibt die Hintergrundfarbe fuer einen NetzwerkKomponente-Typ zurueck."""
    return TYP_FARBEN.get(typ, "#374151")
