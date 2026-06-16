# switchLIVE

Стенд для тестирования коммутаторов и других консольных устройств.

## Установка

```bash
# Клонировать репозиторий
git clone https://github.com/zl0nline/switchLIVE.git
cd switchLIVE

# Виртуальное окружение
python3 -m venv .venv
. .venv/bin/activate

# Установить в режиме разработки
pip install -e ".[dev]"
```

## Запуск

```bash
switchlive
```

или

```bash
python -m switchlive
```

## Внешние зависимости

- `iperf3` — должен быть установлен в системе и доступен в PATH
- Linux serial access: пользователь должен иметь права на `/dev/ttyUSB*` или `/dev/ttyACM*`

## Конфигурация

```bash
cp configs/switchlive.example.json switchlive.json
cp configs/standart_login.example.txt standart_login.txt
```

См. `configs/switchlive.example.json`.

## Подготовка стенда

Пошаговая инструкция для control host, test host, serial permissions,
iperf3 и PoE camera mode: [docs/FIELD_SETUP.md](docs/FIELD_SETUP.md).

## Архитектура

См. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
