"""
Biblioteka do sterowania silnikiem anteny radioteleskopu
Protokół komunikacji: SPID

Główna biblioteka zawierająca kompletny system sterowania anteną radioteleskopu.
Obejmuje sterowniki SPID i symulatory, kontroler pozycji, monitorowanie w czasie
rzeczywistym oraz kompleksową obsługę błędów i limitów bezpieczeństwa.

Autor: Aleks Czarnecki
"""

import serial
import glob
import logging
import platform
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Dict, Any, Callable, List


# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Domyślny port szeregowy dla kontrolera SPID
DEFAULT_SPID_PORT = "/dev/tty.usbserial-A10PDNT7"


def auto_detect_spid_ports() -> List[str]:
    """Automatycznie wykrywa dostępne porty szeregowe dla SPID"""
    ports = []
    system = platform.system()

    if system == "Darwin":  # macOS
        ports.extend(glob.glob("/dev/tty.usbserial*"))
        ports.extend(glob.glob("/dev/cu.usbserial*"))
        ports.extend(glob.glob("/dev/tty.usbmodem*"))
    elif system == "Linux":
        ports.extend(glob.glob("/dev/ttyUSB*"))
        ports.extend(glob.glob("/dev/ttyACM*"))
        ports.extend(glob.glob("/dev/serial/by-id/*"))
    elif system == "Windows":
        # Na Windows użyjemy pyserial.tools.list_ports
        try:
            import serial.tools.list_ports
            win_ports = [port.device for port in serial.tools.list_ports.comports()]
            ports.extend(win_ports)
        except ImportError:
            # Fallback dla Windows
            for i in range(1, 21):
                ports.append(f"COM{i}")

    return sorted(ports)


def find_working_spid_port(baudrate: int = 115200, timeout: float = 0.5) -> Optional[str]:
    """
    Znajduje pierwszy działający port SPID poprzez testowanie połączenia
    """
    detected_ports = auto_detect_spid_ports()
    logger.info(f"Wykryte porty: {detected_ports}")

    for port in detected_ports:
        try:
            logger.debug(f"Testowanie portu: {port}")

            # Testuj połączenie z portem
            ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=timeout
            )

            # Opcjonalnie: wyślij komendę STATUS i sprawdź odpowiedź
            try:
                status_cmd = b'\x57' + b'\x00' * 10 + b'\x1F' + b'\x20'
                ser.write(status_cmd)
                time.sleep(0.1)
                response = ser.read(12)

                # Sprawdź czy odpowiedź wygląda jak SPID (zaczyna się od 0x57)
                if len(response) >= 1 and response[0] == 0x57:
                    ser.close()
                    logger.info(f"Znaleziono działający port SPID: {port}")
                    return port

            except Exception:
                # Jeśli test SPID nie działa, sprawdź przynajmniej czy port się otwiera
                pass

            ser.close()
            logger.debug(f"Port {port} dostępny (ale nie potwierdził protokołu SPID)")

        except (serial.SerialException, OSError) as e:
            logger.debug(f"Port {port} niedostępny: {e}")
            continue

    logger.warning("Nie znaleziono działającego portu SPID")
    return None


