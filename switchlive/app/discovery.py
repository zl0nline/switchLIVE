"""Device discovery: автопоиск подключённого устройства по COM-портам.

Логика:
1. Получить список доступных COM-портов.
2. Для каждого порта:
   a. Открыть serial transport.
   b. Создать CLISession.
   c. Попробовать логин (стандартные пароли, затем ручной ввод).
   d. Отключить пейджер.
   e. Прогнать все зарегистрированные детекторы.
   f. Если найден — вернуть результат.
   g. Если не найден — закрыть, следующий порт.
3. Вернуть результат: найдено / не найдено / ошибка.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from switchlive.core.credentials import Credentials, load_standard_logins
from switchlive.core.errors import SessionError, TransportError
from switchlive.core.models import DeviceIdentity
from switchlive.devices.base import DeviceAdapter, DeviceDetector
from switchlive.devices.dlink import DLinkAdapter, DLinkDetector  # noqa: F401 — регистрация
from switchlive.devices.eltex import EltexAdapter, EltexDetector  # noqa: F401 — регистрация
from switchlive.devices.registry import get_all_detectors
from switchlive.sessions.cli_session import CLISession
from switchlive.transports.serial import SerialTransport, is_pyserial_available, list_serial_ports

log = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    """Результат автопоиска устройства."""

    found: bool
    identity: DeviceIdentity | None = None
    adapter: DeviceAdapter | None = None
    session: CLISession | None = None
    port: str = ""
    error: str = ""
    auth_method: str = ""  # "standard", "manual", "none"


def run_discovery(
    standard_logins_path: str = "standart_login.txt",
    manual_credential_callback=None,
    progress_callback=None,
) -> DiscoveryResult:
    """Автопоиск устройства по всем COM-портам.

    Args:
        standard_logins_path: путь к файлу стандартных логинов.
        manual_credential_callback: функция(credentials_list) -> Credentials | None
            для запроса логина/пароля у оператора.
        progress_callback: функция(message: str) — для UI обновлений.

    Returns:
        DiscoveryResult с найденным устройством или ошибкой.
    """
    def _progress(msg: str) -> None:
        log.info("Discovery: %s", msg)
        if progress_callback:
            progress_callback(msg)

    # Загрузить стандартные логины
    standard_creds = load_standard_logins(standard_logins_path)
    _progress(f"Загружено стандартных логинов: {len(standard_creds)}")

    # Получить список портов
    ports = list_serial_ports()
    if not ports:
        if not is_pyserial_available():
            error = (
                "pyserial не установлен в текущем Python-окружении. "
                "Запустите scripts/install-linux.sh и затем switchlive без sudo."
            )
            _progress(error)
            return DiscoveryResult(found=False, error=error)
        _progress("COM-порты не найдены")
        return DiscoveryResult(
            found=False,
            error=(
                "Нет доступных COM-портов. Проверьте USB-console адаптер, "
                "группу dialout/uucp и перезапустите сессию пользователя; sudo не нужен."
            ),
        )

    _progress(f"Найдено COM-портов: {len(ports)}")

    # Получить все детекторы
    detectors = get_all_detectors()
    _progress(f"Зарегистрировано детекторов: {len(detectors)}")

    for port_info in ports:
        port_name = port_info.name
        _progress(f"Проверка порта {port_name}...")

        result = _try_port(
            port_name,
            standard_creds,
            manual_credential_callback,
            detectors,
            _progress,
        )

        if result and result.found:
            return result

    _progress("Устройство не найдено ни на одном порту")
    return DiscoveryResult(found=False, error="Устройство не обнаружено")


def _try_port(
    port_name: str,
    standard_creds: list[Credentials],
    manual_credential_callback,
    detectors: list[DeviceDetector],
    progress,
) -> DiscoveryResult | None:
    """Попробовать найти устройство на конкретном порту."""
    transport = SerialTransport(port=port_name)

    try:
        transport.open()
    except TransportError as e:
        progress(f"  Не удалось открыть {port_name}: {e}")
        return None

    # Попробовать разные бодрейты (9600 — стандарт, но иногда 115200)
    for baudrate in (9600, 115200):
        if baudrate != 9600:
            transport.close()
            transport = SerialTransport(port=port_name, baudrate=baudrate)
            try:
                transport.open()
            except TransportError:
                continue

        session = CLISession(transport, vendor="dlink")

        # Попытки логина
        auth_method = _try_login(session, standard_creds, manual_credential_callback, progress)

        if auth_method is None:
            continue  # не удалось войти на этом бодрейте

        # Прогнать детекторы
        for detector in detectors:
            try:
                if detector.can_detect(session):
                    progress(f"  Детектор {type(detector).__name__}: совпадение!")
                    identity = detector.identify(session)
                    adapter = _create_adapter(identity)
                    session.vendor = adapter.profile.prompt_vendor
                    _disable_paging(session, adapter, progress)
                    return DiscoveryResult(
                        found=True,
                        identity=identity,
                        adapter=adapter,
                        session=session,
                        port=port_name,
                        auth_method=auth_method,
                    )
            except Exception as e:
                progress(f"  Детектор {type(detector).__name__}: ошибка — {e}")

        # Ни один детектор не сработал
        progress(f"  Устройство на {port_name} не распознано (ни один детектор)")

    transport.close()
    return None


def _try_login(
    session: CLISession,
    standard_creds: list[Credentials],
    manual_callback,
    progress,
) -> str | None:
    """Попробовать войти на устройстве.

    Возвращает метод авторизации ("none", "standard", "manual") или None.
    """
    # 1. Без авторизации
    try:
        if session.login(Credentials()):
            progress("  Логин не требуется")
            return "none"
    except SessionError:
        pass

    if not session.transcript.strip():
        progress("  Нет ответа от консоли на этом baudrate")
        return None

    # 2. Стандартные логины
    for cred in standard_creds:
        try:
            if session.login(cred):
                progress(f"  Вошли через стандартный логин: {cred.username}")
                return "standard"
        except SessionError:
            continue

    # 3. Ручной ввод
    if manual_callback:
        cred = manual_callback(standard_creds)
        if cred:
            try:
                if session.login(cred):
                    progress(f"  Вошли через ручной ввод: {cred.username}")
                    return "manual"
            except SessionError as e:
                progress(f"  Ручной логин не удался: {e}")

    progress("  Не удалось войти")
    return None


def _create_adapter(identity: DeviceIdentity) -> DeviceAdapter:
    """Создать адаптер для найденного устройства."""
    if identity.vendor.lower() in ("dlink", "d-link"):
        adapter = DLinkAdapter()
        if identity.model != "unknown":
            adapter.set_model(identity.model)
        return adapter

    if identity.vendor.lower() == "eltex":
        adapter = EltexAdapter()
        if identity.model != "unknown":
            adapter.set_model(identity.model)
        return adapter

    # Unknown — вернём D-Link base как fallback
    log.warning(
        "Unknown vendor: %s, returning D-Link adapter as fallback", identity.vendor
    )
    return DLinkAdapter()


def _disable_paging(
    session: CLISession,
    adapter: DeviceAdapter,
    progress,
) -> None:
    command = adapter.profile.disable_paging_cmd
    if not command:
        return
    try:
        session.disable_paging(command)
    except Exception as e:
        progress(f"  Не удалось отключить paging: {e}")
