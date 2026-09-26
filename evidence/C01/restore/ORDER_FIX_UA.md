# C01 native: порядок синтетичного наповнення

Перший actual TLS/native run (`native-1.json`) завершив12 сценаріїв включно з чистим відновленням53 таблиць, точними байтами БД і перевіркою початкового імпорту; потім AssertionError на етапі B03 whole-snapshot. Продуктові backup/restore файли не змінено.

Source diagnosis: `snapshot.home.tasks` входить у незмінний повний B03 snapshot. Root помилково додавав нові Task після його збереження. Порівняння до/після відновлення тому мало різні моменти початкового стану. Це помилка нового тестового setup; саме red без traceback не доводить втрату даних.

Мінімальна зміна: C01 наповнення переміщено перед B03 наповненням, обидва після імпорту. Усі старі14 assertions і literal whole-snapshot comparisons залишено; жодного поля не вилучено з порівняння. Другий actual run має підтвердити виправлення. Попередній source та raw report/log збережено.

Другий actual run завершено:16/16, exit0. B03 повний snapshot і всі7 receipts literal-equal;4Task,6Task proposals, повна історія/active/archive literal-equal. Читання власних receipts із нової сесії успішне, виконання старої сесії403, повтори не додали ефектів. Це ізольований checkpoint; canonical full24 ще попереду.
