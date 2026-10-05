from django.db import migrations, models


def _field():
    field = models.JSONField(default=dict, blank=True)
    field.set_attributes_from_name('mapping')
    return field


def add_mapping(apps, schema_editor):
    """Add the column in place.

    Django's SQLite AddField rebuilds the table, and the rebuilt table's AUTOINCREMENT counter restarts
    at MAX(id): a deleted connector's id could be issued again and an empty table loses its high-water.
    ALTER TABLE ADD COLUMN keeps the table and its sqlite_sequence row untouched. Other databases add
    the column in place already, so they use the regular schema editor.
    """
    model = apps.get_model('connectors', 'Connector')
    if schema_editor.connection.vendor == 'sqlite':
        schema_editor.execute(
            'ALTER TABLE "connectors_connector" ADD COLUMN "mapping" text NOT NULL DEFAULT \'{}\' '
            'CHECK ((JSON_VALID("mapping") OR "mapping" IS NULL))')
    else:
        schema_editor.add_field(model, _field())


def remove_mapping(apps, schema_editor):
    model = apps.get_model('connectors', 'Connector')
    if schema_editor.connection.vendor == 'sqlite':
        schema_editor.execute('ALTER TABLE "connectors_connector" DROP COLUMN "mapping"')
    else:
        schema_editor.remove_field(model, _field())


class Migration(migrations.Migration):

    dependencies = [
        ('connectors', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='connector',
                    name='mapping',
                    field=models.JSONField(blank=True, default=dict),
                ),
            ],
            database_operations=[migrations.RunPython(add_mapping, remove_mapping)],
        ),
    ]
