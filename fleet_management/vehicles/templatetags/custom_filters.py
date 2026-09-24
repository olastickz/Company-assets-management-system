import builtins
from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Get an item from a dictionary using dot notation in templates."""
    if dictionary is None:
        return 0
    return dictionary.get(key, 0)

@register.filter
def abs(value):
    """Return the absolute value of a number in templates."""
    try:
        return builtins.abs(value)
    except Exception:
        return value
