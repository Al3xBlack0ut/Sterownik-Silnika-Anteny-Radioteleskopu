"""
Zaawansowane przykłady śledzenia astronomicznego dla Sterownika Anteny Radioteleskopu
Protokół komunikacji: SPID

Demonstruje śledzenie Słońca w czasie rzeczywistym oraz predykcję ścieżek ruchu obiektów niebieskich.
Zawiera algorytmy kompensacji ruchu, interpolacji pozycji oraz inteligentne zarządzanie
długotrwałymi sesjami obserwacyjnymi z uwzględnieniem limitów mechanicznych anteny.

Autor: Aleks Czarnecki
"""

import os
import sys
import time
from datetime import datetime, timezone, timedelta

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import (MotorConfig,
    Position, AntennaState, DEFAULT_SPID_PORT, DEFAULT_BAUDRATE,
    AntennaControllerFactory
)

from astronomic_calculator import (
    AstronomicalCalculator, AstronomicalObjectType, OBSERVATORIES
)

# Dodanie wyjątku SafetyError dla przypadku przekroczenia limitów
class SafetyError(Exception):
    """Wyjątek związany z bezpieczeństwem anteny"""


# =============================================================================
# PRZYKŁAD 1: Śledzenie Słońca w czasie rzeczywistym
# =============================================================================

def track_sun_realtime():
    """Śledzenie Słońca w czasie rzeczywistym"""
    print("=== Śledzenie Słońca w czasie rzeczywistym ===")

    # Konfiguracja lokalizacji
    observer_location = OBSERVATORIES['poznan']
    print(f"Lokalizacja: {observer_location.name} "
          f"({observer_location.latitude:.4f}°N, {observer_location.longitude:.4f}°E)")

    # Konfiguracja kalkulatora astronomicznego
    calculator = AstronomicalCalculator(observer_location)

    # Konfiguracja kontrolera anteny
    motor_config = MotorConfig(
        steps_per_revolution=200,
        microsteps=16
    )

    # Tworzenie kontrolera z protokołem SPID
    controller = AntennaControllerFactory.create_spid_controller(
        port=DEFAULT_SPID_PORT,  # Używa domyślnego portu SPID
        baudrate=DEFAULT_BAUDRATE,
        motor_config=motor_config
    )

    # Klasa pomocnicza do śledzenia
    class SunTrackingMonitor:
        """Klasa do monitorowania śledzenia Słońca"""
        def __init__(self):
            self.tracking = False
            self.current_sun_position = None
            self.path_history = []
            self.start_time = datetime.now()

        def position_callback(self, position: Position, _state: AntennaState):
            """Callback wywoływany przy aktualizacji pozycji"""
            elapsed = (datetime.now() - self.start_time).total_seconds()
            if self.current_sun_position:
                print(f"[{elapsed:6.1f}s] "
                      f"Antena: Az={position.azimuth:6.1f}° El={position.elevation:5.1f}° | "
                      f"Słońce: Az={self.current_sun_position.azimuth:6.1f}° El={self.current_sun_position.elevation:5.1f}°")
            else:
                print(f"[{elapsed:6.1f}s] "
                      f"Antena: Az={position.azimuth:6.1f}° El={position.elevation:5.1f}° | "
                      f"Słońce: --")

            # Zapisz historię
            self.path_history.append({
                'time': elapsed,
                'antenna_az': position.azimuth,
                'antenna_el': position.elevation,
                'sun_az': self.current_sun_position.azimuth if self.current_sun_position else None,
                'sun_el': self.current_sun_position.elevation if self.current_sun_position else None
            })

    # Stworzenie monitora i przypisanie callbacka
    monitor = SunTrackingMonitor()
    controller.update_callback = monitor.position_callback

    try:
        controller.initialize()
        print("Kontroler anteny zainicjalizowany")
        print("Rozpoczynam śledzenie Słońca...")
        print("-" * 70)

        monitor.tracking = True
        start_time = time.time()

        # Główna pętla śledzenia będzie działać przez 5 minut
        tracking_duration = 300
        update_interval = 5

        while time.time() - start_time < tracking_duration:
            # Pobierz aktualną pozycję Słońca
            sun_position = calculator.get_sun_position()
            monitor.current_sun_position = sun_position

            # Przelicz na pozycję anteny
            antenna_position = sun_position.to_antenna_position()

            if antenna_position:
                # Aktualizuj pozycję anteny
                controller.move_to(antenna_position)
                # Pokaż czas wschodu/zachodu
                if len(monitor.path_history) <= 1:  # Tylko raz na początku
                    sun_times = calculator.calculate_rise_set_times(AstronomicalObjectType.SUN)
                    print("\nSłońce dzisiaj:")
                    for event, time_val in sun_times.items():
                        if time_val:
                            print(f"  {event}: {time_val.strftime('%H:%M:%S')}")
            else:
                print("Słońce poniżej minimalnej elewacji - śledzenie wstrzymane")

            # Poczekaj na następną aktualizację
            time.sleep(update_interval)

        print("\n✓ Śledzenie zakończone po upływie czasu")

        # Statystyki śledzenia
        if monitor.path_history:
            print("\nStatystyki śledzenia:")
            sun_elevations = [p['sun_el'] for p in monitor.path_history if p['sun_el'] is not None]
            if sun_elevations:
                print(f"Zmiana elewacji Słońca: {min(sun_elevations):.2f}° → {max(sun_elevations):.2f}°")
            print(f"Czas śledzenia: {monitor.path_history[-1]['time']:.1f}s")

    except Exception as e:
        print(f"✗ Błąd podczas śledzenia: {e}")
    finally:
        controller.shutdown()
        print("System wyłączony")


