from django import template

from wohnungsverwaltung.formatting import format_room_count

register = template.Library()
register.filter("room_count", format_room_count)
