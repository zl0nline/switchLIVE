# switchLIVE

Стенд для полевого тестирования коммутаторов через консольный порт.

Текущий MVP ориентирован на Linux workbench, D-Link и Eltex MES2324B/MES2324FB.
Архитектура оставляет транспорт, сессию, vendor-парсеры, тестовый движок,
отчёты и хранение истории раздельными, чтобы добавлять новые семейства
устройств без переписывания core flow.

## Что умеет

- Автоопределение устройства через serial console.
- Авторизация стандартными логинами из `standart_login.txt` с ручным fallback.
- Walk-test портов по профилю устройства.
- Pre-test проверка factory-default состояния для D-Link: если устройство
  выглядит уже настроенным, тест блокируется и предлагается reset/reboot.
- Определение активного порта по MAC-table.
- Link/counters checks.
- PoE probe с нормализованным verdict, независимо от Ethernet verdict.
- Опциональная проверка PoE-камеры по IP.
- SFP/SFP+ probe и DOM metrics, если они доступны на устройстве.
- Опциональный traffic test через `iperf3`.
- HTML/CSV отчёты и SQLite history после полного или частичного теста.
- Безопасная finalization helper: отчёты/history создаются до optional factory reset.
- Debug logging и sanitized debug bundle для багрепортов.

## Установка

На Linux-стенде используйте инсталлятор. Он ставит системные зависимости,
ставит `switchlive` через `pipx`, создаёт рабочие config-файлы из примеров и
добавляет текущего пользователя в serial-группу (`dialout`/`uucp`):

```bash
git clone https://github.com/zl0nline/switchLIVE.git
cd switchLIVE
./scripts/install-linux.sh
```

После добавления в группу нужно перелогиниться или открыть новую сессию через
`newgrp dialout`, иначе Linux ещё не даст доступ к `/dev/ttyUSB*`.

Для разработки можно ставить отдельно в локальное окружение, но на стенде venv
не нужен.

```bash
python3 -m pip install -e ".[dev]"
```

Python 3.10+ обязателен.

## Запуск

```bash
switchlive
```

С явным конфигом:

```bash
switchlive --config switchlive.json
```

Доступные CLI-флаги:

```bash
switchlive --help
```

Быстрая проверка serial console без логина и без запуска полного discovery:

```bash
switchlive console-probe
switchlive console-probe --port /dev/ttyUSB0 --baudrates 9600,115200
switchlive console-probe --output-dir logs/console-probe
```

`console-probe` пробует скорости из `serial.default_baudrates` в конфиге,
по умолчанию `9600` и `115200`, отправляет Enter, читает короткий RX-сэмпл и
показывает `READABLE`, `GARBLED` или `SILENT`. Это полезно, когда непонятно,
на какой скорости коммутатор отдаёт консоль.

## Меню

Интерактивный режим показывает:

- `Определение коммутатора` — serial discovery, login, vendor/model/profile.
- `Тест портов / traffic` — discovery, uplink preflight, полный walk-test и iperf.
- `PoE тест` — отдельная проверка PoE-портов, если они есть в профиле.
- `История тестов` — последние сохранённые запуски по модели/serial/verdict.
- `Настройки` — пока заглушка.
- `Собрать debug bundle` — zip для багрепорта.

## Конфигурация

Создайте рабочие файлы из примеров:

```bash
cp configs/switchlive.example.json switchlive.json
cp configs/standart_login.example.txt standart_login.txt
```

Основные поля `switchlive.json`:

- `standard_login_file`: путь к файлу стандартных логинов.
- `iperf.server_host`: IP хоста с `iperf3 -s`.
- `iperf.server_port`: TCP port iperf, по умолчанию `5201`.
- `iperf.duration_sec`: длительность traffic test.
- `iperf.min_throughput_mbps`: порог WARN по throughput.
- `iperf.max_loss_percent`: порог WARN по loss.
- `timeouts.link_sec`: обычный timeout link/test ожиданий.
- `timeouts.poe_sec`: timeout ожидания PoE-камеры.
- `timeouts.max_sec`: верхний предел расширенного timeout.
- `reports.report_dir`: директория HTML/CSV отчётов.
- `reports.db_path`: SQLite history database.
- `debug`: включает debug logging без CLI-флага `--debug`.
- `serial.default_baudrates`: скорости для `console-probe` и полевой проверки
  консоли, обычно `[9600, 115200]`.

Секреты держите вне git. Файл `standart_login.txt` имеет формат:

```text
username password [enable_password]
```

## Внешние зависимости

- `iperf3` — нужен только для traffic test.
- Доступ к serial device: `/dev/ttyUSB*` или `/dev/ttyACM*`.
- На Linux пользователь должен быть в serial-группе (`dialout` или `uucp`).
- Не запускайте `switchlive` через `sudo`: root может не видеть Python-пакеты,
  поставленные для оператора, и discovery покажет, что `pyserial` не установлен.

Подробная подготовка control host, test host, serial permissions и PoE camera
mode описана в [docs/FIELD_SETUP.md](docs/FIELD_SETUP.md).

## Debug и багрепорты

Включить подробные логи:

```bash
switchlive --debug
```

Лог пишется в:

```text
logs/switchlive-YYYYMMDD-HHMMSS.log
```

Собрать debug bundle и выйти:

```bash
switchlive --debug --bug-report
```

Или выберите `Собрать debug bundle` в меню. Архив создаётся в
`debug-bundles/` и включает:

- `environment.txt`;
- `config.sanitized.json`;
- текущий debug log, если debug был включён;
- последние HTML/CSV отчёты.

Пароли, enable passwords, tokens, API keys и типовые сетевые CLI-секреты
маскируются перед записью в лог/bundle. SQLite history database в bundle не
попадает.

## Отчёты, история и finalization

Console UI сохраняет результаты полного или остановленного оператором теста в:

- SQLite history database для повторного поиска по serial number.
- HTML report для просмотра человеком.
- CSV report для импорта или таблиц.

`finalize_after_test()` пишет отчёты и history до optional factory reset, чтобы
результат теста не терялся при ошибке reset/reload.

Во время walk-test обход идёт автоматически. Чтобы закончить тест и сохранить
отчёт по уже проверенным портам, наберите `q` и нажмите Enter.

## Проверки разработки

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
python3 -m ruff check .
```

## Документация

- [docs/FIELD_SETUP.md](docs/FIELD_SETUP.md) — подготовка стенда.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — архитектура и границы модулей.
- [SUPPORTED.md](SUPPORTED.md) — текущая матрица поддерживаемых устройств.
