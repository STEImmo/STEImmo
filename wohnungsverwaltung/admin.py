"""Keep account and permission management in the UIkit management area."""

from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

for model in (get_user_model(), Group):
    try:
        admin.site.unregister(model)
    except NotRegistered:
        pass
