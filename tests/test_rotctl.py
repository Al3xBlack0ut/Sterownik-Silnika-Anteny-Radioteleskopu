"""
Testy protokołu SPID dla Sterownika Anteny Radioteleskopu
Używa biblioteki Hamlib (rotctl) do komunikacji z kontrolerem SPID MD-01/02/03

Test jednostkowy do weryfikacji komunikacji z kontrolerem SPID.
Zawiera testy połączenia, pozycjonowania i odczytu pozycji.

Autor: Aleks Czarnecki
"""

import subprocess
import sys
import unittest
import time
import logging

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Domyślny port SPID
DEFAULT_SPID_PORT = "/dev/tty.usbserial-A10PDNT7"

def ustaw_pozycje(port: str, az: float, el: float, speed: int = 115200):
    """Ustawia pozycję rotatora SPID MD-03 za pomocą rotctl (Hamlib)"""
    komenda = f"P {az % 360:.1f} {el:.1f}\n"

    proc = subprocess.Popen(
        ['rotctl', '-m', '903', '-r', port, '-s', str(speed), '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout, stderr = proc.communicate(input=komenda)

    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl: {stderr.strip()}")

    return stdout.strip()

def odczytaj_pozycje(port: str, speed: int = 115200):
    """
    Odczytuje aktualną pozycję rotatora SPID.
    Zwraca tuple (azymut, elewacja) w stopniach.
    """
    proc = subprocess.Popen(
        ['rotctl', '-m', '903', '-r', port, '-s', str(speed), '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout, stderr = proc.communicate(input="p\n")

    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl: {stderr.strip()}")

    lines = stdout.strip().split('\n')
    values = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('p '):
            try:
                values.append(float(line))
            except ValueError:
                # Sprawdź czy linia zawiera wartość po "p "
                if line.startswith('p '):
                    try:
                        values.append(float(line[2:]))
                    except ValueError:
                        continue

    if len(values) >= 2:
        return values[0], values[1]
    else:
        # Alternatywne parsowanie - spróbuj wyciągnąć liczby z całego tekstu
        import re
        numbers = re.findall(r'[-+]?\d*\.?\d+', stdout)
        if len(numbers) >= 2:
            try:
                return float(numbers[0]), float(numbers[1])
            except ValueError:
                pass

        raise RuntimeError(f"Niepełna odpowiedź pozycji: {stdout}")

def zatrzymaj_rotor(port: str, speed: int = 115200):
    """Zatrzymuje ruch rotatora."""
    proc = subprocess.Popen(
        ['rotctl', '-m', '903', '-r', port, '-s', str(speed), '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    stdout, stderr = proc.communicate(input="S\n")

    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl STOP: {stderr.strip()}")

    return stdout.strip()

def sprawdz_rotctl():
    """Sprawdza czy rotctl jest dostępne w systemie."""
    try:
        result = subprocess.run(['rotctl', '--version'],
                              capture_output=True, text=True, timeout=5, check=False)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def sprawdz_pozycje(port: str, target_az: float, target_el: float, tolerance: float = 1.5,
                   max_attempts: int = 10, wait_time: float = 2.0, speed: int = 115200):
    """
    Sprawdza czy rotor osiągnał zadaną pozycję z określoną tolerancją.

    Args:
        port: Port szeregowy
        target_az: Docelowy azymut w stopniach
        target_el: Docelowa elewacja w stopniach
        tolerance: Tolerancja w stopniach (domyślnie 1.5°)
        max_attempts: Maksymalna liczba prób (domyślnie 10)
        wait_time: Czas oczekiwania między próbami w sekundach
        speed: Prędkość portu

    Returns:
        tuple: (success: bool, final_az: float, final_el: float, attempts: int)
    """
    for attempt in range(max_attempts):
        try:
            current_az, current_el = odczytaj_pozycje(port, speed)

            # Oblicz różnicę, uwzględniając przejście przez 0°/360° dla azymutu
            az_diff = abs(current_az - target_az)
            if az_diff > 180:
                az_diff = 360 - az_diff

            el_diff = abs(current_el - target_el)

            logger.debug(f"Próba {attempt + 1}: Az={current_az:.1f}° (cel {target_az:.1f}°, diff {az_diff:.1f}°), "
                        f"El={current_el:.1f}° (cel {target_el:.1f}°, diff {el_diff:.1f}°)")

            # Sprawdź czy osiągnęliśmy pozycję z tolerancją
            if az_diff <= tolerance and el_diff <= tolerance:
                return True, current_az, current_el, attempt + 1

            # Czekaj przed następną próbą
            if attempt < max_attempts - 1:
                time.sleep(wait_time)

        except Exception as e:
            logger.warning(f"Błąd podczas sprawdzania pozycji (próba {attempt + 1}): {e}")
            time.sleep(wait_time)

    # Ostatni odczyt dla zwrócenia aktualnej pozycji
    try:
        final_az, final_el = odczytaj_pozycje(port, speed)
        return False, final_az, final_el, max_attempts
    except Exception:
        return False, 0.0, 0.0, max_attempts


class SPIDProtocolTests(unittest.TestCase):
    """Testy protokołu komunikacji SPID z użyciem Hamlib"""

    PORT = DEFAULT_SPID_PORT
    BAUDRATE = 115200

    @classmethod
    def setUpClass(cls):
        """Sprawdzenie czy rotctl jest dostępne przed rozpoczęciem testów."""
        if not sprawdz_rotctl():
            raise unittest.SkipTest("rotctl (Hamlib) nie jest dostępne w systemie")

        logger.info("=" * 60)
        logger.info("ROZPOCZĘCIE TESTÓW PROTOKOŁU SPID")
        logger.info(f"Port: {cls.PORT}")
        logger.info(f"Baudrate: {cls.BAUDRATE}")
        logger.info("=" * 60)

    def setUp(self):
        """Przygotowanie do każdego testu."""
        logger.info("-" * 60)
        logger.info(f"Rozpoczęcie testu: {self._testMethodName}")

    def tearDown(self):
        """Sprzątanie po każdym teście."""
        logger.info(f"Zakończenie testu: {self._testMethodName}")
        # Zatrzymaj rotor po każdym teście dla bezpieczeństwa
        try:
            zatrzymaj_rotor(self.PORT, self.BAUDRATE)
            logger.info("Rotor zatrzymany po teście")
        except Exception as e:
            logger.warning(f"Nie można zatrzymać rotora: {e}")

    def test_01_connection_test(self):
        """Test połączenia z kontrolerem SPID."""
        logger.info("Test połączenia z kontrolerem SPID")

        try:
            az, el = odczytaj_pozycje(self.PORT, self.BAUDRATE)
            logger.info(f"Połączenie OK - Pozycja: Az={az:.1f}°, El={el:.1f}°")

            # Sprawdź czy wartości są w rozsądnych zakresach
            self.assertTrue(0 <= az <= 360, f"Azymut poza zakresem: {az}")
            self.assertTrue(-90 <= el <= 90, f"Elewacja poza zakresem: {el}")

        except Exception as e:
            self.fail(f"Błąd połączenia z kontrolerem SPID: {e}")

    def test_02_position_reading(self):
        """Test wielokrotnego odczytu pozycji."""
        logger.info("Test wielokrotnego odczytu pozycji")

        positions = []
        for i in range(3):
            try:
                az, el = odczytaj_pozycje(self.PORT, self.BAUDRATE)
                positions.append((az, el))
                logger.info(f"Odczyt {i+1}: Az={az:.1f}°, El={el:.1f}°")
                time.sleep(0.5)
            except Exception as e:
                self.fail(f"Błąd odczytu pozycji (próba {i+1}): {e}")

        # Sprawdź czy wszystkie odczyty się powiodły
        self.assertEqual(len(positions), 3, "Nie wszystkie odczyty się powiodły")

        # Pozycje powinny być stabilne (maksymalna różnica 1 stopień)
        first_az, first_el = positions[0]
        for az, el in positions[1:]:
            self.assertLess(abs(az - first_az), 2.0, "Niestabilne odczyty azymutu")
            self.assertLess(abs(el - first_el), 2.0, "Niestabilne odczyty elewacji")

    def test_03_safe_position_move(self):
        """Test ruchu do bezpiecznej pozycji (0°, 0°)."""
        logger.info("Test ruchu do bezpiecznej pozycji (0°, 0°)")

        # Odczytaj pozycję początkową
        initial_az, initial_el = odczytaj_pozycje(self.PORT, self.BAUDRATE)
        logger.info(f"Pozycja początkowa: Az={initial_az:.1f}°, El={initial_el:.1f}°")

        # Przejedź do pozycji 0°, 0°
        target_az, target_el = 0.0, 0.0

        try:
            ustaw_pozycje(self.PORT, az=target_az, el=target_el, speed=self.BAUDRATE)
            logger.info(f"Komenda MOVE do ({target_az}°, {target_el}°) wysłana")

            # Sprawdź czy pozycja została osiągnięta
            success, final_az, final_el, attempts = sprawdz_pozycje(
                self.PORT, target_az, target_el, tolerance=2.0, max_attempts=8, wait_time=2.5
            )

            logger.info(f"Pozycja końcowa: Az={final_az:.1f}°, El={final_el:.1f}° (próby: {attempts})")

            # Test zakończony sukcesem tylko jeśli osiągnięto pozycję
            if success:
                logger.info(f"Pozycja ({target_az}°, {target_el}°) osiągnięta pomyślnie")
            else:
                az_diff = abs(final_az - target_az)
                if az_diff > 180:
                    az_diff = 360 - az_diff
                el_diff = abs(final_el - target_el)
                self.fail(f"Nie osiągnięto pozycji ({target_az}°, {target_el}°). "
                         f"Różnica: Az={az_diff:.1f}°, El={el_diff:.1f}°")

        except Exception as e:
            self.fail(f"Błąd podczas ruchu do pozycji ({target_az}°, {target_el}°): {e}")

    def test_04_small_move_test(self):
        """Test małego ruchu (5° w azymucie)."""
        logger.info("Test małego ruchu w azymucie")

        # Odczytaj pozycję początkową
        initial_az, initial_el = odczytaj_pozycje(self.PORT, self.BAUDRATE)
        logger.info(f"Pozycja początkowa: Az={initial_az:.1f}°, El={initial_el:.1f}°")

        # Oblicz nową pozycję (dodaj 5° do azymutu)
        target_az = (initial_az + 5.0) % 360.0
        target_el = initial_el

        try:
            ustaw_pozycje(self.PORT, az=target_az, el=target_el, speed=self.BAUDRATE)
            logger.info(f"Komenda MOVE do Az={target_az:.1f}°, El={target_el:.1f}° wysłana")

            # Sprawdź czy pozycja została osiągnięta
            success, final_az, final_el, attempts = sprawdz_pozycje(
                self.PORT, target_az, target_el, tolerance=1.5, max_attempts=6, wait_time=2.0
            )

            logger.info(f"Pozycja końcowa: Az={final_az:.1f}°, El={final_el:.1f}° (próby: {attempts})")

            # Test zakończony sukcesem tylko jeśli osiągnięto pozycję
            if success:
                logger.info(f"Pozycja Az={target_az:.1f}°, El={target_el:.1f}° osiągnięta pomyślnie")
            else:
                az_diff = abs(final_az - target_az)
                if az_diff > 180:
                    az_diff = 360 - az_diff
                el_diff = abs(final_el - target_el)
                self.fail(f"Nie osiągnięto pozycji Az={target_az:.1f}°, El={target_el:.1f}°. "
                         f"Różnica: Az={az_diff:.1f}°, El={el_diff:.1f}°")

        except Exception as e:
            self.fail(f"Błąd podczas małego ruchu: {e}")

    def test_05_stop_command(self):
        """Test komendy STOP."""
        logger.info("Test komendy STOP")

        try:
            result = zatrzymaj_rotor(self.PORT, self.BAUDRATE)
            logger.info(f"Komenda STOP wykonana: {result}")

            # Sprawdź że rotor odpowiada na komendy po STOP
            time.sleep(1.0)
            az, el = odczytaj_pozycje(self.PORT, self.BAUDRATE)
            logger.info(f"Pozycja po STOP: Az={az:.1f}°, El={el:.1f}°")

        except Exception as e:
            self.fail(f"Błąd podczas wykonywania komendy STOP: {e}")

    def test_06_boundary_positions(self):
        """Test pozycji granicznych (bezpiecznych)."""
        logger.info("Test pozycji granicznych")

        # Testuj tylko bezpieczne pozycje graniczne
        safe_positions = [
            (0.0, 0.0),
            (90.0, -50.0),
            (180.0, 0.0),
            (270.0, 0.0),
            (0.0, 20.0),
            (50.0, 50.0),
        ]

        for az, el in safe_positions:
            with self.subTest(az=az, el=el):
                try:
                    logger.info(f"Test pozycji Az={az}°, El={el}°")
                    ustaw_pozycje(self.PORT, az=az, el=el, speed=self.BAUDRATE)

                    # Krótka pauza
                    time.sleep(1.5)

                    # Sprawdź czy komenda została przyjęta
                    current_az, current_el = odczytaj_pozycje(self.PORT, self.BAUDRATE)
                    logger.info(f"Pozycja po komendzie: Az={current_az:.1f}°, El={current_el:.1f}°")

                except Exception as e:
                    self.fail(f"Błąd przy pozycji ({az}, {el}): {e}")

    def test_07_protocol_sequence(self):
        """Test sekwencji komend: STATUS -> MOVE -> STATUS -> STOP."""
        logger.info("Test sekwencji komend protokołu")

        try:
            # 1. Sprawdź status początkowy
            initial_az, initial_el = odczytaj_pozycje(self.PORT, self.BAUDRATE)
            logger.info(f"Status początkowy: Az={initial_az:.1f}°, El={initial_el:.1f}°")

            # 2. Wykonaj ruch
            target_az = (initial_az + 10.0) % 360.0
            target_el = max(-20.0, min(20.0, initial_el))  # Bezpieczna elewacja

            ustaw_pozycje(self.PORT, az=target_az, el=target_el, speed=self.BAUDRATE)
            logger.info(f"Komenda MOVE do Az={target_az:.1f}°, El={target_el:.1f}°")

            # 3. Sprawdź czy pozycja została osiągnięta
            success, final_az, final_el, attempts = sprawdz_pozycje(
                self.PORT, target_az, target_el, tolerance=2.0, max_attempts=6, wait_time=2.0
            )

            logger.info(f"Status po ruchu: Az={final_az:.1f}°, El={final_el:.1f}° (próby: {attempts})")

            # 4. Zatrzymaj
            zatrzymaj_rotor(self.PORT, self.BAUDRATE)
            logger.info("Rotor zatrzymany")

            # 5. Końcowy status
            time.sleep(1.0)
            status_az, status_el = odczytaj_pozycje(self.PORT, self.BAUDRATE)
            logger.info(f"Status końcowy: Az={status_az:.1f}°, El={status_el:.1f}°")

            # Sprawdź czy test się powiódł
            if success:
                logger.info("Sekwencja protokołu wykonana pomyślnie")
            else:
                az_diff = abs(final_az - target_az)
                if az_diff > 180:
                    az_diff = 360 - az_diff
                el_diff = abs(final_el - target_el)
                self.fail(f"Sekwencja nieudana - nie osiągnięto pozycji docelowej. "
                         f"Różnica: Az={az_diff:.1f}°, El={el_diff:.1f}°")

        except Exception as e:
            self.fail(f"Błąd w sekwencji komend: {e}")


def main():
    """Funkcja główna do uruchamiania testów."""
    if len(sys.argv) > 1:
        # Użyj podanego portu
        SPIDProtocolTests.PORT = sys.argv[1]

    # Uruchom testy
    unittest.main(argv=[''], exit=False, verbosity=2)


if __name__ == "__main__":
    main()
