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
import time
from dataclasses import dataclass

from switchlive.core.credentials import Credentials, load_standard_logins
from switchlive.core.errors import SessionError, TransportError
from switchlive.core.models import DeviceIdentity
from switchlive.devices.base import DeviceAdapter, DeviceDetector
from switchlive.devices.dlink import DLinkAdapter, DLinkDetector  # noqa: F401 — регистрация
from switchlive.devices.eltex import EltexAdapter, EltexDetector  # noqa: F401 — регистрация
from switchlive.devices.registry import get_all_detectors
from switchlive.sessions.cli_session import CLISession
from switchlive.sessions.prompts import contains_auth_retry
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
    baudrates: tuple[int, ...] | list[int] | None = None,
    silent_retries: int = 6,
    silent_retry_delay: float = 5.0,
) -> DiscoveryResult:
    """Автопоиск устройства по всем COM-портам.

    Args:
        standard_logins_path: путь к файлу стандартных логинов.
        manual_credential_callback: функция(credentials_list) -> Credentials | None
            для запроса логина/пароля у оператора.
        progress_callback: функция(message: str) — для UI обновлений.
        baudrates: список скоростей serial console для проверки.
        silent_retries: сколько раз повторить поиск, если serial открыт,
            но консоль полностью молчит на всех скоростях.
        silent_retry_delay: пауза между silent retry, в секундах.

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
    baudrates = tuple(baudrates or (9600, 115200))

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

    attempts = max(1, silent_retries + 1)
    for attempt in range(1, attempts + 1):
        any_console_output = False

        for port_info in ports:
            port_name = port_info.name
            _progress(f"Проверка порта {port_name}...")

            result, had_output = _try_port(
                port_name,
                standard_creds,
                manual_credential_callback,
                detectors,
                _progress,
                baudrates,
            )

            if had_output:
                any_console_output = True

            if result and result.found:
                return result

        if any_console_output:
            break

        if attempt < attempts:
            _progress(
                f"Жду загрузку консоли {silent_retry_delay:g}с "
                f"({attempt}/{silent_retries})"
            )
            time.sleep(silent_retry_delay)

    if not any_console_output:
        baudrate_list = ", ".join(str(baudrate) for baudrate in baudrates)
        _progress("Устройство не найдено ни на одном порту")
        return DiscoveryResult(
            found=False,
            error=(
                f"Нет ответа от консоли ни на одной скорости ({baudrate_list}). "
                "Возможно, коммутатор не работает. "
                "Попробуйте перезагрузить коммутатор по питанию и повторить."
            ),
        )

    _progress("Устройство не найдено ни на одном порту")
    return DiscoveryResult(found=False, error="Устройство не обнаружено")


def _try_port(
    port_name: str,
    standard_creds: list[Credentials],
    manual_credential_callback,
    detectors: list[DeviceDetector],
    progress,
    baudrates: tuple[int, ...] = (9600, 115200),
) -> tuple[DiscoveryResult | None, bool]:
    """Попробовать найти устройство на конкретном порту.

    Returns: (result, had_any_output)
    """
    manual_baudrates: list[int] = []
    had_any_output = False

    for baudrate in baudrates:
        result, had_console_output = _try_baudrate(
            port_name,
            baudrate,
            standard_creds,
            manual_callback=None,
            detectors=detectors,
            progress=progress,
        )
        if result:
            return result, True
        if had_console_output:
            manual_baudrates.append(baudrate)
            had_any_output = True

    if manual_credential_callback:
        for baudrate in manual_baudrates:
            result, _ = _try_baudrate(
                port_name,
                baudrate,
                standard_creds=[],
                manual_callback=manual_credential_callback,
                detectors=detectors,
                progress=progress,
            )
            if result:
                return result, True

    return None, had_any_output


def _try_baudrate(
    port_name: str,
    baudrate: int,
    standard_creds: list[Credentials],
    manual_callback,
    detectors: list[DeviceDetector],
    progress,
) -> tuple[DiscoveryResult | None, bool]:
    transport = SerialTransport(port=port_name, baudrate=baudrate)
    try:
        transport.open()
    except TransportError as e:
        progress(f"  Не удалось открыть {port_name}: {e}")
        return None, False

    session = CLISession(transport, vendor="discovery")
    keep_open = False
    try:
        auth_method = _try_login(session, standard_creds, manual_callback, progress)
        had_console_output = _has_auth_console_output(session.transcript)
        if auth_method is None:
            return None, had_console_output

        result = _detect_device(port_name, session, auth_method, detectors, progress)
        if result:
            keep_open = True
            return result, had_console_output
        return None, had_console_output
    finally:
        if not keep_open:
            transport.close()


def _detect_device(
    port_name: str,
    session: CLISession,
    auth_method: str,
    detectors: list[DeviceDetector],
    progress,
) -> DiscoveryResult | None:
    for detector in detectors:
        try:
            if detector.can_detect(session):
                progress(f"  Детектор {type(detector).__name__}: совпадение!")
                _disable_detector_paging(session, detector, progress)
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

    progress(f"  Устройство на {port_name} не распознано (ни один детектор)")
    return None


def _disable_detector_paging(
    session: CLISession,
    detector: DeviceDetector,
    progress,
) -> None:
    if isinstance(detector, DLinkDetector):
        _disable_paging(session, DLinkAdapter(), progress)


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
        # Пересоздаём сессию для каждой попытки — предыдущий login
        # мог оставить switch в состоянии auth-fail / lockout.
        # Закрываем и открываем порт заново.
        session.reset()
        try:
            session.transport.close()
            session.transport.open()
            time.sleep(0.5)
        except Exception:
            pass
        try:
            if session.login(cred):
                progress(f"  Вошли через стандартный логин: {cred.username}")
                return "standard"
        except SessionError:
            continue

    # 3. Ручной ввод
    if manual_callback:
        session.reset()
        try:
            session.transport.close()
            session.transport.open()
            time.sleep(0.5)
        except Exception:
            pass
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


def _has_auth_console_output(text: str) -> bool:
    """Вернуть True только для читаемого auth/login вывода консоли.

    На неверном baudrate serial может отдавать мусорные байты. Их не нужно
    считать поводом для ручного логина, иначе оператору первым предлагают
    заведомо нерабочую скорость.
    """
    lowered = text.lower()
    return any(
        marker in lowered
        for marker in (
            "login",
            "user name",
            "username",
            "password",
            "passwd",
            "authentication failed",
        )
    ) or contains_auth_retry(text)


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
