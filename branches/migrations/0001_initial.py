import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Начальная схема оргструктуры.

    Написана вручную: на неё уже ссылаются tasks.0004_task_branch,
    finance.0003_transaction_branch и employees.0003_employee_branch,
    поэтому makemigrations не мог собрать граф без неё.
    """

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Branch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('code', models.CharField(db_index=True, max_length=50, unique=True)),
                ('type', models.CharField(choices=[('headquarters', 'Центральний офіс'), ('department', 'Підрозділ'), ('regional', 'Регіональний філіал'), ('mobile', 'Мобільний офіс'), ('foreign', 'Іноземний філіал')], db_index=True, default='regional', max_length=20)),
                ('lat', models.FloatField(blank=True, null=True)),
                ('lng', models.FloatField(blank=True, null=True)),
                ('status', models.CharField(choices=[('green', 'Норма'), ('yellow', 'Відхилення'), ('red', 'Простій / невиконання')], db_index=True, default='green', max_length=10)),
                ('employee_count', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='branches.branch')),
            ],
            options={
                'ordering': ['type', 'name'],
                'verbose_name_plural': 'branches',
            },
        ),
    ]
