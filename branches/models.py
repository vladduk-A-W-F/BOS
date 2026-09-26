from django.db import models


class Branch(models.Model):
    """Узел организационной структуры — офис, управление, регион, филиал.

    Модель намеренно generic: никакой pasport-специфики здесь нет.
    Структура задаётся ДАННЫМИ (сид/админка), а не кодом — поэтому та же
    модель обслуживает и коммерческую версию с другой оргструктурой.
    """

    TYPE_CHOICES = [
        ('headquarters', 'Центральний офіс'),
        ('department',   'Підрозділ'),
        ('regional',     'Регіональний філіал'),
        ('mobile',       'Мобільний офіс'),
        ('foreign',      'Іноземний філіал'),
    ]
    STATUS_CHOICES = [
        ('green',  'Норма'),
        ('yellow', 'Відхилення'),
        ('red',    'Простій / невиконання'),
    ]

    # Отображаемое название — "Київське управління"
    name = models.CharField(max_length=200)

    # Коротка назва для дерева й вузьких місць інтерфейсу — місто або
    # ключове слово. Порожнє поле = показуємо повну назву (fallback у фронті).
    short_name = models.CharField(max_length=60, blank=True, default='')

    # Машинный ключ узла — используется фронтом как стабильный id в дереве
    code = models.CharField(max_length=50, unique=True, db_index=True)

    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='regional', db_index=True)

    # Self-FK: дерево любой глубины. null = корень структуры.
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.CASCADE, related_name='children',
    )

    # Координаты для карты. null = узел на карте не показывается (напр. виртуальный).
    lat = models.FloatField(null=True, blank=True)
    lng = models.FloatField(null=True, blank=True)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='green', db_index=True)

    # Денормализованный счётчик — показывается в дереве. Реальные Employee
    # могут быть не заведены (демо-режим), поэтому это отдельное поле, а не count().
    employee_count = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['type', 'name']
        verbose_name_plural = 'branches'

    def __str__(self):
        return f'{self.name} ({self.code})'

    def descendant_ids(self):
        """ID этого узла + всех потомков — для агрегации KPI по поддереву.

        Обходим в питоне, а не рекурсивным SQL: дерево оргструктуры маленькое
        (десятки узлов), зато код переносим на любую БД.
        """
        ids = [self.id]
        stack = list(self.children.all())
        while stack:
            node = stack.pop()
            ids.append(node.id)
            stack.extend(node.children.all())
        return ids
