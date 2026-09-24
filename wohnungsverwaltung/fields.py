from django.db import models


class PostgreSQLEnumField(models.CharField):
    """A CharField backed by a named PostgreSQL enum type."""

    def __init__(self, *args, enum_type: str, **kwargs):
        self.enum_type = enum_type
        super().__init__(*args, **kwargs)

    def db_type(self, connection):
        if connection.vendor == "postgresql":
            return self.enum_type
        return super().db_type(connection)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs["enum_type"] = self.enum_type
        return name, path, args, kwargs