def get_best_spid_port(preferred_port: Optional[str] = None, baudrate: int = 115200) -> str:
    """
    Zwraca najlepszy dostępny port SPID
    """
    # 1. Jeśli podano preferowany port, sprawdź czy działa
    if preferred_port:
        try:
            ser = serial.Serial(preferred_port, baudrate=baudrate, timeout=0.5)
            ser.close()
            logger.info(f"Używam podanego portu: {preferred_port}")
            return preferred_port
        except (serial.SerialException, OSError):
            logger.warning(f"Podany port {preferred_port} nie jest dostępny")

    # 2. Spróbuj automatycznie znaleźć działający port
    auto_port = find_working_spid_port(baudrate)
    if auto_port:
        return auto_port

    # 3. Fallback na domyślny port
    logger.info(f"Używam domyślnego portu: {DEFAULT_SPID_PORT}")
    return DEFAULT_SPID_PORT


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
    elevation: float  # stopnie (0-90)

    def __post_init__(self):
        """Walidacja pozycji"""
        if not (0 <= self.azimuth <= 360):
            raise ValueError(f"Azymut musi być w zakresie 0-360°, otrzymano: {self.azimuth}")
        if not (0 <= self.elevation <= 90):
            raise ValueError(f"Elewacja musi być w zakresie 0-90°, otrzymano: {self.elevation}")


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
    """Kalibracja pozycji anteny"""
    azimuth_offset: float = 0.0      # Offset dla azymutu w stopniach (korekta północy)
    azimuth_inverted: bool = False   # Czy oś azymutu jest odwrócona (True = odwrócony kierunek)
    elevation_inverted: bool = False  # Czy oś elewacji jest odwrócona (True = 0° góra, 90° dół)
    elevation_offset: float = 0.0    # Dodatkowy offset dla elewacji w stopniach

    def apply_calibration(self, position: Position) -> Position:
        """Aplikuje kalibrację do pozycji"""
        # Aplikuj odwrócenie azymutu
        if self.azimuth_inverted:
            # Odwróć oś azymutu: 0° staje się 180°, 90° staje się 270°, itd.
            calibrated_azimuth = (360.0 - position.azimuth) % 360
        else:
            calibrated_azimuth = position.azimuth

        # Aplikuj offset azymutu
        calibrated_azimuth = (calibrated_azimuth + self.azimuth_offset) % 360

        # Aplikuj kalibrację elewacji
        if self.elevation_inverted:
            # Odwróć oś elewacji: 0° staje się 90°, 90° staje się 0°
            calibrated_elevation = 90.0 - position.elevation
        else:
            calibrated_elevation = position.elevation

        # Aplikuj offset elewacji
        calibrated_elevation += self.elevation_offset

        # Ogranicz elewację do sensownego zakresu
        calibrated_elevation = max(-90.0, min(90.0, calibrated_elevation))

        return Position(calibrated_azimuth, calibrated_elevation)

    def reverse_calibration(self, calibrated_position: Position) -> Position:
        """Odwraca kalibrację - konwertuje z pozycji skalibrowanej do surowej"""
        # Cofnij offset azymutu
        raw_azimuth = (calibrated_position.azimuth - self.azimuth_offset) % 360

        # Cofnij odwrócenie azymutu
        if self.azimuth_inverted:
            raw_azimuth = (360.0 - raw_azimuth) % 360

        # Cofnij offset elewacji
        raw_elevation = calibrated_position.elevation - self.elevation_offset

        # Cofnij odwrócenie elewacji
        if self.elevation_inverted:
            raw_elevation = 90.0 - raw_elevation

        # Ogranicz do sensownych zakresów
        raw_elevation = max(-90.0, min(90.0, raw_elevation))

        return Position(raw_azimuth, raw_elevation)


