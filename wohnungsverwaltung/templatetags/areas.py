from django import template

from wohnungsverwaltung.formatting import format_area

register = template.Library()
register.filter("area", format_area)
