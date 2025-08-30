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
import os

# Dodaj ścieżkę do głównego folderu projektu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import (
    PositionCalibration, DEFAULT_CALIBRATION_FILE, DEFAULT_SPID_PORT, DEFAULT_BAUDRATE,
    sprawdz_rotctl
)

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def ustaw_pozycje(port: str, az: float, el: float, speed: int = DEFAULT_BAUDRATE, apply_calibration: bool = True):
    """Ustawia pozycję rotatora SPID MD-03 za pomocą rotctl (Hamlib)"""
    
    # Zastosuj offset kalibracji jeśli włączony
    if apply_calibration:
        try:
            calibration = wczytaj_kalibracje()
            az, el = zastosuj_offset_kalibracji(az, el, calibration)
            logger.debug(f"Pozycja po aplikacji offsetu: Az={az:.1f}°, El={el:.1f}°")
        except Exception as e:
            logger.warning(f"Nie można zastosować kalibracji: {e}")
    
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

def odczytaj_pozycje(port: str, speed: int = DEFAULT_BAUDRATE, apply_calibration: bool = True):
    """
    Odczytuje aktualną pozycję rotatora SPID.
    Zwraca tuple (azymut, elewacja) w stopniach z uwzględnieniem offsetów kalibracji.
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
        raw_az, raw_el = values[0], values[1]
        
        # Zastosuj kompensację offsetu kalibracji jeśli włączona
        if apply_calibration:
            try:
                calibration = wczytaj_kalibracje()
                # Odejmij offsety żeby uzyskać rzeczywistą pozycję
                compensated_az = (raw_az - calibration.azimuth_offset) % 360
                compensated_el = raw_el - calibration.elevation_offset
                logger.debug(f"Pozycja surowa: Az={raw_az:.1f}°, El={raw_el:.1f}°")
                logger.debug(f"Pozycja po kompensacji: Az={compensated_az:.1f}°, El={compensated_el:.1f}°")
                return compensated_az, compensated_el
            except Exception as e:
                logger.warning(f"Nie można zastosować kompensacji kalibracji: {e}")
        
        return raw_az, raw_el
    else:
        # Alternatywne parsowanie - spróbuj wyciągnąć liczby z całego tekstu
        import re
        numbers = re.findall(r'[-+]?\d*\.?\d+', stdout)
        if len(numbers) >= 2:
            try:
                raw_az, raw_el = float(numbers[0]), float(numbers[1])
                
                # Zastosuj kompensację offsetu kalibracji jeśli włączona
                if apply_calibration:
                    try:
                        calibration = wczytaj_kalibracje()
                        # Odejmij offsety żeby uzyskać rzeczywistą pozycję
                        compensated_az = (raw_az - calibration.azimuth_offset) % 360
                        compensated_el = raw_el - calibration.elevation_offset
                        return compensated_az, compensated_el
                    except Exception as e:
                        logger.warning(f"Nie można zastosować kompensacji kalibracji: {e}")
                
                return raw_az, raw_el
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


def sprawdz_pozycje(port: str, target_az: float, target_el: float, tolerance: float = 1.5,
                   timeout: float = 90.0, speed: int = DEFAULT_BAUDRATE):
    """
    Sprawdza czy rotor osiągnął zadaną pozycję z określoną tolerancją.
    Używa inteligentnego czekania sprawdzając pozycję co 0.5s zamiast stałego czekania.
    Przedłuża timeout jeśli wykryje ruch anteny.

    Args:
        port: Port szeregowy
        target_az: Docelowy azymut w stopniach
        target_el: Docelowa elewacja w stopniach
        tolerance: Tolerancja w stopniach (domyślnie 1.5°)
        timeout: Maksymalny czas oczekiwania w sekundach (domyślnie 90s)
        speed: Prędkość portu

    Returns:
        tuple: (success: bool, final_az: float, final_el: float, elapsed_time: float)
    """
    start_time = time.time()
    last_movement_time = start_time
    attempt = 0
    prev_az, prev_el = None, None
    
    while True:
        attempt += 1
        current_time = time.time()
        elapsed_time = current_time - start_time
        
        try:
            current_az, current_el = odczytaj_pozycje(port, speed)

            # Sprawdź czy antena się porusza (porównaj z poprzednią pozycją)
            if prev_az is not None and prev_el is not None:
                az_moved = abs(current_az - prev_az)
                if az_moved > 180:  # Uwzględnij przejście przez 0°
                    az_moved = 360 - az_moved
                el_moved = abs(current_el - prev_el)
                
                # Jeśli antena się porusza (więcej niż 0.2°), zaktualizuj czas ostatniego ruchu
                if az_moved > 0.2 or el_moved > 0.2:
                    last_movement_time = current_time
                    logger.debug(f"Wykryto ruch: dAz={az_moved:.1f}°, dEl={el_moved:.1f}°")

            # Oblicz różnicę od pozycji docelowej
            az_diff = abs(current_az - target_az)
            if az_diff > 180:
                az_diff = 360 - az_diff
            el_diff = abs(current_el - target_el)

            logger.debug(f"Próba {attempt}: Az={current_az:.1f}° (cel {target_az:.1f}°, diff {az_diff:.1f}°), "
                        f"El={current_el:.1f}° (cel {target_el:.1f}°, diff {el_diff:.1f}°), "
                        f"elapsed={elapsed_time:.1f}s")

            # Sprawdź czy osiągnęliśmy pozycję z tolerancją
            if az_diff <= tolerance and el_diff <= tolerance:
                return True, current_az, current_el, elapsed_time

            # Sprawdź timeout - ale tylko jeśli antena nie porusza się przez ostatnie 10 sekund
            time_since_movement = current_time - last_movement_time
            if elapsed_time > timeout and time_since_movement > 10.0:
                logger.warning(f"Timeout po {elapsed_time:.1f}s (brak ruchu przez {time_since_movement:.1f}s)")
                break

            # Zapisz pozycję dla następnej iteracji
            prev_az, prev_el = current_az, current_el
            
            # Czekaj przed następną próbą
            time.sleep(0.5)

        except Exception as e:
            logger.warning(f"Błąd podczas sprawdzania pozycji (próba {attempt}): {e}")
            time.sleep(0.5)

    # Ostatni odczyt dla zwrócenia aktualnej pozycji
    try:
        final_az, final_el = odczytaj_pozycje(port, speed)
        elapsed_time = time.time() - start_time
        return False, final_az, final_el, elapsed_time
    except Exception:
        elapsed_time = time.time() - start_time
        return False, 0.0, 0.0, elapsed_time


def wczytaj_kalibracje(calibration_file=None):
    """Wczytuje kalibrację z pliku"""
    file_path = calibration_file or DEFAULT_CALIBRATION_FILE
    try:
        calibration = PositionCalibration.load_from_file(file_path)
        logger.info(f"Kalibracja wczytana z {file_path}: az_offset={calibration.azimuth_offset:.1f}°, el_offset={calibration.elevation_offset:.1f}°")
        return calibration
    except Exception as e:
        logger.warning(f"Nie można wczytać kalibracji z {file_path}: {e}. Używam wartości domyślnych.")
        return PositionCalibration()


def zastosuj_offset_kalibracji(az: float, el: float, calibration: PositionCalibration):
    """Stosuje offset kalibracji do pozycji"""
    calibrated_az = (az + calibration.azimuth_offset) % 360
    calibrated_el = el + calibration.elevation_offset
    
    # Ogranicz elewację do sensownego zakresu
    calibrated_el = max(calibration.min_elevation, min(calibration.max_elevation, calibrated_el))
    
    return calibrated_az, calibrated_el


class SPIDProtocolTests(unittest.TestCase):
    """Testy protokołu komunikacji SPID z użyciem Hamlib"""

    PORT = DEFAULT_SPID_PORT
    BAUDRATE = DEFAULT_BAUDRATE

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
        
        # Wczytaj kalibrację
        self.calibration = wczytaj_kalibracje()

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
            success, final_az, final_el, elapsed_time = sprawdz_pozycje(
                self.PORT, target_az, target_el, tolerance=2.0, timeout=20.0
            )

            logger.info(f"Pozycja końcowa: Az={final_az:.1f}°, El={final_el:.1f}° (czas: {elapsed_time:.1f}s)")

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
            success, final_az, final_el, elapsed_time = sprawdz_pozycje(
                self.PORT, target_az, target_el, tolerance=1.5, timeout=15.0
            )

            logger.info(f"Pozycja końcowa: Az={final_az:.1f}°, El={final_el:.1f}° (czas: {elapsed_time:.1f}s)")

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
        """Test pozycji granicznych z kalibracją."""
        logger.info("Test pozycji granicznych z kalibracją")

        # Użyj limitów z kalibracji do definiowania bezpiecznych pozycji
        min_az = self.calibration.min_azimuth
        max_az = self.calibration.max_azimuth
        min_el = self.calibration.min_elevation
        max_el = self.calibration.max_elevation
        
        logger.info(f"Limity z kalibracji: Az({min_az:.1f}°-{max_az:.1f}°), El({min_el:.1f}°-{max_el:.1f}°)")

        # Bezpieczne pozycje testowe (przed zastosowaniem offsetu)
        test_positions = [
            (0.0, 10.0),    # Pozycja startowa
            (90.0, 20.0),   # Wschód
            (180.0, 15.0),  # Południe  
            (270.0, 10.0),  # Zachód
            (45.0, max_el - 5.0),   # Prawie maksymalna elewacja
            (0.0, min_el + 5.0),    # Prawie minimalna elewacja
        ]

        for az, el in test_positions:
            with self.subTest(az=az, el=el):
                try:
                    # Zastosuj offset kalibracji
                    calibrated_az, calibrated_el = zastosuj_offset_kalibracji(az, el, self.calibration)
                    
                    logger.info(f"Test pozycji Az={az:.1f}°→{calibrated_az:.1f}°, El={el:.1f}°→{calibrated_el:.1f}°")
                    
                    # Sprawdź czy pozycja po kalibracji jest w bezpiecznych limitach
                    if (calibrated_el < min_el or calibrated_el > max_el or 
                        calibrated_az < min_az or calibrated_az >= max_az):
                        logger.warning(f"Pozycja po kalibracji poza limitami ({calibrated_az:.1f}°, {calibrated_el:.1f}°), pomijam test")
                        continue
                    
                    # Wykonaj ruch do pozycji skalibrowanej (nie stosuj offsetu ponownie)
                    ustaw_pozycje(self.PORT, az=calibrated_az, el=calibrated_el, speed=self.BAUDRATE, apply_calibration=False)

                    # Krótka pauza
                    time.sleep(1.5)

                    # Sprawdź czy komenda została przyjęta (nie stosuj kompensacji ponownie)
                    current_az, current_el = odczytaj_pozycje(self.PORT, self.BAUDRATE, apply_calibration=False)
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
            success, final_az, final_el, elapsed_time = sprawdz_pozycje(
                self.PORT, target_az, target_el, tolerance=2.0, timeout=15.0
            )

            logger.info(f"Status po ruchu: Az={final_az:.1f}°, El={final_el:.1f}° (czas: {elapsed_time:.1f}s)")

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