class MotorConfig:
    """Konfiguracja silnika z możliwościami kalibracji"""

    def __init__(self, steps_per_revolution: int = 200, microsteps: int = 16,
                 gear_ratio_azimuth: float = 100.0, gear_ratio_elevation: float = 80.0,
                 azimuth_offset: float = 0.0, elevation_offset: float = 0.0,
                 invert_azimuth: bool = False, invert_elevation: bool = False):
        self.steps_per_revolution = steps_per_revolution
        self.microsteps = microsteps
        self.gear_ratio_azimuth = gear_ratio_azimuth
        self.gear_ratio_elevation = gear_ratio_elevation

        # Parametry kalibracji
        self.azimuth_offset = azimuth_offset  # Offset kalibracji azymutu w stopniach
        self.elevation_offset = elevation_offset  # Offset kalibracji elewacji w stopniach
        self.invert_azimuth = invert_azimuth  # Odwrócenie kierunku azymutu
        self.invert_elevation = invert_elevation  # Odwrócenie kierunku elewacji

    @property
    def steps_per_degree_azimuth(self) -> float:
        """Liczba kroków na stopień dla azymutu"""
        return (self.steps_per_revolution * self.microsteps * self.gear_ratio_azimuth) / 360.0

    @property
    def steps_per_degree_elevation(self) -> float:
        """Liczba kroków na stopień dla elewacji"""
        return (self.steps_per_revolution * self.microsteps * self.gear_ratio_elevation) / 360.0

    def apply_calibration(self, azimuth: float, elevation: float) -> Tuple[float, float]:
        """Stosuje kalibrację do pozycji"""
        calibrated_azimuth = azimuth + self.azimuth_offset
        calibrated_elevation = elevation + self.elevation_offset

        if self.invert_azimuth:
            calibrated_azimuth = -calibrated_azimuth

        if self.invert_elevation:
            calibrated_elevation = -calibrated_elevation

        # Normalizuj azymut do zakresu 0-360
        calibrated_azimuth = calibrated_azimuth % 360.0

        # Ogranicz elewację do zakresu -90 do 90
        calibrated_elevation = max(-90.0, min(90.0, calibrated_elevation))

        return calibrated_azimuth, calibrated_elevation

    def reverse_calibration(self, calibrated_azimuth: float, calibrated_elevation: float) -> Tuple[float, float]:
        """Odwraca kalibrację dla uzyskania pozycji raw"""
        azimuth = calibrated_azimuth
        elevation = calibrated_elevation

        if self.invert_azimuth:
            azimuth = -azimuth

        if self.invert_elevation:
            elevation = -elevation

        azimuth = azimuth - self.azimuth_offset
        elevation = elevation - self.elevation_offset

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
    def move_to_position(self, azimuth_steps: int, elevation_steps: int) -> None:
        """Przesuwa silniki do pozycji (w krokach)"""

    @abstractmethod
    def get_position(self) -> Tuple[int, int]:
        """Zwraca aktualną pozycję w krokach (azymut, elewacja)"""

    @abstractmethod
    def stop(self) -> None:
        """Zatrzymuje wszystkie silniki"""

    @abstractmethod
    def is_moving(self) -> bool:
        """Sprawdza czy silniki się poruszają"""


