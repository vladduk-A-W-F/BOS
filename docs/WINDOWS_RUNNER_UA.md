# BoS · Windows runner

Статус: **НЕ ЗАПУЩЕНО — немає підтвердженого Windows runner і адреси репозиторію BoS**. Обов’язковий job `tests-windows` залишається в конвеєрі як `when: manual`, `allow_failure: false`. Він не вважається пройденим до справжнього запуску.

Передумови на окремій тестовій Windows-машині: Git, Python 3.12 з launcher `py`, PowerShell 7, GitLab Runner та Docker з Linux-контейнерами, доступний обліковому запису служби runner. Робочі бази BoS на цю машину не копіювати. Потрібен доступ до GitLab-проєкту: Settings → CI/CD → Runners → New project runner, тег `windows`, executor `shell`, shell `pwsh`. Отриману URL і runner authentication token використовувати тільки на цій машині; не надсилати токен у чат і не комітити його.

Після завантаження `gitlab-runner.exe` до робочого каталогу runner виконайте три команди в адміністративному PowerShell. Першу скопіюйте зі сторінки створення runner і додайте параметри executor/shell; значення нижче є позначеннями полів, а не готовими обліковими даними:

```powershell
.\gitlab-runner.exe register --non-interactive --url "URL_З_ПРОЄКТУ" --token "TOKEN_З_ПРОЄКТУ" --executor "shell" --shell "pwsh"
.\gitlab-runner.exe install
.\gitlab-runner.exe start
```

Служба runner повинна бачити Python, Git і Docker. Якщо Docker Desktop доступний лише іншому обліковому запису, спочатку налаштуйте доступ служби; успішна реєстрація runner сама по собі не доводить готовність середовища. Встановіть `concurrent = 1` для цього тестового runner; додатково job має `resource_group` для PostgreSQL.

У конвеєрі натисніть запуск `tests-windows`. Job створить нове `.venv-ci`, встановить залежності, підніме одноразовий `postgres:16` і виконає `verify.ps1 -Suite windows`. Критерії 1–3 і 6 перевіряються і на SQLite, і на PostgreSQL. Відсутні інваріанти або E2E залишать результат червоним. Після додавання постійного runner ручний запуск можна замінити автоматичним без ослаблення перевірок.

Результат: `evidence/ci/windows/report.json` та журнали дочірніх перевірок. Агрегатор перевіряє Windows, Python 3.12, набір критеріїв, SHA джерел і поточний pipeline. Артефакт іншої версії не підходить.

Офіційні інструкції: [установка GitLab Runner на Windows](https://docs.gitlab.com/runner/install/windows/) і [реєстрація runner](https://docs.gitlab.com/runner/register/).