# =============================================================================
# PRZYKŁAD 2: Śledzenie Słońca z predykcją ścieżki
# =============================================================================

def track_sun_with_prediction():
    """Śledzenie Słońca z predykcją ścieżki"""
    print("\n=== PRZYKŁAD 2: Śledzenie Słońca z predykcją ścieżki ===")

    # Konfiguracja lokalizacji
    observer_location = OBSERVATORIES['poznan']

    # Konfiguracja kalkulatora astronomicznego
    calculator = AstronomicalCalculator(observer_location)

    # Parametry predykcji
    prediction_hours = 2  # Predykcja na 2 godziny
    prediction_step_minutes = 5  # Co 5 minut

    # Ustawienie konkretnej daty do predykcji - letnie południe dla zapewnienia widoczności słońca
    current_time = datetime(2025, 6, 21, 12, 0, 0, tzinfo=timezone.utc)

    print(f"Czas symulacji: {current_time.strftime('%d/%m/%Y %H:%M:%S UTC')}")

    # Obliczanie przewidywanej ścieżki Słońca
    print(f"Obliczam przewidywaną ścieżkę Słońca na {prediction_hours} godzin...")
    predicted_path = []

    for minutes in range(0, prediction_hours * 60 + 1, prediction_step_minutes):
        prediction_time = current_time + timedelta(minutes=minutes)
        sun_position = calculator.get_sun_position(observation_time=prediction_time)

        # Używamy niższego progu elewacji, aby mieć więcej punktów
        antenna_position = sun_position.to_antenna_position()

        # Podgląd wartości
        print(f"Czas: {prediction_time.strftime('%H:%M:%S')} - "
              f"Az: {sun_position.azimuth:.2f}°, El: {sun_position.elevation:.2f}° - "
              f"Widoczny: {sun_position.is_visible} - Pozycja anteny: {'Tak' if antenna_position else 'Nie'}")

        if antenna_position:
            predicted_path.append({
                'time': prediction_time,
                'minutes_from_now': minutes,
                'position': antenna_position,
                'sun_position': sun_position
            })
        else:
            print(f"Pominięto punkt w czasie {prediction_time.strftime('%H:%M:%S')} - "
                  f"elewacja {sun_position.elevation:.2f}° zbyt niska")

    print(f"✓ Obliczono {len(predicted_path)} punktów ścieżki")

    # Wyświetl fragment przewidywanej ścieżki
    print("\nFragment przewidywanej ścieżki Słońca:")
    print("  Czas           | Azymut    | Elewacja")
    print("-" * 45)

    # Pokaż co 20 minut dla czytelności (ale zapewnij, że przynajmniej kilka punktów będzie pokazane)
    display_step = min(20 // prediction_step_minutes, max(1, len(predicted_path) // 5)) if predicted_path else 1

    for i, point in enumerate(predicted_path):
        if i % display_step == 0 or i == len(predicted_path) - 1:
            time_str = point['time'].strftime('%H:%M:%S')
            az = point['position'].azimuth
            el = point['position'].elevation
            print(f"  {time_str} | {az:8.2f}° | {el:8.2f}°")

    # Sprawdź, czy mamy punkty do śledzenia
    if not predicted_path:
        print("\n⚠ Brak punktów do śledzenia. Sprawdź datę i lokalizację obserwacji.")
        return

    # Konfiguracja kontrolera anteny
    controller = AntennaControllerFactory.create_simulator_controller(
        simulation_speed=4000.0
    )

    # Inicjalizacja zmiennej do przechowywania czasu rozpoczęcia śledzenia
    # WAŻNE: Ta zmienna musi być zdefiniowana PRZED funkcją tracking_callback!
    start_time = None

    # Funkcja monitorująca postęp śledzenia
    def tracking_callback(position: Position, _state: AntennaState):
        """Callback do monitorowania postępu śledzenia"""
        nonlocal start_time
        if start_time is None:
            return

        elapsed = (datetime.now() - start_time).total_seconds()
        minutes_elapsed = elapsed / 60

        # Znajdź najbliższy punkt predykcji
        if predicted_path:
            closest_point = min(predicted_path,
                              key=lambda p: abs(p['minutes_from_now'] - minutes_elapsed))
            target_az = closest_point['position'].azimuth
            target_el = closest_point['position'].elevation

            print(f"[{elapsed:6.1f}s] "
                  f"Antena: Az={position.azimuth:6.1f}° El={position.elevation:5.1f}° | "
                  f"Predykcja: Az={target_az:6.1f}° El={target_el:5.1f}°")

    # Przypisanie callbacku
    controller.update_callback = tracking_callback

    try:
        controller.initialize()
        print("\nRozpoczynanie śledzenia Słońca z wykorzystaniem predykcji...")
        print("-" * 70)

        # Czas rozpoczęcia śledzenia
        start_time = datetime.now()

        # Wykonaj śledzenie przez określony czas
        tracking_duration = 180  # 3 minuty

        # Realizacja ścieżki z predykcji
        for i, point in enumerate(predicted_path):
            # Sprawdź, czy czas śledzenia nie upłynął
            elapsed_seconds = (datetime.now() - start_time).total_seconds()
            if elapsed_seconds >= tracking_duration:
                break

            try:
                # Ruch anteny do przewidywanej pozycji
                controller.move_to(point['position'])

                # Poczekaj na osiągnięcie pozycji lub część czasu między punktami
                wait_start = time.time()
                while controller.state == AntennaState.MOVING:
                    if time.time() - wait_start > 2:  # Maksymalnie 2 sekundy na ruch
                        break
                    time.sleep(0.1)

                # Oblicz czas do następnego punktu
                if i < len(predicted_path) - 1:
                    # Czas między punktami w sekundach (przeskalowany dla demonstracji)
                    wait_time = min(1.0, (prediction_step_minutes * 60) / 120)
                    time.sleep(wait_time)

            except SafetyError as e:
                print(f"⚠ Pozycja poza limitami: {e}")
                continue

        print("\n✓ Śledzenie z predykcją zakończone")

    except Exception as e:
        print(f"✗ Błąd podczas śledzenia z predykcją: {e}")
    finally:
        controller.shutdown()
        print("System wyłączony")


#=============================================================================
# Uruchomienie przykładów
#=============================================================================
if __name__ == "__main__":
    track_sun_realtime()
    track_sun_with_prediction()

    print("\nWszystkie przykłady zaawansowane zakończone pomyślnie.")
