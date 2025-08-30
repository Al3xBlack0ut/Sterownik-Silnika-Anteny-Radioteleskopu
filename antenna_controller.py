"""
Biblioteka do sterowania silnikiem anteny radioteleskopu
Protokół komunikacji: Hamlib rotctl

Główna biblioteka zawierająca kompletny system sterowania anteną radioteleskopu.
Używa biblioteki Hamlib (rotctl) do komunikacji z kontrolerem SPID MD-01/02/03.
Obejmuje sterownik rotctl, kontroler pozycji, monitorowanie w czasie
rzeczywistym oraz kompleksową obsługę błędów i limitów bezpieczeństwa.

Autor: Aleks Czarnecki
"""

import logging
import threading
import time
import json
import os
import subprocess
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, Tuple, Dict, Any, Callable


# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Domyślny port szeregowy dla kontrolera SPID
DEFAULT_SPID_PORT = "/dev/tty.usbserial-A10PDNT7"

# Wspólne stałe konfiguracyjne
DEFAULT_BAUDRATE = 115200
DEFAULT_ROTCTL_MODEL = "903"
DEFAULT_TIMEOUT = 5

# Domyślna ścieżka do pliku konfiguracji kalibracji
DEFAULT_CALIBRATION_FILE = "calibrations/antenna_calibration.json"


