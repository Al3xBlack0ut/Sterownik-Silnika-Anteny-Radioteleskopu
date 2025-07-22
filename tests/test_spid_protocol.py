"""
Testy protokołu SPID dla Sterownika Anteny Radioteleskopu
Protokół komunikacji: SPID

Test jednostkowy do weryfikacji komunikacji z kontrolerem SPID.
Zawiera testy komend MOVE, STATUS i STOP wraz z weryfikacją odpowiedzi.
Przydatne do weryfikacji połączenia i debugowania problemów komunikacyjnych.

Autor: Aleks Czarnecki
"""

import serial
import time
import unittest
import os
import sys
import logging

# Dodaj ścieżkę do modułów głównych
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import DEFAULT_SPID_PORT

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SPIDProtocolTests(unittest.TestCase):
    """Testy protokołu komunikacji SPID"""

    # Port do testowania - można zmienić na inny port w razie potrzeby
    PORT = DEFAULT_SPID_PORT
    BAUDRATE = 115200
    TIMEOUT = 1.0

    def setUp(self):
        """Przygotowanie do testów"""
        logger.info("-" * 60)
        logger.info(f"Rozpoczęcie testu: {self._testMethodName}")
        self.serial_connection = None

    def tearDown(self):
        """Sprzątanie po testach"""
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
        logger.info(f"Zakończenie testu: {self._testMethodName}")
        logger.info("-" * 60)

    def open_serial_connection(self):
        """Otwiera połączenie szeregowe z kontrolerem SPID"""
        try:
            self.serial_connection = serial.Serial(
                port=self.PORT,
                baudrate=self.BAUDRATE,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=self.TIMEOUT
            )
            logger.info(f"Połączenie z portem {self.PORT} nawiązane")
            return True
        except Exception as e:
            logger.error(f"Błąd połączenia z portem {self.PORT}: {e}")
            self.fail(f"Nie można nawiązać połączenia: {e}")
            return False

    def send_command_and_get_response(self, command: bytes, expected_response_length: int = 12) -> bytes:
        """Wysyła komendę i odbiera odpowiedź"""
        if not self.serial_connection or not self.serial_connection.is_open:
            if not self.open_serial_connection():
                return b''

        try:
            logger.info(f"Wysyłanie komendy: {command.hex().upper()}")
            self.serial_connection.write(command)
            time.sleep(0.1)  # Krótka pauza na przetworzenie

            response = self.serial_connection.read(expected_response_length)
            logger.info(f"Otrzymana odpowiedź: {response.hex().upper()}")

            return response

        except Exception as e:
            logger.error(f"Błąd podczas komunikacji: {e}")
            self.fail(f"Błąd komunikacji: {e}")
            return b''

    def test_01_connection(self):
        """Test nawiązania połączenia z kontrolerem SPID"""
        logger.info("Test nawiązania połączenia")

        success = self.open_serial_connection()
        self.assertTrue(success, "Nie można nawiązać połączenia z kontrolerem")
        self.assertTrue(self.serial_connection.is_open, "Połączenie nie zostało otwarte")

    def test_02_status_command(self):
        """Test komendy STATUS"""
        logger.info("Test komendy STATUS")

        # Komenda STATUS: 0x57 + 10 bajtów zer + 0x1F + 0x20
        status_cmd = b'\x57' + b'\x00' * 10 + b'\x1F' + b'\x20'

        response = self.send_command_and_get_response(status_cmd)

        # Sprawdź podstawowe właściwości odpowiedzi
        self.assertGreater(len(response), 0, "Brak odpowiedzi na komendę STATUS")
        self.assertEqual(response[0], 0x57, "Nieprawidłowy nagłówek odpowiedzi STATUS")

        if len(response) >= 12:
            logger.info("Otrzymano kompletną odpowiedź STATUS (12 bajtów)")
            # Można tutaj dodać więcej szczegółowych sprawdzeń formatów odpowiedzi
        else:
            logger.warning(f"Otrzymano niekompletną odpowiedź STATUS ({len(response)} bajtów)")

    def test_03_move_command(self):
        """Test komendy MOVE z bezpiecznymi wartościami"""
        logger.info("Test komendy MOVE")

        # Bezpieczne wartości testowe
        azimuth = 20    # 20 stopni
        elevation = 30  # 30 stopni (bezpieczna wysokość)

        az_str = f"{azimuth:04d}"  # formatowanie do 4 cyfr
        el_str = f"{elevation:04d}"

        # Komenda MOVE: 0x57 + azimuth(4) + 0x00 + elevation(4) + 0x00 + 0x2F + 0x20
        move_cmd = (
            b'\x57' +
            az_str.encode() +
            b'\x00' +
            el_str.encode() +
            b'\x00' +
            b'\x2F' +
            b'\x20'
        )

        response = self.send_command_and_get_response(move_cmd)

        # Sprawdź odpowiedź
        self.assertGreater(len(response), 0, "Brak odpowiedzi na komendę MOVE")
        self.assertEqual(response[0], 0x57, "Nieprawidłowy nagłówek odpowiedzi MOVE")

        logger.info(f"Komenda MOVE wysłana: Az={azimuth}°, El={elevation}°")

        # Opcjonalnie: sprawdź po chwili pozycję przez STATUS
        time.sleep(1.0)  # Daj czas na rozpoczęcie ruchu

        status_cmd = b'\x57' + b'\x00' * 10 + b'\x1F' + b'\x20'
        status_response = self.send_command_and_get_response(status_cmd)

        if len(status_response) >= 12:
            logger.info("Weryfikacja pozycji po komendzie MOVE przez STATUS")

    def test_04_stop_command(self):
        """Test komendy STOP"""
        logger.info("Test komendy STOP")

        # Komenda STOP: 0x57 + 10 bajtów zer + 0x0F + 0x20
        stop_cmd = b'\x57' + b'\x00' * 10 + b'\x0F' + b'\x20'

        response = self.send_command_and_get_response(stop_cmd)

        # Sprawdź odpowiedź
        self.assertGreater(len(response), 0, "Brak odpowiedzi na komendę STOP")
        self.assertEqual(response[0], 0x57, "Nieprawidłowy nagłówek odpowiedzi STOP")

        logger.info("Komenda STOP wykonana pomyślnie")

    def test_05_protocol_sequence(self):
        """Test sekwencji komend: STATUS -> MOVE -> STATUS -> STOP"""
        logger.info("Test sekwencji komend protokołu SPID")

        # 1. Sprawdź status początkowy
        status_cmd = b'\x57' + b'\x00' * 10 + b'\x1F' + b'\x20'
        initial_status = self.send_command_and_get_response(status_cmd)
        self.assertGreater(len(initial_status), 0, "Brak odpowiedzi na pierwszy STATUS")

        # 2. Wykonaj ruch do bezpiecznej pozycji
        azimuth = 45
        elevation = 25
        az_str = f"{azimuth:04d}"
        el_str = f"{elevation:04d}"

        move_cmd = (
            b'\x57' +
            az_str.encode() +
            b'\x00' +
            el_str.encode() +
            b'\x00' +
            b'\x2F' +
            b'\x20'
        )

        move_response = self.send_command_and_get_response(move_cmd)
        self.assertGreater(len(move_response), 0, "Brak odpowiedzi na komendę MOVE")

        # 3. Sprawdź status po ruchu
        time.sleep(0.5)
        status_after_move = self.send_command_and_get_response(status_cmd)
        self.assertGreater(len(status_after_move), 0, "Brak odpowiedzi na STATUS po MOVE")

        # 4. Zatrzymaj ruch
        stop_cmd = b'\x57' + b'\x00' * 10 + b'\x0F' + b'\x20'
        stop_response = self.send_command_and_get_response(stop_cmd)
        self.assertGreater(len(stop_response), 0, "Brak odpowiedzi na komendę STOP")

        logger.info("Sekwencja komend wykonana pomyślnie")


if __name__ == "__main__":
    try:
        # Uruchom testy
        unittest.main(verbosity=2)
    except KeyboardInterrupt:
        print("\nTesty przerwane przez użytkownika")
    except Exception as e:
        print(f"Błąd podczas testów: {e}")
