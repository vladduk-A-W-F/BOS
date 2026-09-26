# A10 control: фактичний стан

A09 supervisor фактично запущено через перевірений HTTPS; контрольного endpoint немає. `A10_CONTROL_BEFORE.json` фіксує очікуваний red. Supervisor і його Caddy/Waitress діти завершилися звичайно з exit 0.

Створено окремі tmp-only drafts `a10_control_draft/scripts/maintenance_control.py` та `a10_control_draft/scripts/lifecycle_server.py`. A09 frozen файл SHA e21fa92d… не змінювався. Прототип має Unix transport, incarnation nonce, UUID/root inode, peer UID/PID, one-use request IDs, typed live QuiescenceLease, same-generation release/recovery та відмову запускати original N після active pointer.

Перший реальний subprocess test зупинився ДО bind і створення будь-яких WSGI дітей: `socket.socket(AF_UNIX, SOCK_STREAM)` повернув `PermissionError: [Errno 1] Operation not permitted`. Жоден lease не видано, positive IPC/quiescence/resume не перевірено. `A10_CONTROL_ACTUAL.log` і `A10_CONTROL_ACTUAL_RESULT.json` є доказом цієї межі, а не green acceptance.

Waitress drain runner окремо фактично перевірений agent a09_server_review: `A10_DRAIN_ACTUAL_1.json`, frozen runner SHA f25b421a…. Цей успіх не підміняє відсутній IPC proof. Source review показав, а його actual baseline підтвердив, що A09 shutdown може повертати True і process exit 0 при живому worker; A10 lease має вимагати фактичний child stdout drain receipt, нуль queued/active/workers, closed sockets та exit 0 без force.

Root отримав blocker і обирає доступне середовище або окремо погоджений transport. Не застосовано bypass syscall restriction; gate 7/9, backup/restore/upgrade та production не позначені виконаними.
