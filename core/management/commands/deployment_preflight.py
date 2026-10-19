from django.core.management import BaseCommand, CommandError, call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Prüft Produktionssettings und meldet ausstehende Migrationen mit Exit-Code 3."
    requires_system_checks = []

    def handle(self, *args, **options):
        call_command(
            "check", deploy=True, fail_level="WARNING", stdout=self.stdout, stderr=self.stderr
        )
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            raise CommandError("Schemaänderungen: kein automatischer Image-Rollback.", returncode=3)
        self.stdout.write("Keine Schemaänderungen: automatischer Image-Rollback ist möglich.")
