"""
Testy sprzętowe dla Sterownika Anteny Radioteleskopu
Protokół komunikacji: SPID

Kompletna suita testów automatycznych weryfikujących działanie systemu anteny.
Obejmuje testy połączenia, kalibracji, precyzji ruchu, bezpieczeństwa oraz śledzenia astronomicznego.
Zawiera również testy obciążeniowe i powtarzalności pozycjonowania dla zapewnienia jakości działania.

Autor: Aleks Czarnecki
"""

import os
import unittest
import time
import logging
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import (
    AntennaControllerFactory,
    Position,
    MotorConfig,
    AntennaLimits,
    AntennaState,
    SafetyError,
    SPIDMotorDriver,
    DEFAULT_SPID_PORT,
)

from astronomic_calculator import (
    ObserverLocation,
    AstronomicalCalculator,
    AstronomicalTracker,
)

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("hardware_tests.log"),
    ],
)
logger = logging.getLogger("hardware_tests")


class AntennaHardwareTests(unittest.TestCase):
    """Testy sprzętowe kontrolera anteny"""

    # Konfiguracja dla testów — używa domyślnego portu SPID
    PORT = DEFAULT_SPID_PORT
    BAUDRATE = 115200

    # Współrzędne geograficzne obserwatora (Poznań, Polanka)
    OBSERVER_LAT = 52.40030228321106
    OBSERVER_LON = 16.955077591791788
    OBSERVER_ELEV = 75

    def setUp(self):
        """Przygotowanie do testów — inicjalizacja kontrolera"""
        logger.info("-" * 80)
        logger.info(f"Rozpoczęcie testu: {self._testMethodName}")

        # Konfiguracja silnika
        self.motor_config = MotorConfig(
            steps_per_revolution=200,
            microsteps=16,
            gear_ratio_azimuth=100.0,
            gear_ratio_elevation=80.0,
        )

        # Limity bezpieczeństwa
        self.limits = AntennaLimits(
            min_azimuth=0.0,
            max_azimuth=360.0,
            min_elevation=0.0,  # Minimum 5 stopni nad horyzontem
            max_elevation=85.0,  # Maksimum 85 stopni (unikamy zenitu)
        )

        # Inicjalizacja kontrolera
        try:
            self.controller = AntennaControllerFactory.create_spid_controller(
                port=self.PORT,
                baudrate=self.BAUDRATE,
                motor_config=self.motor_config,
                limits=self.limits,
            )

            self.controller.initialize()
            logger.info("Kontroler zainicjalizowany pomyślnie")

            # Konfiguracja kalkulatora astronomicznego
            self.observer_location = ObserverLocation(
                latitude=self.OBSERVER_LAT,
                longitude=self.OBSERVER_LON,
                elevation=self.OBSERVER_ELEV,
                name="Test Location",
            )
            self.calculator = AstronomicalCalculator(self.observer_location)
            self.tracker = AstronomicalTracker(self.calculator)

        except Exception as e:
            logger.error(f"Błąd inicjalizacji kontrolera: {e}")
            raise

    def tearDown(self):
        """Sprzątanie po testach — bezpieczne wyłączenie kontrolera"""
        try:
            # Sprawdzamy, czy kontroler istnieje i jest zainicjalizowany
            if hasattr(self, "controller"):
                # Powrót do pozycji bezpiecznej
                try:
                    self.move_to_safe_position()
                except Exception as e:
                    logger.error(f"Błąd podczas powrotu do pozycji bezpiecznej: {e}")

                # Wyłączenie kontrolera
                self.controller.shutdown()
                logger.info("Kontroler wyłączony")
        except Exception as e:
            logger.error(f"Błąd podczas wyłączania: {e}")

        logger.info(f"Zakończenie testu: {self._testMethodName}")
        logger.info("-" * 80)

    def move_to_safe_position(self):
        """Przesuwa antenę do bezpiecznej pozycji (azymut = 0, elewacja = 10)"""
        logger.info("Powrót do pozycji bezpiecznej...")

        safe_position = Position(0.0, 10.0)
        self.controller.move_to(safe_position)

        # Czekaj na zakończenie ruchu
        self.wait_for_movement(timeout=30)

        logger.info(
            f"Pozycja bezpieczna osiągnięta: {self.controller.current_position}"
        )

    def wait_for_movement(self, timeout=60):
        """Czeka na zakończenie ruchu z timeoutem"""
        start_time = time.time()
        while self.controller.state == AntennaState.MOVING:
            if time.time() - start_time > timeout:
                self.controller.stop()
                raise TimeoutError(
                    f"Przekroczono czas oczekiwania na ruch ({timeout}s)"
                )
            time.sleep(0.5)

    def test_00_reset(self):
        """Reset stanu błędu sterownika"""
        logger.info("Reset stanu błędu sterownika")

        try:
            # Resetowanie stanu błędu
            self.controller.reset_error()
            logger.info("Stan błędu został zresetowany")

            # Sprawdzenie, czy reset był skuteczny
            self.assertEqual(self.controller.state, AntennaState.IDLE)
            logger.info("Sterownik jest w stanie IDLE po resecie")
        except Exception as e:
            logger.error(f"Błąd podczas resetowania stanu błędu: {e}")
            raise

    def test_01_connection(self):
        """Test połączenia z fizycznym sterownikiem"""
        logger.info("Test połączenia ze sterownikiem")

        # Sprawdzenie stanu kontrolera
        self.assertIsNotNone(self.controller)
        self.assertEqual(self.controller.state, AntennaState.IDLE)

        # Sprawdzenie, czy sterownik to rzeczywiście SPIDMotorDriver
        self.assertIsInstance(self.controller.motor_driver, SPIDMotorDriver)
        self.assertTrue(self.controller.motor_driver.connected)

        # Pobierz aktualną pozycję
        position = self.controller.current_position
        logger.info(
            f"Aktualna pozycja: Az={position.azimuth:.2f}°, El={position.elevation:.2f}°"
        )

        # Sprawdź, czy pozycja jest w sensownych granicach
        self.assertGreaterEqual(position.azimuth, self.limits.min_azimuth)
        self.assertLessEqual(position.azimuth, self.limits.max_azimuth)
        self.assertGreaterEqual(position.elevation, self.limits.min_elevation)
        self.assertLessEqual(position.elevation, self.limits.max_elevation)

    def test_02_calibration(self):
        """Test kalibracji anteny"""
        logger.info("Test kalibracji anteny")

        # Wykonaj kalibrację
        self.controller.calibrate()

        # Czekaj na zakończenie kalibracji
        while (
            self.controller.state == AntennaState.CALIBRATING
            or self.controller.state == AntennaState.MOVING
        ):
            time.sleep(0.5)

        # Sprawdź, czy pozycja po kalibracji jest bliska (0,0)
        position = self.controller.current_position
        logger.info(
            f"Pozycja po kalibracji: Az={position.azimuth:.2f}°, El={position.elevation:.2f}°"
        )

        # Tolerancja na niedokładność mechaniczną
        self.assertAlmostEqual(position.azimuth, 0.0, delta=1.0)
        self.assertAlmostEqual(position.elevation, 0.0, delta=1.0)

    def test_03_basic_movement(self):
        """Test podstawowego ruchu anteny"""
        logger.info("Test podstawowego ruchu")

        # Sekwencja pozycji do testowania
        test_positions = [
            Position(45.0, 30.0),  # Północny-wschód, średnia wysokość
            Position(135.0, 45.0),  # Południowy-wschód, wyżej
            Position(225.0, 30.0),  # Południowy-zachód, średnia wysokość
            Position(315.0, 15.0),  # Północny-zachód, niżej
            Position(0.0, 10.0),  # Powrót do pozycji bezpiecznej
        ]

        for i, pos in enumerate(test_positions):
            logger.info(
                f"Ruch {i+1}/{len(test_positions)}: Az={pos.azimuth:.1f}°, El={pos.elevation:.1f}°"
            )

            start_time = time.time()
            self.controller.move_to(pos)

            # Czekaj na zakończenie ruchu
            self.wait_for_movement()

            # Sprawdź, czy osiągnięto zadaną pozycję z pewną tolerancją
            current = self.controller.current_position
            move_time = time.time() - start_time

            logger.info(
                f"Osiągnięto: Az={current.azimuth:.1f}°, El={current.elevation:.1f}° w {move_time:.1f}s"
            )

            # Tolerancja pozycji (stopnie)
            tolerance = 1.5
            self.assertAlmostEqual(current.azimuth, pos.azimuth, delta=tolerance)
            self.assertAlmostEqual(current.elevation, pos.elevation, delta=tolerance)

            # Krótka pauza między ruchami
            time.sleep(1.0)

    def test_04_precision_movement(self):
        """Test precyzyjnego ruchu w małych krokach"""
        logger.info("Test precyzyjnego ruchu")

        # Rozpocznij od pozycji zerowej
        self.controller.move_to(Position(0.0, 10.0))
        self.wait_for_movement()

        # Seria małych ruchów azymutowych
        for azimuth in [5.0, 10.0, 15.0, 20.0, 25.0]:
            pos = Position(azimuth, 10.0)
            logger.info(f"Precyzyjny ruch do Az={azimuth:.1f}°")

            self.controller.move_to(pos)
            self.wait_for_movement()

            current = self.controller.current_position
            logger.info(f"Osiągnięto: Az={current.azimuth:.2f}°")

            # Dokładniejsza tolerancja
            self.assertAlmostEqual(current.azimuth, azimuth, delta=1.0)

        # Seria małych ruchów elewacyjnych
        for elevation in [15.0, 20.0, 25.0, 30.0]:
            pos = Position(25.0, elevation)
            logger.info(f"Precyzyjny ruch do El={elevation:.1f}°")

            self.controller.move_to(pos)
            self.wait_for_movement()

            current = self.controller.current_position
            logger.info(f"Osiągnięto: El={current.elevation:.2f}°")

            # Dokładniejsza tolerancja
            self.assertAlmostEqual(current.elevation, elevation, delta=1.0)

    def test_05_speed_limits(self):
        """Test limitów prędkości"""
        logger.info("Test limitów prędkości")

        # Zapisz aktualne limity prędkości
        original_az_speed = self.limits.max_azimuth_speed
        original_el_speed = self.limits.max_elevation_speed

        try:
            # Ustaw wolniejsze limity dla testów
            self.limits.max_azimuth_speed = 2.0  # 2 stopnie/s
            self.limits.max_elevation_speed = 1.0  # 1 stopień/s

            # Przesuń do pozycji początkowej
            self.controller.move_to(Position(0.0, 10.0))
            self.wait_for_movement()

            # Wykonaj duży ruch i zmierz czas
            target = Position(90.0, 45.0)  # 90° w azymucie i 35° w elewacji

            logger.info(
                f"Ruch do Az={target.azimuth}°, El={target.elevation}° z ograniczoną prędkością"
            )
            start_time = time.time()

            self.controller.move_to(target)
            self.wait_for_movement()

            elapsed = time.time() - start_time
            logger.info(f"Czas ruchu: {elapsed:.1f}s")

            # Oczekiwany minimalny czas
            # Azymut: 90° przy 2°/s = min 45s
            # Elewacja: 35° przy 1°/s = min 35s
            # Powinien dominować dłuższy czas
            expected_min_time = max(
                90.0 / self.limits.max_azimuth_speed,
                35.0 / self.limits.max_elevation_speed,
            )

            # Sprawdź, czy ruch nie był zbyt szybki (z pewnym marginesem)
            self.assertGreaterEqual(elapsed, expected_min_time * 0.8)

        finally:
            # Przywróć oryginalne limity
            self.limits.max_azimuth_speed = original_az_speed
            self.limits.max_elevation_speed = original_el_speed

    def test_06_emergency_stop(self):
        """Test awaryjnego zatrzymania"""
        logger.info("Test awaryjnego zatrzymania")

        # Ruch do odległej pozycji
        target = Position(180.0, 60.0)
        logger.info(
            f"Rozpoczynanie ruchu do Az={target.azimuth}°, El={target.elevation}°"
        )

        self.controller.move_to(target)

        # Poczekaj chwilę aż ruch się rozpocznie
        time.sleep(2.0)

        # Sprawdź, czy kontroler jest w ruchu
        self.assertEqual(self.controller.state, AntennaState.MOVING)

        # Wykonaj awaryjny stop
        logger.info("Wykonywanie awaryjnego zatrzymania")
        self.controller.stop()

        # Sprawdź, czy zatrzymanie było skuteczne
        time.sleep(1.0)
        self.assertEqual(self.controller.state, AntennaState.STOPPED)

        # Zapisz pozycję zatrzymania
        stop_position = self.controller.current_position
        logger.info(
            f"Pozycja zatrzymania: Az={stop_position.azimuth:.1f}°, El={stop_position.elevation:.1f}°"
        )

        # Poczekaj 3 sekundy i sprawdź, czy pozycja się nie zmieniła
        time.sleep(3.0)
        current_position = self.controller.current_position

        self.assertAlmostEqual(
            current_position.azimuth, stop_position.azimuth, delta=0.5
        )
        self.assertAlmostEqual(
            current_position.elevation, stop_position.elevation, delta=0.5
        )

        logger.info("Awaryjne zatrzymanie działa poprawnie")

    def test_07_safety_limits(self):
        """Test limitów bezpieczeństwa"""
        logger.info("Test limitów bezpieczeństwa")

        # Test limitu minimalnej elewacji
        min_el_target = Position(90.0, self.limits.min_elevation - 1.0)
        logger.info(
            f"Próba ruchu poniżej limitu elewacji: El={min_el_target.elevation:.1f}°"
        )

        with self.assertRaises(SafetyError):
            self.controller.move_to(min_el_target)

        # Test limitu maksymalnej elewacji
        max_el_target = Position(90.0, self.limits.max_elevation + 1.0)
        logger.info(
            f"Próba ruchu powyżej limitu elewacji: El={max_el_target.elevation:.1f}°"
        )

        with self.assertRaises(SafetyError):
            self.controller.move_to(max_el_target)

        # Dla azymutu zakładamy, że zakres 0-360 jest obsługiwany przez normalizację
        # Test będzie polegał na sprawdzeniu, czy wartość jest prawidłowo zwijana
        try:
            over_az_target = Position(
                370.0, 20.0
            )  # 370° powinno być interpretowane jako 10°
            logger.info(
                f"Próba ruchu do Az={over_az_target.azimuth:.1f}° (powinna być znormalizowana)"
            )

            self.controller.move_to(over_az_target)
            self.wait_for_movement()

            # Sprawdzamy, czy pozycja została znormalizowana do zakresu 0-360
            current = self.controller.current_position
            logger.info(f"Osiągnięta pozycja: Az={current.azimuth:.1f}°")

            self.assertGreaterEqual(current.azimuth, 0)
            self.assertLess(current.azimuth, 360)
            self.assertAlmostEqual(current.azimuth, 10.0, delta=1.5)

        except SafetyError:
            # Jeśli implementacja nie obsługuje normalizacji, test również jest zaliczony
            logger.info(
                "Wykryto SafetyError dla azymutu poza zakresem - również poprawne zachowanie"
            )

    def test_08_sun_tracking(self):
        """Test śledzenia Słońca"""
        logger.info("Test śledzenia Słońca")

        # Sprawdź, czy Słońce jest widoczne
        sun_position = self.calculator.get_sun_position()

        if not sun_position.is_visible or sun_position.elevation < 10.0:
            logger.warning(
                f"Słońce nie jest wystarczająco wysoko ({sun_position.elevation:.1f}°) - pomijam test"
            )
            self.skipTest("Słońce nie jest wystarczająco wysoko")

        # Przygotowanie funkcji śledzenia
        sun_tracker = self.tracker.track_sun(min_elevation=5.0)

        # Śledź Słońce przez 5 minut
        logger.info("Rozpoczynanie śledzenia Słońca przez 5 minut")
        tracking_duration = 5 * 60  # 5 minut
        update_interval = 30  # Aktualizacja co 30 sekund

        start_time = time.time()
        end_time = start_time + tracking_duration

        while time.time() < end_time:
            # Pobierz aktualną pozycję Słońca
            sun_pos = sun_tracker()

            if not sun_pos:
                logger.warning("Słońce poza zasięgiem - przerywam śledzenie")
                break

            logger.info(
                f"Pozycja Słońca: Az={sun_pos.azimuth:.2f}°, El={sun_pos.elevation:.2f}°"
            )

            try:
                # Przesuń antenę do pozycji Słońca
                self.controller.move_to(sun_pos)
                self.wait_for_movement()

                # Sprawdź dokładność śledzenia
                current = self.controller.current_position
                sun_actual = self.calculator.get_sun_position().to_antenna_position()

                if sun_actual:
                    # Oblicz odchylenie od aktualnej pozycji Słońca
                    az_error = abs(current.azimuth - sun_actual.azimuth)
                    el_error = abs(current.elevation - sun_actual.elevation)

                    # Uwzględnij przejście przez 0° azymutu
                    if az_error > 180:
                        az_error = 360 - az_error

                    logger.info(
                        f"Dokładność śledzenia: dAz={az_error:.2f}°, dEl={el_error:.2f}°"
                    )

                    # Sprawdzenie z dużą tolerancją (ze względu na powolny ruch Słońca)
                    self.assertLessEqual(
                        az_error, 3.0, "Zbyt duży błąd śledzenia azymutu"
                    )
                    self.assertLessEqual(
                        el_error, 3.0, "Zbyt duży błąd śledzenia elewacji"
                    )

                # Pauza przed następną aktualizacją
                remaining = min(update_interval, int(end_time) - int(time.time()))
                if remaining > 0:
                    time.sleep(remaining)

            except Exception as e:
                logger.error(f"Błąd podczas śledzenia Słońca: {e}")
                self.fail(f"Wyjątek podczas śledzenia Słońca: {e}")

        elapsed = time.time() - start_time
        logger.info(f"Śledzenie Słońca zakończone po {elapsed:.1f}s")

    def test_09_repeated_positioning(self):
        """Test powtarzalności pozycjonowania"""
        logger.info("Test powtarzalności pozycjonowania")

        reference_position = Position(90.0, 45.0)
        repetitions = 5

        # Lista do zapisywania osiągniętych pozycji
        achieved_positions = []

        for i in range(repetitions):
            logger.info(f"Cykl {i+1}/{repetitions}: Ruch do pozycji referencyjnej")

            # Najpierw przesuwamy się do innej pozycji, aby test był miarodajny
            intermediate_pos = Position(0.0, 10.0)
            self.controller.move_to(intermediate_pos)
            self.wait_for_movement()

            # Teraz przesuwamy się do pozycji referencyjnej
            self.controller.move_to(reference_position)
            self.wait_for_movement()

            # Zapisujemy osiągniętą pozycję
            current = self.controller.current_position
            logger.info(
                f"Osiągnięto: Az={current.azimuth:.3f}°, El={current.elevation:.3f}°"
            )

            achieved_positions.append((current.azimuth, current.elevation))

        # Obliczanie odchylenia standardowego dla azymutu i elewacji
        az_values = [pos[0] for pos in achieved_positions]
        el_values = [pos[1] for pos in achieved_positions]

        az_mean = sum(az_values) / len(az_values)
        el_mean = sum(el_values) / len(el_values)

        az_variance = sum((x - az_mean) ** 2 for x in az_values) / len(az_values)
        el_variance = sum((x - el_mean) ** 2 for x in el_values) / len(el_values)

        az_std_dev = az_variance**0.5
        el_std_dev = el_variance**0.5

        logger.info(f"Średnia pozycja: Az={az_mean:.3f}°, El={el_mean:.3f}°")
        logger.info(
            f"Odchylenie standardowe: Az={az_std_dev:.3f}°, El={el_std_dev:.3f}°"
        )

        # Sprawdź powtarzalność (powinna być lepsza niż 1°)
        self.assertLess(az_std_dev, 1.0, "Zbyt duża wariancja azymutu")
        self.assertLess(el_std_dev, 1.0, "Zbyt duża wariancja elewacji")

        # Sprawdź średni błąd względem zadanej pozycji
        az_error = abs(az_mean - reference_position.azimuth)
        el_error = abs(el_mean - reference_position.elevation)

        logger.info(f"Średni błąd: Az={az_error:.3f}°, El={el_error:.3f}°")

        # Błąd systematyczny powinien być mniejszy niż 2°
        self.assertLess(az_error, 2.0, "Zbyt duży błąd systematyczny azymutu")
        self.assertLess(el_error, 2.0, "Zbyt duży błąd systematyczny elewacji")

    def test_10_stress_test(self):
        """Test obciążeniowy — wiele ruchów w pętli"""
        logger.info("Test obciążeniowy - seria ruchów")

        num_cycles = 10
        test_positions = [
            Position(0.0, 10.0),
            Position(90.0, 20.0),
            Position(180.0, 30.0),
            Position(270.0, 20.0),
            Position(0.0, 10.0),
        ]

        logger.info(f"Rozpoczęcie {num_cycles} cykli po {len(test_positions)} pozycji")
        start_time = time.time()

        try:
            for cycle in range(num_cycles):
                logger.info(f"Cykl {cycle+1}/{num_cycles}")

                for i, pos in enumerate(test_positions):
                    logger.info(
                        f"  Pozycja {i+1}/{len(test_positions)}: Az={pos.azimuth}°, El={pos.elevation}°"
                    )

                    self.controller.move_to(pos)
                    self.wait_for_movement(
                        timeout=30
                    )  # Krótszy timeout dla szybszego wykrycia problemów

                    # Krótka pauza między ruchami
                    time.sleep(0.1)

            elapsed = time.time() - start_time
            total_moves = num_cycles * len(test_positions)
            avg_time = elapsed / total_moves

            logger.info(f"Test zakończony: {total_moves} ruchów w {elapsed:.1f}s")
            logger.info(f"Średni czas na ruch: {avg_time:.1f}s")

        except Exception as e:
            logger.error(f"Błąd podczas testu obciążeniowego: {e}")
            self.fail(f"Test obciążeniowy nie powiódł się: {e}")
