from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """
    Ermöglicht dict[key] Zugriff in Templates.
    
    Usage: {{ monate_dict|get_item:1 }}
    """
    if dictionary is None:
        return None
    return dictionary.get(key)