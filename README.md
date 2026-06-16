# switchLIVE

Стенд для тестирования коммутаторов и других консольных устройств.

## Установка

```bash
# Клонировать репозиторий
git clone https://github.com/zl0nline/switchLIVE.git
cd switchLIVE

# Установить в режиме разработки
pip install -e ".[dev]"

# Опционально: красивый UI
pip install -e ".[ui]"
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

## Конфигурация

См. `configs/switchlive.example.yaml`.

## Архитектура

См. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