class SPIDMotorDriver(MotorDriver):
    """Sterownik silnika komunikujący się przez protokół SPID"""

    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial_connection: Optional[serial.Serial] = None
        self.connected = False
        self.current_azimuth = 0.0
        self.current_elevation = 0.0
        self.target_azimuth = 0.0
        self.target_elevation = 0.0
        self.is_moving_flag = False

    def connect(self) -> None:
        """Nawiązuje połączenie z kontrolerem SPID"""
        try:
            self.serial_connection = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=8,
                parity='N',
                stopbits=1,
                timeout=1
            )
            time.sleep(0.5)  # Pauza po otwarciu portu
            self.connected = True
            logger.info(f"Połączono z kontrolerem SPID na porcie {self.port} (baudrate: {self.baudrate})")

            # Pobierz aktualną pozycję po połączeniu
            self._update_position()
        except serial.SerialException as e:
            raise CommunicationError(f"Nie można połączyć się z portem {self.port}: {e}")

    def disconnect(self) -> None:
        """Rozłącza połączenie"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        self.connected = False
        logger.info("Rozłączono ze sterownikiem")

    def _send_spid_command(self, cmd: bytes) -> bytes:
        """Wysyła komendę SPID i odbiera odpowiedź"""
        if not self.connected or not self.serial_connection:
            raise CommunicationError("Brak połączenia z kontrolerem SPID")

        try:
            # Wyczyść bufory
            self.serial_connection.reset_input_buffer()
            self.serial_connection.reset_output_buffer()

            # Wyślij komendę
            self.serial_connection.write(cmd)
            logger.debug(f"TX SPID: {cmd.hex().upper()}")

            time.sleep(0.1)  # Krótka pauza

            # Odbierz odpowiedź (oczekiwana 12-bajtowa odpowiedź)
            response = self.serial_connection.read(12)
            logger.debug(f"RX SPID: {response.hex().upper()} ({len(response)} bajtów)")

            return response
        except Exception as e:
            raise CommunicationError(f"Błąd komunikacji SPID: {e}")

    def _decode_spid_response(self, response: bytes) -> dict:
        """Dekoduje odpowiedź z kontrolera SPID i transluje hex na czytelny format"""
        if len(response) < 12:
            logger.warning(f"Niepełna odpowiedź SPID: {len(response)} bajtów - {response.hex().upper()}")
            return {'error': f'Niepełna odpowiedź: {len(response)} bajtów', 'raw_hex': response.hex().upper()}

        try:
            # Struktura odpowiedzi SPID (12 bajtów)
            result = {
                'raw_hex': response.hex().upper(),
                'start_byte': f'0x{response[0]:02X}',        # 0x57 = 'W' - znacznik początku
                'azimuth_data': response[1:5],               # 4 bajty danych azymutu
                'separator1': f'0x{response[5]:02X}',        # 0x00 - separator
                'elevation_data': response[6:10],            # 4 bajty danych elewacji
                'separator2': f'0x{response[10]:02X}',       # 0x00 - separator lub kod statusu
                'end_byte': f'0x{response[11]:02X}'          # Znacznik końca
            }

            # Dekodowanie pozycji azymutu i elewacji z ASCII
            try:
                azimuth_str = result['azimuth_data'].decode('ascii', errors='ignore')
                elevation_str = result['elevation_data'].decode('ascii', errors='ignore')

                # Sprawdź czy dane są liczbami
                if azimuth_str.isdigit() and elevation_str.isdigit():
                    # Konwersja na wartości liczbowe (dzielenie przez 10 dla precyzji dziesiętnej)
                    result['azimuth_degrees'] = float(azimuth_str) / 10.0
                    result['elevation_degrees'] = float(elevation_str) / 10.0
                else:
                    logger.debug(f"Dane pozycji nie są liczbowe: Az='{azimuth_str}', El='{elevation_str}'")
                    result['azimuth_degrees'] = 0.0
                    result['elevation_degrees'] = 0.0

            except (UnicodeDecodeError, ValueError) as e:
                logger.error(f"Błąd dekodowania pozycji z odpowiedzi SPID: {e}")
                result['azimuth_degrees'] = 0.0
                result['elevation_degrees'] = 0.0

            # Dodatkowe informacje o statusie na podstawie bajtów końcowych
            result['status_info'] = self._decode_status_bytes(response[10], response[11])
            result['command_type'] = self._identify_command_type(response[10])

            logger.debug(f"Dekodowana odpowiedź SPID: {result['status_info']}")
            if 'azimuth_degrees' in result and 'elevation_degrees' in result:
                logger.debug(f"Pozycja: Az={result['azimuth_degrees']:.1f}°, El={result['elevation_degrees']:.1f}°")

            return result

        except Exception as e:
            logger.error(f"Błąd dekodowania odpowiedzi SPID: {e}")
            return {'raw_hex': response.hex().upper(), 'error': str(e)}

    def _decode_status_bytes(self, byte1: int, byte2: int) -> str:
        """Dekoduje bajty statusu SPID na czytelny opis"""
        status_info = []

        # Dekodowanie pierwszego bajtu (typ komendy/status)
        command_types = {
            0x00: "Separator/Data",
            0x0F: "STOP Command Response",
            0x1F: "STATUS Query Response",
            0x2F: "MOVE Command Response"
        }

        status_info.append(command_types.get(byte1, f"Unknown Command: 0x{byte1:02X}"))

        # Dekodowanie drugiego bajtu (znacznik końca/status)
        end_markers = {
            0x20: "End Marker OK",
            0x0D: "Carriage Return",
            0x0A: "Line Feed",
            0x00: "NULL Terminator"
        }

        status_info.append(end_markers.get(byte2, f"Unknown End Marker: 0x{byte2:02X}"))

        return " | ".join(status_info)

    def _identify_command_type(self, command_byte: int) -> str:
        """Identyfikuje typ komendy na podstawie bajtu"""
        command_map = {
            0x0F: "STOP",
            0x1F: "STATUS",
            0x2F: "MOVE",
            0x00: "DATA"
        }
        return command_map.get(command_byte, "UNKNOWN")

    def move_to_position(self, azimuth_steps: int, elevation_steps: int) -> None:
        """Przesuwa anteny do pozycji w krokach (konwertowane na stopnie dla SPID)"""
        # Konwersja kroków na stopnie - dostosuj współczynnik zgodnie z konfiguracją
        azimuth_degrees = azimuth_steps / 100.0
        elevation_degrees = elevation_steps / 100.0

        self.move_to_degrees(azimuth_degrees, elevation_degrees)

    def move_to_degrees(self, azimuth: float, elevation: float) -> None:
        """Przesuwa anteny do pozycji w stopniach"""
        try:
            # Ograniczenia bezpieczeństwa
            azimuth = max(0, min(360, azimuth))
            elevation = max(0, min(90, elevation))

            # Formatowanie pozycji do 4 cyfr (zgodnie z protokołem SPID)
            # Mnożenie przez 10 dla precyzji dziesiętnej
            az_str = f"{int(azimuth * 10):04d}"
            el_str = f"{int(elevation * 10):04d}"

            # Budowanie komendy SPID zgodnie z protokołem
            cmd = (
                b'\x57' +                    # Start byte (0x57 = 'W')
                az_str.encode('ascii') +     # Azimuth (4 cyfry ASCII)
                b'\x00' +                   # Separator
                el_str.encode('ascii') +     # Elevation (4 cyfry ASCII)
                b'\x00' +                   # Separator
                b'\x2F' +                   # Move command marker
                b'\x20'                     # End marker
            )

            logger.info(f"SPID: Ruch do pozycji Az={azimuth:.1f}°, El={elevation:.1f}°")
            logger.debug(f"SPID Move Command: {cmd.hex().upper()}")

            # Wyślij komendę
            response = self._send_spid_command(cmd)

            # Dekoduj odpowiedź
            decoded = self._decode_spid_response(response)

            # Ustaw flagi ruchu
            self.target_azimuth = azimuth
            self.target_elevation = elevation
            self.is_moving_flag = True

            logger.info(f"SPID: Komenda ruchu wysłana pomyślnie. Odpowiedź: {decoded.get('raw_hex', 'Brak')}")

        except Exception as e:
            raise CommunicationError(f"Błąd podczas ruchu SPID: {e}")

    def get_position(self) -> Tuple[int, int]:
        """Zwraca aktualną pozycję w krokach"""
        self._update_position()
        # Konwersja stopni na kroki
        azimuth_steps = int(self.current_azimuth * 100)
        elevation_steps = int(self.current_elevation * 100)
        return azimuth_steps, elevation_steps

    def _update_position(self) -> None:
        """Aktualizuje aktualną pozycję z kontrolera za pomocą komendy STATUS"""
        try:
            # Komenda STATUS zgodnie z protokołem SPID
            status_cmd = b'\x57' + b'\x00' * 10 + b'\x1F' + b'\x20'

            logger.debug("SPID: Zapytanie o status pozycji")
            response = self._send_spid_command(status_cmd)
            decoded = self._decode_spid_response(response)

            if decoded and 'azimuth_degrees' in decoded:
                self.current_azimuth = decoded['azimuth_degrees']
                self.current_elevation = decoded['elevation_degrees']

                logger.debug(f"SPID: Aktualna pozycja - Az={self.current_azimuth:.1f}°, El={self.current_elevation:.1f}°")

                # Sprawdź czy ruch został zakończony
                if self.is_moving_flag:
                    az_diff = abs(self.current_azimuth - self.target_azimuth)
                    el_diff = abs(self.current_elevation - self.target_elevation)

                    if az_diff < 1.0 and el_diff < 1.0:  # Tolerancja 1 stopień
                        self.is_moving_flag = False
                        logger.info("SPID: Ruch anteny zakończony")

        except Exception as e:
            logger.warning(f"Nie można zaktualizować pozycji SPID: {e}")

    def stop(self) -> None:
        """Zatrzymuje ruch anteny"""
        try:
            # Komenda STOP zgodnie z protokołem SPID
            stop_cmd = b'\x57' + b'\x00' * 10 + b'\x0F' + b'\x20'

            logger.info("SPID: Wysyłanie komendy STOP")
            response = self._send_spid_command(stop_cmd)

            # Dekoduj odpowiedź
            decoded = self._decode_spid_response(response)

            self.is_moving_flag = False
            logger.info(f"SPID: Zatrzymano ruch anteny. Odpowiedź: {decoded.get('raw_hex', 'Brak')}")

        except Exception as e:
            logger.error(f"Błąd podczas zatrzymywania SPID: {e}")
            raise CommunicationError(f"Nie można zatrzymać anteny: {e}")

    def is_moving(self) -> bool:
        """Sprawdza czy antena się porusza"""
        self._update_position()
        return self.is_moving_flag


class SimulatedMotorDriver(MotorDriver):
    """Symulator sterownika silnika do testów"""

    def __init__(self, simulation_speed: float = 1000.0):
        self.simulation_speed = simulation_speed  # kroki/s
        self.current_azimuth_steps = 0
        self.current_elevation_steps = 0
        self.target_azimuth_steps = 0
        self.target_elevation_steps = 0
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

    def move_to_position(self, azimuth_steps: int, elevation_steps: int) -> None:
        """Symuluje ruch do pozycji"""
        if not self.connected:
            raise CommunicationError("Symulator nie jest połączony")

        self.target_azimuth_steps = azimuth_steps
        self.target_elevation_steps = elevation_steps
        self.is_moving_flag = True
        self.last_move_time = time.time()

        logger.info(f"Symulator: Ruch do pozycji Az={azimuth_steps} kroków, El={elevation_steps} kroków")

    def get_position(self) -> Tuple[int, int]:
        """Zwraca aktualną pozycję z symulacją ruchu"""
        if not self.connected:
            raise CommunicationError("Symulator nie jest połączony")

        if self.is_moving_flag:
            self._simulate_movement()

        return self.current_azimuth_steps, self.current_elevation_steps

    def _simulate_movement(self) -> None:
        """Symuluje płynny ruch anteny"""
        current_time = time.time()
        dt = current_time - self.last_move_time
        self.last_move_time = current_time

        # Oblicz maksymalny ruch w tym kroku czasowym
        max_move = int(self.simulation_speed * dt)

        # Ruch azymutu
        az_diff = self.target_azimuth_steps - self.current_azimuth_steps
        if abs(az_diff) <= max_move:
            self.current_azimuth_steps = self.target_azimuth_steps
        else:
            self.current_azimuth_steps += max_move if az_diff > 0 else -max_move

        # Ruch elewacji
        el_diff = self.target_elevation_steps - self.current_elevation_steps
        if abs(el_diff) <= max_move:
            self.current_elevation_steps = self.target_elevation_steps
        else:
            self.current_elevation_steps += max_move if el_diff > 0 else -max_move

        # Sprawdź czy osiągnięto cel
        if (self.current_azimuth_steps == self.target_azimuth_steps and
            self.current_elevation_steps == self.target_elevation_steps):
            self.is_moving_flag = False
            logger.debug("Symulator: Ruch zakończony")

    def stop(self) -> None:
        """Symuluje zatrzymanie ruchu"""
        self.is_moving_flag = False
        # Ustaw cele na aktualną pozycję
        self.target_azimuth_steps = self.current_azimuth_steps
        self.target_elevation_steps = self.current_elevation_steps
        logger.info("Symulator: Ruch zatrzymany")

    def is_moving(self) -> bool:
        """Sprawdza czy symulator jest w ruchu"""
        if self.is_moving_flag:
            self._simulate_movement()
        return self.is_moving_flag


class AntennaController:
    """Główny kontroler anteny radioteleskopu"""

    def __init__(self, motor_driver: MotorDriver, motor_config: MotorConfig,
                 limits: AntennaLimits, update_callback: Optional[Callable] = None,
                 position_calibration: Optional[PositionCalibration] = None):
        self.motor_driver = motor_driver
        self.motor_config = motor_config
        self.limits = limits
        self.update_callback = update_callback
        self.position_calibration = position_calibration or PositionCalibration()

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
                az_steps, el_steps = self.motor_driver.get_position()
                azimuth = az_steps / self.motor_config.steps_per_degree_azimuth
                elevation = el_steps / self.motor_config.steps_per_degree_elevation

                self.current_position = Position(azimuth, elevation)

                # Sprawdź czy ruch się zakończył
                if self.state == AntennaState.MOVING and not self.motor_driver.is_moving():
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
                    logger.error(f"Zbyt wiele błędów monitorowania pod rząd ({consecutive_errors})")

                # Krótka pauza po błędzie
                time.sleep(0.2)

            time.sleep(0.5)  # Aktualizacja co 500ms

    def _validate_position(self, position: Position) -> None:
        """Waliduje pozycję względem limitów mechanicznych"""
        if not (self.limits.min_azimuth <= position.azimuth <= self.limits.max_azimuth):
            raise SafetyError(f"Azymut {position.azimuth}° poza limitami "
                              f"({self.limits.min_azimuth}°-{self.limits.max_azimuth}°)")

        if not (self.limits.min_elevation <= position.elevation <= self.limits.max_elevation):
            raise SafetyError(f"Elewacja {position.elevation}° poza limitami "
                              f"({self.limits.min_elevation}°-{self.limits.max_elevation}°)")

    def move_to(self, position: Position) -> None:
        """Przesuwa antenę do zadanej pozycji (z uwzględnieniem kalibracji)"""
        if self.state == AntennaState.ERROR:
            raise AntennaError("System w stanie błędu - nie można wykonać ruchu")

        # Aplikuj kalibrację do zadanej pozycji
        calibrated_position = self.position_calibration.apply_calibration(position)

        # Waliduj skalibrowaną pozycję
        self._validate_position(calibrated_position)

        # Przelicz stopnie na kroki
        az_steps = int(calibrated_position.azimuth * self.motor_config.steps_per_degree_azimuth)
        el_steps = int(calibrated_position.elevation * self.motor_config.steps_per_degree_elevation)

        try:
            self.target_position = position  # Zapisz oryginalną pozycję (bez kalibracji)
            self.state = AntennaState.MOVING
            self.motor_driver.move_to_position(az_steps, el_steps)
            logger.info(f"Rozpoczęto ruch do pozycji: {position} (skalibrowana: {calibrated_position})")
        except Exception as e:
            self.state = AntennaState.ERROR
            raise PositionError(f"Błąd podczas ruchu: {e}")

    def get_current_position(self, apply_reverse_calibration: bool = True) -> Position:
        """
        Zwraca aktualną pozycję anteny

        Args:
            apply_reverse_calibration: Czy zastosować odwrotną kalibrację do pozycji surowej
        """
        if apply_reverse_calibration:
            # Zwróć pozycję z odwróconą kalibracją (rzeczywista pozycja logiczna)
            return self.position_calibration.reverse_calibration(self.current_position)
        else:
            # Zwróć surową pozycję z sensora
            return self.current_position

    def set_position_calibration(self, calibration: PositionCalibration) -> None:
        """Ustawia kalibrację pozycji"""
        self.position_calibration = calibration
        logger.info(f"Ustawiono kalibrację pozycji: offset_az={calibration.azimuth_offset}°, "
                   f"inverted_az={calibration.azimuth_inverted}, "
                   f"inverted_el={calibration.elevation_inverted}, offset_el={calibration.elevation_offset}°")

    def calibrate_azimuth_reference(self, current_azimuth: float = None, invert_azimuth: bool = False) -> None:
        """ Kalibruje referencję azymutu """
        if current_azimuth is None:
            current_azimuth = self.current_position.azimuth

        # Oblicz offset potrzebny aby current_azimuth stał się 0°
        offset = -current_azimuth
        self.position_calibration.azimuth_offset = offset
        self.position_calibration.azimuth_inverted = invert_azimuth

        logger.info(f"Skalibrowano azymut: offset={offset}°, odwrócona={invert_azimuth}")


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
            'state': self.state.value,
            'current_position': {
                'azimuth': self.current_position.azimuth,
                'elevation': self.current_position.elevation
            },
            'target_position': {
                'azimuth': self.target_position.azimuth,
                'elevation': self.target_position.elevation
            } if self.target_position else None,
            'is_moving': self.motor_driver.is_moving() if hasattr(self.motor_driver, 'is_moving') else False,
            'limits': {
                'azimuth': (self.limits.min_azimuth, self.limits.max_azimuth),
                'elevation': (self.limits.min_elevation, self.limits.max_elevation)
            }
        }

    def reset_error(self) -> None:
        """Resetuje stan błędu kontrolera"""
        if self.state == AntennaState.ERROR:
            self.state = AntennaState.IDLE
            logger.info("Stan błędu został zresetowany")


class AntennaControllerFactory:
    """Factory do tworzenia kontrolerów anteny"""

    @staticmethod
    def create_spid_controller(port: Optional[str] = None, baudrate: int = 115200,
                               motor_config: Optional[MotorConfig] = None,
                               limits: Optional[AntennaLimits] = None) -> AntennaController:
        """
        Tworzy kontroler z sterownikiem SPID

        Args:
            port: Port szeregowy (jeśli None, zostanie automatycznie wykryty)
            baudrate: Prędkość transmisji
            motor_config: Konfiguracja silników
            limits: Limity mechaniczne
        """
        # Jeśli port nie został podany, użyj inteligentnego wyboru
        if port is None:
            port = get_best_spid_port(baudrate=baudrate)
            logger.info(f"Automatycznie wybrano port: {port}")
        else:
            # Sprawdź czy podany port jest dostępny
            port = get_best_spid_port(preferred_port=port, baudrate=baudrate)

        motor_driver = SPIDMotorDriver(port, baudrate)
        motor_config = motor_config or MotorConfig()
        limits = limits or AntennaLimits()

        return AntennaController(motor_driver, motor_config, limits)

    @staticmethod
    def create_simulator_controller(simulation_speed: float = 1000.0,
                                   motor_config: Optional[MotorConfig] = None,
                                   limits: Optional[AntennaLimits] = None) -> AntennaController:
        """Tworzy kontroler z symulatorem"""
        motor_driver = SimulatedMotorDriver(simulation_speed)
        motor_config = motor_config or MotorConfig()
        limits = limits or AntennaLimits()

        return AntennaController(motor_driver, motor_config, limits)


# Przykład użycia
if __name__ == "__main__":
    def status_callback(position: Position, state: AntennaState):
        """Callback wywoływany przy zmianie stanu"""
        print(f"Status: {state.value}, Pozycja: Az={position.azimuth:.2f}°, El={position.elevation:.2f}°")

    # Konfiguracja
    motor_config = MotorConfig(
        steps_per_revolution=200,
        microsteps=16,
        gear_ratio_azimuth=100.0,
        gear_ratio_elevation=80.0
    )

    limits = AntennaLimits(
        min_azimuth=0.0,
        max_azimuth=360.0,
        min_elevation=0.0,
        max_elevation=90.0
    )

    # Przykład użycia z SPID (zmień port na właściwy)
    try:
        controller = AntennaControllerFactory.create_spid_controller(
            port="/dev/tty.usbserial-A10PDNT7",  # Twój port
            baudrate=115200,
            motor_config=motor_config,
            limits=limits
        )
        controller.initialize()  # Próbuj zainicjalizować
        print("Utworzono kontroler SPID")
    except Exception as e:
        # Fallback na symulator jeśli nie można połączyć z prawdziwym urządzeniem
        print(f"Nie można połączyć z SPID ({e}), przełączam na symulator")
        controller = AntennaControllerFactory.create_simulator_controller(
            simulation_speed=2000.0,
            motor_config=motor_config,
            limits=limits
        )
        print("Utworzono symulator (brak dostępu do prawdziwego urządzenia)")

    # Przypisanie callbacku
    controller.update_callback = status_callback

    try:
        # Inicjalizacja (jeśli jeszcze nie została wykonana)
        if not hasattr(controller, '_initialized') or not controller._initialized:
            controller.initialize()
            controller._initialized = True
        print("System zainicjalizowany")

        # Test ruchu
        target_positions = [
            Position(20.0, 80.0),
            Position(45.0, 30.0),
            Position(90.0, 45.0),
            Position(0.0, 0.0)       # powrót do pozycji domowej
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
        time.sleep(2)  # Pozwól na rozpoczęcie ruchu
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