def sprawdz_rotctl() -> bool:
    """Sprawdza czy rotctl jest dostępne w systemie."""
    try:
        result = subprocess.run(
            ["rotctl", "--version"],
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def ustaw_pozycje_rotctl(port: str, az: float, el: float, speed: int = DEFAULT_BAUDRATE) -> str:
    """Ustawia pozycję rotatora za pomocą rotctl (Hamlib)."""
    komenda = f"P {az % 360:.1f} {el:.1f}\n"

    proc = subprocess.Popen(
        ["rotctl", "-m", DEFAULT_ROTCTL_MODEL, "-r", port, "-s", str(speed), "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = proc.communicate(input=komenda)

    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl: {stderr.strip()}")

    return stdout.strip()


def odczytaj_pozycje_rotctl(port: str, speed: int = DEFAULT_BAUDRATE) -> Tuple[float, float]:
    """
    Odczytuje aktualną pozycję rotatora za pomocą rotctl.
    Zwraca tuple (azymut, elewacja) w stopniach.
    """
    proc = subprocess.Popen(
        ["rotctl", "-m", DEFAULT_ROTCTL_MODEL, "-r", port, "-s", str(speed), "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = proc.communicate(input="p\n")

    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl: {stderr.strip()}")

    # Parsowanie odpowiedzi - usuń echo komendy
    lines = stdout.strip().split("\n")
    values = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith("p "):
            try:
                values.append(float(line))
            except ValueError:
                # Sprawdź czy linia zawiera wartość po "p "
                if line.startswith("p "):
                    try:
                        values.append(float(line[2:]))
                    except ValueError:
                        continue

    if len(values) >= 2:
        return values[0], values[1]
    else:
        # Alternatywne parsowanie - wyciągnij liczby z całego tekstu
        numbers = re.findall(r"[-+]?\d*\.?\d+", stdout)
        if len(numbers) >= 2:
            try:
                return float(numbers[0]), float(numbers[1])
            except ValueError:
                pass

        raise RuntimeError(f"Niepełna odpowiedź pozycji: {stdout}")


def zatrzymaj_rotor_rotctl(port: str, speed: int = DEFAULT_BAUDRATE) -> str:
    """Zatrzymuje ruch rotatora za pomocą rotctl."""
    proc = subprocess.Popen(
        ["rotctl", "-m", DEFAULT_ROTCTL_MODEL, "-r", port, "-s", str(speed), "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = proc.communicate(input="S\n")

    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl STOP: {stderr.strip()}")

    return stdout.strip()


def get_best_spid_port(preferred_port: Optional[str] = None) -> str:
    """
    Zwraca najlepszy port dla kontrolera SPID.
    Sprawdza czy rotctl jest dostępne.
    """
    if not sprawdz_rotctl():
        raise RuntimeError("rotctl (Hamlib) nie jest dostępne w systemie")

    if preferred_port:
        logger.info(f"Używam podanego portu: {preferred_port}")
        return preferred_port

    logger.info(f"Używam domyślnego portu: {DEFAULT_SPID_PORT}")
    return DEFAULT_SPID_PORT


# =============================================================================
# FUNKCJE ROTCTL (HAMLIB) -  SPOSÓB KOMUNIKACJI Z SPID
# =============================================================================


def rotctl_ustaw_pozycje(
    port: str, az: float, el: float, speed: int = DEFAULT_BAUDRATE, retry_count: int = 2
) -> str:
    """
    Ustawia pozycję rotatora SPID za pomocą rotctl (Hamlib).

    Args:
        port: Port szeregowy (np. '/dev/tty.usbserial-A10PDNT7')
        az: Azymut w stopniach (0-360)
        el: Elewacja w stopniach (-90 do +90)
        speed: Prędkość portu szeregowego
        retry_count: Liczba ponownych prób w przypadku błędu

    Returns:
        Odpowiedź rotctl jako string

    Raises:
        RuntimeError: Jeśli komenda się nie powiodła po wszystkich próbach
    """
    if not sprawdz_rotctl():
        raise RuntimeError("rotctl (Hamlib) nie jest dostępne w systemie")

    komenda = f"P {az % 360:.1f} {el:.1f}\n"
    
    # Dodatkowe logowanie pozycji przed wysłaniem
    normalized_az = az % 360
    logger.info(f"Rotctl: Wysyłam komendę pozycji - Az={normalized_az:.1f}°, El={el:.1f}°")
    
    # Sprawdź podstawowe limity (rozsądne zakresy)
    if el < -90.0 or el > 90.0:
        raise RuntimeError(f"Elewacja {el:.1f}° poza dozwolonym zakresem (-90° do +90°)")

    for attempt in range(retry_count + 1):
        try:
            proc = subprocess.Popen(
                ["rotctl", "-m", "903", "-r", port, "-s", str(speed), "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout, stderr = proc.communicate(input=komenda, timeout=15)

            if proc.returncode == 0:
                logger.debug(
                    f"Rotctl ustaw pozycję Az={normalized_az:.1f}°, El={el:.1f}° - odpowiedź: {stdout.strip()}"
                )
                return stdout.strip()
            else:
                error_msg = stderr.strip() if stderr.strip() else stdout.strip()
                if attempt < retry_count:
                    logger.warning(
                        f"Próba {attempt + 1} nieudana, kod: {proc.returncode}, błąd: '{error_msg}', ponawiam..."
                    )
                    time.sleep(1)  # Krótka pauza przed ponowieniem
                    continue
                else:
                    raise RuntimeError(
                        f"Błąd rotctl podczas ustawiania pozycji Az={normalized_az:.1f}°, El={el:.1f}°: kod {proc.returncode}, błąd: '{error_msg}'"
                    )

        except subprocess.TimeoutExpired:
            proc.kill()
            if attempt < retry_count:
                logger.warning(f"Timeout podczas próby {attempt + 1}, ponawiam...")
                time.sleep(1)
                continue
            else:
                raise RuntimeError(
                    "Timeout podczas komunikacji z rotctl po wszystkich próbach"
                )
        except Exception as e:
            if attempt < retry_count:
                logger.warning(f"Błąd podczas próby {attempt + 1}: {e}, ponawiam...")
                time.sleep(1)
                continue
            else:
                raise RuntimeError(f"Błąd podczas komunikacji z rotctl: {e}")


def rotctl_odczytaj_pozycje(
    port: str, speed: int = DEFAULT_BAUDRATE, retry_count: int = 2
) -> Tuple[float, float]:
    """
    Odczytuje aktualną pozycję rotatora SPID za pomocą rotctl.

    Args:
        port: Port szeregowy
        speed: Prędkość portu szeregowego
        retry_count: Liczba ponownych prób w przypadku błędu

    Returns:
        Tuple (azymut, elewacja) w stopniach

    Raises:
        RuntimeError: Jeśli odczyt się nie powiódł po wszystkich próbach
    """
    if not sprawdz_rotctl():
        raise RuntimeError("rotctl (Hamlib) nie jest dostępne w systemie")

    for attempt in range(retry_count + 1):
        try:
            proc = subprocess.Popen(
                ["rotctl", "-m", "903", "-r", port, "-s", str(speed), "-"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout, stderr = proc.communicate(input="p\n", timeout=15)

            if proc.returncode == 0:
                # Parsowanie odpowiedzi rotctl
                lines = stdout.strip().split("\n")
                values = []

                for line in lines:
                    line = line.strip()
                    if line and not line.startswith("p "):
                        try:
                            values.append(float(line))
                        except ValueError:
                            # Sprawdź czy linia zawiera wartość po "p "
                            if line.startswith("p "):
                                try:
                                    values.append(float(line[2:]))
                                except ValueError:
                                    continue

                if len(values) >= 2:
                    az, el = values[0], values[1]
                    logger.debug(f"Rotctl odczyt pozycji: Az={az:.1f}°, El={el:.1f}°")
                    return az, el
                else:
                    # Alternatywne parsowanie - wyciągnij liczby z całego tekstu
                    numbers = re.findall(r"[-+]?\d*\.?\d+", stdout)
                    if len(numbers) >= 2:
                        try:
                            az, el = float(numbers[0]), float(numbers[1])
                            logger.debug(
                                f"Rotctl odczyt pozycji (alt): Az={az:.1f}°, El={el:.1f}°"
                            )
                            return az, el
                        except ValueError:
                            pass

                    if attempt < retry_count:
                        logger.warning(
                            f"Niepełna odpowiedź podczas próby {attempt + 1}: {stdout}, ponawiam..."
                        )
                        time.sleep(0.5)
                        continue
                    else:
                        raise RuntimeError(
                            f"Niepełna odpowiedź pozycji rotctl: {stdout}"
                        )
            else:
                if attempt < retry_count:
                    logger.warning(
                        f"Błąd rotctl podczas próby {attempt + 1}: {stderr.strip()}, ponawiam..."
                    )
                    time.sleep(0.5)
                    continue
                else:
                    raise RuntimeError(
                        f"Błąd rotctl podczas odczytu pozycji: {stderr.strip()}"
                    )

        except subprocess.TimeoutExpired:
            proc.kill()
            if attempt < retry_count:
                logger.warning(
                    f"Timeout podczas odczytu pozycji, próba {attempt + 1}, ponawiam..."
                )
                time.sleep(0.5)
                continue
            else:
                raise RuntimeError(
                    "Timeout podczas odczytu pozycji z rotctl po wszystkich próbach"
                )
        except Exception as e:
            if attempt < retry_count:
                logger.warning(
                    f"Błąd podczas odczytu pozycji, próba {attempt + 1}: {e}, ponawiam..."
                )
                time.sleep(0.5)
                continue
            else:
                raise RuntimeError(f"Błąd podczas odczytu pozycji z rotctl: {e}")


def rotctl_zatrzymaj_rotor(port: str, speed: int = DEFAULT_BAUDRATE) -> str:
    """
    Zatrzymuje ruch rotatora za pomocą rotctl.

    Args:
        port: Port szeregowy
        speed: Prędkość portu szeregowego

    Returns:
        Odpowiedź rotctl jako string

    Raises:
        RuntimeError: Jeśli komenda się nie powiodła
    """
    if not sprawdz_rotctl():
        raise RuntimeError("rotctl (Hamlib) nie jest dostępne w systemie")

    try:
        proc = subprocess.Popen(
            ["rotctl", "-m", "903", "-r", port, "-s", str(speed), "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        stdout, stderr = proc.communicate(input="S\n", timeout=10)

        if proc.returncode != 0:
            raise RuntimeError(f"Błąd rotctl podczas zatrzymywania: {stderr.strip()}")

        logger.info("Rotor zatrzymany za pomocą rotctl")
        return stdout.strip()

    except subprocess.TimeoutExpired:
        proc.kill()
        raise RuntimeError("Timeout podczas zatrzymywania rotora przez rotctl")
    except Exception as e:
        raise RuntimeError(f"Błąd podczas zatrzymywania rotora przez rotctl: {e}")


def run_rotctl_command(
    command: list[str], 
    port: str = DEFAULT_SPID_PORT, 
    baudrate: int = DEFAULT_BAUDRATE,
    timeout: int = 10
) -> subprocess.CompletedProcess:
    """
    Uruchamia komendę rotctl z standardowymi parametrami.
    
    Args:
        command: Lista argumentów komendy (bez rotctl, -m, -r, -s)
        port: Port SPID
        baudrate: Prędkość transmisji
        timeout: Timeout w sekundach
    
    Returns:
        Wynik subprocess.run
    """
    cmd = [
        "rotctl", 
        "-m", DEFAULT_ROTCTL_MODEL,
        "-r", port,
        "-s", str(baudrate),
        "-t", str(timeout)
    ] + command
    
    logger.debug(f"Wykonuję komendę rotctl: {' '.join(cmd)}")
    
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout + 5,  # Dodatkowy bufor
        check=False,
    )


def test_spid_connection(port: str = DEFAULT_SPID_PORT, baudrate: int = DEFAULT_BAUDRATE) -> bool:
    """
    Testuje połączenie ze SPID przez rotctl.
    
    Args:
        port: Port SPID
        baudrate: Prędkość transmisji
    
    Returns:
        True jeśli połączenie działa
    """
    try:
        result = run_rotctl_command(["get_pos"], port, baudrate, timeout=10)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Błąd podczas testowania połączenia SPID: {e}")
        return False


# ===== KLASY BŁĘDÓW =====

class AntennaError(Exception):
    """Podstawowy wyjątek dla błędów anteny"""


class CommunicationError(AntennaError):
    """Błąd komunikacji z sterownikiem"""


class PositionError(AntennaError):
    """Błąd pozycjonowania anteny"""


class SafetyError(AntennaError):
    """Błąd bezpieczeństwa - przekrocenie limitów"""


class AntennaState(Enum):
    """Stany anteny"""

    IDLE = "idle"
    MOVING = "moving"
    ERROR = "error"
    STOPPED = "stopped"
    CALIBRATING = "calibrating"


@dataclass
class Position:
    """Pozycja anteny (azymut i elewacja)"""

    azimuth: float  # stopnie (0-360)
    elevation: float  # stopnie (bez ograniczeń, limity sprawdzane w AntennaController)

    def __post_init__(self):
        """Walidacja pozycji"""
        if not (0 <= self.azimuth <= 360):
            raise ValueError(
                f"Azymut musi być w zakresie 0-360°, otrzymano: {self.azimuth}"
            )
        # Elewacja bez ograniczeń - limity sprawdzane w AntennaController


@dataclass
class AntennaLimits:
    """Limity mechaniczne anteny"""

    min_azimuth: float = 0.0
    max_azimuth: float = 360.0
    min_elevation: float = 0.0
    max_elevation: float = 90.0
    max_azimuth_speed: float = 5.0  # stopnie/s
    max_elevation_speed: float = 3.0  # stopnie/s


@dataclass
class PositionCalibration:
    """Kalibracja pozycji anteny z limitami bezpieczeństwa"""

    azimuth_offset: float = 0.0  # Offset dla azymutu w stopniach
    elevation_offset: float = 0.0  # Offset dla elewacji w stopniach

    # Limity bezpieczeństwa
    min_azimuth: float = 0.0  # Minimalny azimut w stopniach
    max_azimuth: float = 360.0  # Maksymalny azimut w stopniach
    min_elevation: float = 0.0  # Minimalna elewacja w stopniach
    max_elevation: float = 90.0  # Maksymalna elewacja w stopniach
    max_azimuth_speed: float = 5.0  # Maksymalna prędkość azymutu w stopniach/s
    max_elevation_speed: float = 3.0  # Maksymalna prędkość elewacji w stopniach/s

    def apply_calibration(self, position: Position) -> Position:
        """Aplikuje kalibrację do pozycji"""
        # Aplikuj offset azymutu
        calibrated_azimuth = (position.azimuth + self.azimuth_offset) % 360

        # Aplikuj offset elewacji
        calibrated_elevation = position.elevation + self.elevation_offset

        # Ogranicz elewację do zakresów z kalibracji
        calibrated_elevation = max(self.min_elevation, min(self.max_elevation, calibrated_elevation))

        return Position(calibrated_azimuth, calibrated_elevation)

    def reverse_calibration(self, calibrated_position: Position) -> Position:
        """Odwraca kalibrację - konwertuje z pozycji skalibrowanej do surowej"""
        # Cofnij offset azymutu
        raw_azimuth = (calibrated_position.azimuth - self.azimuth_offset) % 360

        # Cofnij offset elewacji
        raw_elevation = calibrated_position.elevation - self.elevation_offset

        # Ogranicz do sensownych zakresów
        raw_elevation = max(-90.0, min(90.0, raw_elevation))

        return Position(raw_azimuth, raw_elevation)

    def get_antenna_limits(self) -> AntennaLimits:
        """Zwraca limity anteny na podstawie ustawień kalibracji"""
        return AntennaLimits(
            min_azimuth=self.min_azimuth,
            max_azimuth=self.max_azimuth,
            min_elevation=self.min_elevation,
            max_elevation=self.max_elevation,
            max_azimuth_speed=self.max_azimuth_speed,
            max_elevation_speed=self.max_elevation_speed,
        )

    def save_to_file(self, filepath: str = DEFAULT_CALIBRATION_FILE) -> None:
        """Zapisuje kalibrację i limity do pliku JSON"""
        try:
            # Utwórz folder jeśli nie istnieje
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            calibration_data = {
                "azimuth_offset": self.azimuth_offset,
                "elevation_offset": self.elevation_offset,
                "min_azimuth": self.min_azimuth,
                "max_azimuth": self.max_azimuth,
                "min_elevation": self.min_elevation,
                "max_elevation": self.max_elevation,
                "max_azimuth_speed": self.max_azimuth_speed,
                "max_elevation_speed": self.max_elevation_speed,
                "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "version": "2.0",
            }

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(calibration_data, f, indent=4, ensure_ascii=False)

            logger.info(f"Kalibracja z limitami zapisana do pliku: {filepath}")

        except Exception as e:
            logger.error(f"Błąd podczas zapisywania kalibracji: {e}")
            raise AntennaError(f"Nie można zapisać kalibracji do pliku {filepath}: {e}")

    @classmethod
    def load_from_file(
        cls, filepath: str = DEFAULT_CALIBRATION_FILE
    ) -> "PositionCalibration":
        """Wczytuje kalibrację i limity z pliku JSON"""
        try:
            if not os.path.exists(filepath):
                logger.warning(
                    f"Plik kalibracji {filepath} nie istnieje, używam domyślnych wartości"
                )
                return cls()  # Zwróć domyślną kalibrację

            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Walidacja danych - podstawowe pola kalibracji
            required_fields = [
                "azimuth_offset",
                "elevation_offset",
            ]
            for field in required_fields:
                if field not in data:
                    logger.warning(
                        f"Brak pola '{field}' w pliku kalibracji, używam wartości domyślnej"
                    )

            calibration = cls(
                azimuth_offset=float(data.get("azimuth_offset", 0.0)),
                elevation_offset=float(data.get("elevation_offset", 0.0)),
                min_azimuth=float(data.get("min_azimuth", 0.0)),
                max_azimuth=float(data.get("max_azimuth", 360.0)),
                min_elevation=float(data.get("min_elevation", 0.0)),
                max_elevation=float(data.get("max_elevation", 90.0)),
                max_azimuth_speed=float(data.get("max_azimuth_speed", 5.0)),
                max_elevation_speed=float(data.get("max_elevation_speed", 3.0)),
            )

            logger.info(f"Kalibracja wczytana z pliku: {filepath}")
            logger.info(
                f"Parametry kalibracji: "
                f"az_off={calibration.azimuth_offset:.2f}°, "
                f"el_off={calibration.elevation_offset:.2f}°"
            )
            logger.info(
                f"Limity: az({calibration.min_azimuth}°-{calibration.max_azimuth}°), "
                f"el({calibration.min_elevation}°-{calibration.max_elevation}°)"
            )

            return calibration

        except json.JSONDecodeError as e:
            logger.error(f"Błąd parsowania JSON w pliku {filepath}: {e}")
            raise AntennaError(f"Nieprawidłowy format pliku kalibracji: {e}")
        except Exception as e:
            logger.error(f"Błąd podczas wczytywania kalibracji: {e}")
            raise AntennaError(f"Nie można wczytać kalibracji z pliku {filepath}: {e}")

    def export_to_dict(self) -> Dict[str, Any]:
        """Eksportuje kalibrację do słownika"""
        return asdict(self)

    @classmethod
    def import_from_dict(cls, data: Dict[str, Any]) -> "PositionCalibration":
        """Importuje kalibrację ze słownika"""
        return cls(
            azimuth_offset=float(data.get("azimuth_offset", 0.0)),
            elevation_offset=float(data.get("elevation_offset", 0.0)),
            min_azimuth=float(data.get("min_azimuth", 0.0)),
            max_azimuth=float(data.get("max_azimuth", 360.0)),
            min_elevation=float(data.get("min_elevation", 0.0)),
            max_elevation=float(data.get("max_elevation", 90.0)),
            max_azimuth_speed=float(data.get("max_azimuth_speed", 5.0)),
            max_elevation_speed=float(data.get("max_elevation_speed", 3.0)),
        )


class MotorConfig:
    """Konfiguracja silnika z możliwościami kalibracji"""

    def __init__(
        self,
        steps_per_revolution: int = 200,
        microsteps: int = 16,
        azimuth_offset: float = 0.0,
        elevation_offset: float = 0.0,
    ):
        self.steps_per_revolution = steps_per_revolution
        self.microsteps = microsteps

        # Parametry kalibracji
        self.azimuth_offset = azimuth_offset  # Offset kalibracji azymutu w stopniach
        self.elevation_offset = elevation_offset  # Offset kalibracji elewacji w stopniach

    def apply_calibration(
        self, azimuth: float, elevation: float
    ) -> Tuple[float, float]:
        """Stosuje kalibrację do pozycji"""
        calibrated_azimuth = azimuth + self.azimuth_offset
        calibrated_elevation = elevation + self.elevation_offset

        # Normalizuj azymut do zakresu 0-360
        calibrated_azimuth = calibrated_azimuth % 360.0

        return calibrated_azimuth, calibrated_elevation

    def reverse_calibration(
        self, calibrated_azimuth: float, calibrated_elevation: float
    ) -> Tuple[float, float]:
        """Odwraca kalibrację dla uzyskania pozycji raw (tylko offsety)"""
        azimuth = calibrated_azimuth - self.azimuth_offset
        elevation = calibrated_elevation - self.elevation_offset

        # Normalizuj azymut
        azimuth = azimuth % 360.0

        return azimuth, elevation


class MotorDriver(ABC):
    """Abstrakcyjna klasa sterownika silnika"""

    @abstractmethod
    def connect(self) -> None:
        """Nawiązuje połączenie z sterownikiem"""

    @abstractmethod
    def disconnect(self) -> None:
        """Rozłącza się ze sterownikiem"""

    @abstractmethod
    def move_to_position(self, azimuth: float, elevation: float) -> None:
        """Przesuwa anteny do pozycji w stopniach"""

    @abstractmethod
    def get_position(self) -> Tuple[float, float]:
        """Zwraca aktualną pozycję w stopniach"""

    @abstractmethod
    def stop(self) -> None:
        """Zatrzymuje wszystkie silniki"""

    @abstractmethod
    def is_moving(self) -> bool:
        """Sprawdza czy silniki się poruszają"""


class RotctlMotorDriver(MotorDriver):
    """Sterownik silnika komunikujący się przez rotctl (Hamlib) z protokołem SPID"""

    def __init__(self, port: str, baudrate: int = DEFAULT_BAUDRATE):
        self.port = port
        self.baudrate = baudrate
        self.connected = False
        self.current_azimuth = 0.0
        self.current_elevation = 0.0
        self.target_azimuth = 0.0
        self.target_elevation = 0.0
        self.is_moving_flag = False

    def connect(self) -> None:
        """Sprawdza dostępność rotctl i portu"""
        try:
            if not sprawdz_rotctl():
                raise CommunicationError("rotctl (Hamlib) nie jest dostępne w systemie")

            # Test połączenia - spróbuj odczytać pozycję
            self.current_azimuth, self.current_elevation = rotctl_odczytaj_pozycje(
                self.port, self.baudrate
            )
            self.connected = True
            logger.info(
                f"Połączono z kontrolerem SPID przez rotctl na porcie {self.port} (baudrate: {self.baudrate})"
            )
            logger.info(
                f"Aktualna pozycja: Az={self.current_azimuth:.1f}°, El={self.current_elevation:.1f}°"
            )

        except Exception as e:
            logger.error(f"Błąd połączenia z SPID przez rotctl: {e}")
            raise CommunicationError(f"Nie można nawiązać połączenia przez rotctl: {e}")

    def disconnect(self) -> None:
        """Rozłącza połączenie - rotctl nie wymaga jawnego rozłączania"""
        self.connected = False
        logger.info("Rozłączono z kontrolerem SPID (rotctl)")

    def get_position(self) -> Tuple[float, float]:
        """Odczytuje aktualną pozycję anteny w stopniach"""
        if not self.connected:
            raise CommunicationError("Sterownik rotctl nie jest połączony")

        try:
            self.current_azimuth, self.current_elevation = rotctl_odczytaj_pozycje(
                self.port, self.baudrate
            )
            return self.current_azimuth, self.current_elevation

        except Exception as e:
            logger.error(f"Błąd odczytu pozycji przez rotctl: {e}")
            raise CommunicationError(f"Nie można odczytać pozycji przez rotctl: {e}")

    def move_to_position(self, azimuth: float, elevation: float) -> None:
        """Przesuwa antenę do zadanej pozycji w stopniach"""
        if not self.connected:
            raise CommunicationError("Sterownik rotctl nie jest połączony")

        # Walidacja zakresu
        if not (0 <= azimuth <= 360):
            raise PositionError(f"Azymut poza zakresem: {azimuth}° (oczekiwano 0-360°)")

        try:
            self.target_azimuth = azimuth
            self.target_elevation = elevation
            self.is_moving_flag = True

            logger.info(
                f"Rotctl: Ustawianie pozycji Az={azimuth:.1f}°, El={elevation:.1f}°"
            )

            # Dodatkowy delay przed wysłaniem komendy
            time.sleep(0.2)

            response = rotctl_ustaw_pozycje(
                self.port, azimuth, elevation, self.baudrate
            )

            logger.info(f"Rotctl: Komenda wysłana. Odpowiedź: {response}")

        except Exception as e:
            self.is_moving_flag = False
            logger.error(f"Błąd podczas ruchu przez rotctl: {e}")
            raise CommunicationError(f"Nie można przesunąć anteny przez rotctl: {e}")

    def stop(self) -> None:
        """Zatrzymuje ruch anteny"""
        if not self.connected:
            raise CommunicationError("Sterownik rotctl nie jest połączony")

        try:
            logger.info("Rotctl: Zatrzymywanie ruchu anteny")
            response = rotctl_zatrzymaj_rotor(self.port, self.baudrate)
            self.is_moving_flag = False
            logger.info(f"Rotctl: Ruch zatrzymany. Odpowiedź: {response}")

        except Exception as e:
            logger.error(f"Błąd podczas zatrzymywania przez rotctl: {e}")
            raise CommunicationError(f"Nie można zatrzymać anteny przez rotctl: {e}")

    def is_moving(self) -> bool:
        """
        Sprawdza czy antena się porusza przez porównanie aktualnej i docelowej pozycji.

        Nota: rotctl nie zapewnia bezpośredniego sprawdzenia statusu ruchu,
        więc sprawdzamy czy pozycja jest bliska docelowej.
        """
        if not self.is_moving_flag:
            return False

        try:
            current_az, current_el = self.get_position()

            # Tolerancja pozycji (1 stopień)
            az_diff = abs(current_az - self.target_azimuth)
            el_diff = abs(current_el - self.target_elevation)

            # Uwzględnij przejście przez 0°/360° dla azymutu
            if az_diff > 180:
                az_diff = 360 - az_diff

            is_at_target = az_diff < 1.0 and el_diff < 1.0

            if is_at_target:
                self.is_moving_flag = False
                logger.info(
                    f"Rotctl: Pozycja docelowa osiągnięta Az={current_az:.1f}°, El={current_el:.1f}°"
                )

            return not is_at_target

        except Exception as e:
            logger.warning(f"Błąd sprawdzenia ruchu przez rotctl: {e}")
            # W razie błędu zakładamy że ruch się zakończył
            self.is_moving_flag = False
            return False


class SimulatedMotorDriver(MotorDriver):
    """Symulator sterownika silnika do testów - operuje bezpośrednio na stopniach"""

    def __init__(self, simulation_speed: float = 10.0):
        self.simulation_speed = simulation_speed  # stopnie/s
        self.current_azimuth = 0.0  # stopnie
        self.current_elevation = 0.0  # stopnie (horyzont)
        self.target_azimuth = 0.0
        self.target_elevation = 0.0
        self.connected = False
        self.is_moving_flag = False
        self.last_move_time = time.time()

    def connect(self) -> None:
        """Symuluje nawiązanie połączenia"""
        self.connected = True
        logger.info("Połączono z symulatorem sterownika")

    def disconnect(self) -> None:
        """Symuluje rozłączenie"""
        self.connected = False
        logger.info("Rozłączono z symulatorem sterownika")

    def move_to_position(self, azimuth: float, elevation: float) -> None:
        """Symuluje ruch do pozycji w stopniach"""
        if not self.connected:
            raise CommunicationError("Symulator nie jest połączony")

        self.target_azimuth = azimuth
        self.target_elevation = elevation
        self.is_moving_flag = True
        self.last_move_time = time.time()

        logger.info(f"Symulator: Ruch do pozycji Az={azimuth}°, El={elevation}°")

    def get_position(self) -> Tuple[float, float]:
        """Zwraca aktualną pozycję w stopniach z symulacją ruchu"""
        if not self.connected:
            raise CommunicationError("Symulator nie jest połączony")

        if self.is_moving_flag:
            self._simulate_movement()

        return self.current_azimuth, self.current_elevation

    def _simulate_movement(self) -> None:
        """Symuluje płynny ruch anteny w stopniach"""
        current_time = time.time()
        dt = current_time - self.last_move_time
        self.last_move_time = current_time

        # Oblicz maksymalny ruch w tym kroku czasowym (stopnie)
        max_move = self.simulation_speed * dt

        # Ruch azymutu
        az_diff = self.target_azimuth - self.current_azimuth
        if abs(az_diff) <= max_move:
            self.current_azimuth = self.target_azimuth
        else:
            self.current_azimuth += max_move if az_diff > 0 else -max_move

        # Ruch elewacji
        el_diff = self.target_elevation - self.current_elevation
        if abs(el_diff) <= max_move:
            self.current_elevation = self.target_elevation
        else:
            self.current_elevation += max_move if el_diff > 0 else -max_move

        # Sprawdź czy osiągnięto cel
        if (
            abs(self.current_azimuth - self.target_azimuth) < 0.1
            and abs(self.current_elevation - self.target_elevation) < 0.1
        ):
            self.is_moving_flag = False
            logger.debug("Symulator: Ruch zakończony")

    def stop(self) -> None:
        """Symuluje zatrzymanie ruchu"""
        self.is_moving_flag = False
        # Ustaw cele na aktualną pozycję
        self.target_azimuth = self.current_azimuth
        self.target_elevation = self.current_elevation
        logger.info("Symulator: Ruch zatrzymany")

    def is_moving(self) -> bool:
        """Sprawdza czy symulator jest w ruchu"""
        if self.is_moving_flag:
            self._simulate_movement()
        return self.is_moving_flag


class AntennaController:
    """Główny kontroler anteny radioteleskopu"""

    def __init__(
        self,
        motor_driver: MotorDriver,
        motor_config: MotorConfig,
        limits: Optional[AntennaLimits] = None,
        update_callback: Optional[Callable] = None,
        position_calibration: Optional[PositionCalibration] = None,
        calibration_file: str = DEFAULT_CALIBRATION_FILE,
    ):
        self.motor_driver = motor_driver
        self.motor_config = motor_config
        self.update_callback = update_callback
        self.calibration_file = calibration_file

        # Wczytaj kalibrację z pliku lub użyj podanej
        if position_calibration is not None:
            self.position_calibration = position_calibration
        else:
            self.position_calibration = PositionCalibration.load_from_file(
                self.calibration_file
            )

        # Ustaw limity - używaj limitów z kalibracji, jeśli nie podano innych
        if limits is not None:
            self.limits = limits
            logger.info("Używam podanych limitów bezpieczeństwa")
        else:
            self.limits = self.position_calibration.get_antenna_limits()
            logger.info("Używam limitów bezpieczeństwa z pliku kalibracji")

        self.state = AntennaState.IDLE
        self.current_position = Position(0.0, 0.0)
        self.target_position: Optional[Position] = None

        self._monitoring_thread: Optional[threading.Thread] = None
        self._monitoring_active = False
        self._stop_monitoring = threading.Event()

    def initialize(self) -> None:
        """Inicjalizuje system anteny"""
        try:
            self.motor_driver.connect()
            self._start_monitoring()
            self.state = AntennaState.IDLE
            logger.info("System anteny zainicjalizowany")
        except Exception as e:
            self.state = AntennaState.ERROR
            raise AntennaError(f"Błąd inicjalizacji: {e}")

    def shutdown(self) -> None:
        """Bezpieczne wyłączenie systemu"""
        self.stop()
        self._stop_monitoring.set()
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join()
        self.motor_driver.disconnect()
        logger.info("System anteny wyłączony")

    def _start_monitoring(self) -> None:
        """Uruchamia wątek monitorowania pozycji"""
        self._monitoring_active = True
        self._stop_monitoring.clear()
        self._monitoring_thread = threading.Thread(target=self._monitor_position)
        self._monitoring_thread.daemon = True
        self._monitoring_thread.start()

    def _monitor_position(self) -> None:
        """Monitoruje pozycję anteny w osobnym wątku"""
        consecutive_errors = 0
        max_consecutive_errors = 3

        while not self._stop_monitoring.is_set():
            try:
                # Wszystkie sterowniki teraz zwracają bezpośrednio stopnie
                azimuth, elevation = self.motor_driver.get_position()
                self.current_position = Position(azimuth, elevation)

                # Sprawdź czy ruch się zakończył
                if (
                    self.state == AntennaState.MOVING
                    and not self.motor_driver.is_moving()
                ):
                    self.state = AntennaState.IDLE
                    logger.info(f"Ruch zakończony. Pozycja: {self.current_position}")

                # Wywołaj callback jeśli zdefiniowany
                if self.update_callback:
                    self.update_callback(self.current_position, self.state)

                # Zeruj licznik błędów po udanym odczycie
                consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Błąd monitorowania: {e}")

                # Jeśli wystąpiło zbyt wiele błędów pod rząd, ustaw stan błędu
                if consecutive_errors >= max_consecutive_errors:
                    self.state = AntennaState.ERROR
                    logger.error(
                        f"Zbyt wiele błędów monitorowania pod rząd ({consecutive_errors})"
                    )

                # Krótka pauza po błędzie
                time.sleep(0.2)

            time.sleep(0.5)  # Aktualizacja co 500ms

    def _validate_position(self, position: Position) -> None:
        """Waliduje pozycję względem limitów mechanicznych"""
        if not (self.limits.min_azimuth <= position.azimuth <= self.limits.max_azimuth):
            raise SafetyError(
                f"Azymut {position.azimuth}° poza limitami "
                f"({self.limits.min_azimuth}°-{self.limits.max_azimuth}°)"
            )

        if not (
            self.limits.min_elevation <= position.elevation <= self.limits.max_elevation
        ):
            raise SafetyError(
                f"Elewacja {position.elevation}° poza limitami "
                f"({self.limits.min_elevation}°-{self.limits.max_elevation}°)"
            )

    def move_to(self, position: Position) -> None:
        """Przesuwa antenę do zadanej pozycji (z uwzględnieniem kalibracji)"""
        if self.state == AntennaState.ERROR:
            raise AntennaError("System w stanie błędu - nie można wykonać ruchu")

        # Aplikuj kalibrację do zadanej pozycji
        calibrated_position = self.position_calibration.apply_calibration(position)

        # Waliduj skalibrowaną pozycję
        self._validate_position(calibrated_position)

        try:
            self.target_position = (
                position  # Zapisz oryginalną pozycję (bez kalibracji)
            )
            self.state = AntennaState.MOVING

            # Wszystkie sterowniki teraz przyjmują stopnie
            self.motor_driver.move_to_position(
                calibrated_position.azimuth, calibrated_position.elevation
            )

            logger.info(
                f"Rozpoczęto ruch do pozycji: {position} (skalibrowana: {calibrated_position})"
            )
                
        except Exception as e:
            self.state = AntennaState.ERROR
            raise PositionError(f"Błąd podczas ruchu: {e}")

    def get_current_position(self, apply_reverse_calibration: bool = True) -> Position:
        """Zwraca aktualną pozycję anteny"""
        if apply_reverse_calibration:
            # Zwróć pozycję z odwróconą kalibracją (rzeczywista pozycja logiczna)
            return self.position_calibration.reverse_calibration(self.current_position)
        else:
            # Zwróć surową pozycję z sensora
            return self.current_position

    def set_position_calibration(
        self,
        calibration: PositionCalibration,
        save_to_file: bool = True,
        update_limits: bool = True,
    ) -> None:
        """Ustawia kalibrację pozycji"""
        self.position_calibration = calibration

        # Zaktualizuj limity na podstawie kalibracji jeśli wymagane
        if update_limits:
            self.limits = calibration.get_antenna_limits()
            logger.info("Limity bezpieczeństwa zaktualizowane na podstawie kalibracji")

        if save_to_file:
            try:
                calibration.save_to_file(self.calibration_file)
                logger.info("Kalibracja została automatycznie zapisana do pliku")
            except Exception as e:
                logger.warning(f"Nie udało się zapisać kalibracji do pliku: {e}")

        logger.info(
            f"Ustawiono kalibrację pozycji: offset_az={calibration.azimuth_offset}°, "
            f"offset_el={calibration.elevation_offset}°"
        )
        logger.info(
            f"Limity: az({calibration.min_azimuth}°-{calibration.max_azimuth}°), "
            f"el({calibration.min_elevation}°-{calibration.max_elevation}°)"
        )

    def save_calibration(self, filepath: Optional[str] = None) -> None:
        """Zapisuje aktualną kalibrację do pliku"""
        file_to_use = filepath or self.calibration_file
        self.position_calibration.save_to_file(file_to_use)
        logger.info(f"Kalibracja zapisana do {file_to_use}")

    def load_calibration(
        self, filepath: Optional[str] = None, update_limits: bool = True
    ) -> None:
        """Wczytuje kalibrację z pliku"""
        file_to_use = filepath or self.calibration_file
        self.position_calibration = PositionCalibration.load_from_file(file_to_use)

        # Zaktualizuj limity na podstawie wczytanej kalibracji
        if update_limits:
            self.limits = self.position_calibration.get_antenna_limits()
            logger.info(
                "Limity bezpieczeństwa zaktualizowane na podstawie wczytanej kalibracji"
            )

        logger.info(f"Kalibracja wczytana z {file_to_use}")

    def reset_calibration(
        self, save_to_file: bool = True, update_limits: bool = True
    ) -> None:
        """Resetuje kalibrację do wartości domyślnych"""
        self.position_calibration = PositionCalibration()

        # Zaktualizuj limity na podstawie domyślnej kalibracji
        if update_limits:
            self.limits = self.position_calibration.get_antenna_limits()
            logger.info("Limity bezpieczeństwa zresetowane do wartości domyślnych")

        if save_to_file:
            try:
                self.save_calibration()
                logger.info("Zresetowana kalibracja została zapisana do pliku")
            except Exception as e:
                logger.warning(f"Nie udało się zapisać zresetowanej kalibracji: {e}")

        logger.info("Kalibracja została zresetowana do wartości domyślnych")

    def calibrate_azimuth_reference(
        self,
        current_azimuth: float = None,
        save_to_file: bool = True,
    ) -> None:
        """Kalibruje referencję azymutu"""
        if current_azimuth is None:
            current_azimuth = self.current_position.azimuth

        # Oblicz offset potrzebny aby current_azimuth stał się 0°
        offset = -current_azimuth
        self.position_calibration.azimuth_offset = offset

        if save_to_file:
            try:
                self.save_calibration()
                logger.info("Kalibracja azymutu została zapisana do pliku")
            except Exception as e:
                logger.warning(f"Nie udało się zapisać kalibracji azymutu: {e}")

        logger.info(f"Skalibrowano azymut: offset={offset}°")

    def stop(self) -> None:
        """Zatrzymuje ruch anteny"""
        try:
            self.motor_driver.stop()
            self.state = AntennaState.STOPPED
            self.target_position = None
            logger.info("Ruch anteny zatrzymany")
        except Exception as e:
            self.state = AntennaState.ERROR
            raise AntennaError(f"Błąd zatrzymania: {e}")

    def calibrate(self) -> None:
        """Kalibruje pozycję anteny (powrót do pozycji domowej)"""
        logger.info("Rozpoczęcie kalibracji...")
        self.state = AntennaState.CALIBRATING

        # Powrót do pozycji 0,0
        home_position = Position(0.0, 0.0)
        self.move_to(home_position)

        # Czekaj na zakończenie kalibracji
        while self.state == AntennaState.MOVING:
            time.sleep(0.1)

        self.state = AntennaState.IDLE
        logger.info("Kalibracja zakończona")

    def get_status(self) -> Dict[str, Any]:
        """Zwraca pełny status anteny"""
        return {
            "state": self.state.value,
            "current_position": {
                "azimuth": self.current_position.azimuth,
                "elevation": self.current_position.elevation,
            },
            "target_position": (
                {
                    "azimuth": self.target_position.azimuth,
                    "elevation": self.target_position.elevation,
                }
                if self.target_position
                else None
            ),
            "is_moving": (
                self.motor_driver.is_moving()
                if hasattr(self.motor_driver, "is_moving")
                else False
            ),
            "limits": {
                "azimuth": (self.limits.min_azimuth, self.limits.max_azimuth),
                "elevation": (self.limits.min_elevation, self.limits.max_elevation),
                "max_speeds": {
                    "azimuth": self.limits.max_azimuth_speed,
                    "elevation": self.limits.max_elevation_speed,
                },
            },
            "calibration": {
                "azimuth_offset": self.position_calibration.azimuth_offset,
                "elevation_offset": self.position_calibration.elevation_offset,
                "limits": {
                    "min_azimuth": self.position_calibration.min_azimuth,
                    "max_azimuth": self.position_calibration.max_azimuth,
                    "min_elevation": self.position_calibration.min_elevation,
                    "max_elevation": self.position_calibration.max_elevation,
                    "max_azimuth_speed": self.position_calibration.max_azimuth_speed,
                    "max_elevation_speed": self.position_calibration.max_elevation_speed,
                },
            },
            "calibration_file": self.calibration_file,
        }

    def reset_error(self) -> None:
        """Resetuje stan błędu kontrolera"""
        if self.state == AntennaState.ERROR:
            self.state = AntennaState.IDLE
            logger.info("Stan błędu został zresetowany")

    def wait_for_movement(self, timeout: float = 90.0) -> None:
        """
        Czeka na zakończenie ruchu z timeoutem.
        Sprawdza zarówno stan kontrolera jak i rzeczywisty ruch anteny.
        
        Args:
            timeout: Maksymalny czas oczekiwania w sekundach
            
        Raises:
            TimeoutError: Gdy przekroczono czas oczekiwania
        """
        
        start_time = time.time()
        last_movement_time = start_time
        prev_position = None
        
        while True:
            current_time = time.time()
            elapsed_time = current_time - start_time
            
            try:
                # Pobierz aktualną pozycję
                current_position = self.current_position
                
                # Sprawdź czy antena się porusza (porównaj z poprzednią pozycją)
                if prev_position is not None:
                    az_moved = abs(current_position.azimuth - prev_position.azimuth)
                    if az_moved > 180:  # Uwzględnij przejście przez 0°
                        az_moved = 360 - az_moved
                    el_moved = abs(current_position.elevation - prev_position.elevation)
                    
                    # Jeśli antena się porusza (więcej niż 0.2°), zaktualizuj czas ostatniego ruchu
                    if az_moved > 0.2 or el_moved > 0.2:
                        last_movement_time = current_time
                        logger.debug(f"Wykryto ruch anteny: dAz={az_moved:.1f}°, dEl={el_moved:.1f}°")

                # Sprawdź stan kontrolera - jeśli nie jest w ruchu i pozycja się stabilizowała
                time_since_movement = current_time - last_movement_time
                if (self.state != AntennaState.MOVING and 
                    time_since_movement > 3.0):  # 3 sekundy bez ruchu dla lepszej stabilności
                    logger.debug(f"Ruch zakończony - stan: {self.state}, brak ruchu przez {time_since_movement:.1f}s")
                    break
                
                # Sprawdź timeout - ale tylko jeśli antena nie porusza się przez ostatnie 10 sekund
                if elapsed_time > timeout and time_since_movement > 10.0:
                    self.stop()
                    raise TimeoutError(
                        f"Przekroczono czas oczekiwania na ruch ({timeout}s), brak ruchu przez {time_since_movement:.1f}s"
                    )
                
                # Zapisz pozycję dla następnej iteracji
                prev_position = current_position
                time.sleep(0.5)
                
            except Exception as e:
                if isinstance(e, TimeoutError):
                    raise
                logger.warning(f"Błąd podczas sprawdzania ruchu: {e}")
                time.sleep(0.5)


class AntennaControllerFactory:
    """Factory do tworzenia kontrolerów anteny"""

    @staticmethod
    def create_spid_controller(
        port: Optional[str] = None,
        baudrate: int = DEFAULT_BAUDRATE,
        motor_config: Optional[MotorConfig] = None,
        limits: Optional[AntennaLimits] = None,
        calibration_file: str = DEFAULT_CALIBRATION_FILE,
    ) -> AntennaController:
        """Tworzy kontroler z sterownikiem SPID"""
        # Jeśli port nie został podany, użyj inteligentnego wyboru
        if port is None:
            port = get_best_spid_port()
            logger.info(f"Automatycznie wybrano port: {port}")
        else:
            # Sprawdź czy podany port jest dostępny
            port = get_best_spid_port(preferred_port=port)

        motor_driver = RotctlMotorDriver(port, baudrate)
        motor_config = motor_config or MotorConfig()

        return AntennaController(
            motor_driver, motor_config, limits, calibration_file=calibration_file
        )

    @staticmethod
    def create_simulator_controller(
        simulation_speed: float = 1000.0,
        motor_config: Optional[MotorConfig] = None,
        limits: Optional[AntennaLimits] = None,
        calibration_file: str = DEFAULT_CALIBRATION_FILE,
    ) -> AntennaController:
        """Tworzy kontroler z symulatorem"""
        motor_driver = SimulatedMotorDriver(simulation_speed)
        motor_config = motor_config or MotorConfig()

        return AntennaController(
            motor_driver, motor_config, limits, calibration_file=calibration_file
        )


# Przykład użycia
if __name__ == "__main__":

    def status_callback(position: Position, state: AntennaState):
        """Callback wywoływany przy zmianie stanu"""
        print(
            f"Status: {state.value}, Pozycja: Az={position.azimuth:.2f}°, El={position.elevation:.2f}°"
        )

    # Konfiguracja
    motor_config = MotorConfig(
        steps_per_revolution=200,
        microsteps=16,
    )

    # Limity zostaną wczytane z pliku kalibracji automatycznie

    # Przykład użycia z SPID
    try:
        controller = AntennaControllerFactory.create_spid_controller(
            port="/dev/tty.usbserial-A10PDNT7",  # Twój port
            baudrate=DEFAULT_BAUDRATE,
            motor_config=motor_config,
        )
        controller.initialize()  # Próbuj zainicjalizować
        print("Utworzono kontroler SPID")
    except Exception as e:
        # Fallback na symulator jeśli nie można połączyć z prawdziwym urządzeniem
        print(f"Nie można połączyć z SPID ({e}), przełączam na symulator")
        controller = AntennaControllerFactory.create_simulator_controller(
            simulation_speed=2000.0, motor_config=motor_config
        )
        print("Utworzono symulator (brak dostępu do prawdziwego urządzenia)")

    # Przypisanie callbacku
    controller.update_callback = status_callback

    try:
        # Inicjalizacja (jeśli jeszcze nie została wykonana)
        if not hasattr(controller, "_initialized") or not controller._initialized:
            controller.initialize()
            controller._initialized = True
        print("System zainicjalizowany")

        # Test ruchu
        target_positions = [
            Position(20.0, 0.0),
            Position(45.0, 30.0),
            Position(90.0, 45.0),
            Position(0.0, 0.0),  # powrót do pozycji domowej
        ]

        for pos in target_positions:
            print(f"\nRuch do pozycji: Az={pos.azimuth}°, El={pos.elevation}°")
            controller.move_to(pos)

            # Czekaj na zakończenie ruchu
            while controller.state == AntennaState.MOVING:
                time.sleep(0.5)

            print(f"Osiągnięto pozycję: {controller.current_position}")
            time.sleep(1)

        # Test komendy STOP
        print("\nTest komendy STOP...")
        controller.move_to(Position(180.0, 45.0))
        time.sleep(3)  # Pozwól na rozpoczęcie ruchu
        controller.stop()

        # Wyświetl status końcowy
        status = controller.get_status()
        print(f"\nStatus końcowy: {status}")

    except Exception as e:
        print(f"Błąd: {e}")
        logger.error(f"Błąd główny: {e}")

    finally:
        controller.shutdown()
        print("System wyłączony")
