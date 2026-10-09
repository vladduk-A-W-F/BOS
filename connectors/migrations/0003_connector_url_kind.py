from django.db import migrations, models


class Migration(migrations.Migration):
    """A new choice «Таблиця за посиланням». Choices live only in Django's state: no table is rebuilt,
    so SQLite keeps its AUTOINCREMENT high-water (see 0002)."""

    dependencies = [('connectors', '0002_connector_mapping')]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.AlterField(
                model_name='connector', name='kind',
                field=models.CharField(choices=[('csv', 'Excel / CSV'), ('google_sheets', 'Google Таблиці'),
                                                ('url', 'Таблиця за посиланням')], max_length=20))],
            database_operations=[]),
    ]
