"""
Praktyczne przykłady użycia Sterownika Anteny Radioteleskopu
Protokół komunikacji: SPID

Ten skrypt zawiera podstawowe przykłady sterowania anteną.

Autor: Aleks Czarnecki
"""

import time
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import (
    AntennaControllerFactory, Position, MotorConfig, AntennaLimits,
    AntennaState
)


# =============================================================================
# PRZYKŁAD 1: Podstawowe sterowanie anteną
# =============================================================================

def basic_antenna_control():
    """Podstawowy przykład sterowania anteną"""
    print("=== Podstawowe sterowanie ===")

    # Konfiguracja systemu
    motor_config = MotorConfig(
        steps_per_revolution=200,
        microsteps=16,
        gear_ratio_azimuth=100.0,
        gear_ratio_elevation=80.0
    )

    limits = AntennaLimits(
        min_azimuth=0.0,
        max_azimuth=360.0,
        min_elevation=5.0,  # Minimalna elewacja 5° (nad horyzontem)
        max_elevation=85.0  # Maksymalna elewacja 85°
    )

    # Tworzenie kontrolera anteny z protokołem SPID
    # Opcja 1: Automatyczne wykrywanie portu
    controller = AntennaControllerFactory.create_spid_controller(
        baudrate=115200,
        motor_config=motor_config,
        limits=limits
    )

    # Opcja 2: Podanie konkretnego portu
    # controller = AntennaControllerFactory.create_spid_controller(
    #     port="/dev/ttyUSB0",  # Konkretny port
    #     baudrate=115200,
    #     motor_config=motor_config,
    #     limits=limits
    # )

    try:
        # Inicjalizacja
        controller.initialize()
        print("✓ System zainicjalizowany")

        # Lista pozycji do odwiedzenia
        positions = [
            Position(45.0, 30.0),  # Północny-wschód, 30° nad horyzontem
            Position(135.0, 45.0),  # Południowy-wschód, 45° nad horyzontem
            Position(225.0, 60.0),  # Południowy-zachód, 60° nad horyzontem
            Position(315.0, 30.0),  # Północny-zachód, 30° nad horyzontem
            Position(0.0, 10.0)  # Północ, 10° nad horyzontem
        ]

        print(f"Rozpoczynam ruch przez {len(positions)} pozycji...")

        for i, pos in enumerate(positions, 1):
            print(f"\n[{i}/{len(positions)}] Ruch do: Az={pos.azimuth}°, El={pos.elevation}°")

            # Wykonaj ruch
            controller.move_to(pos)

            # Monitoruj postęp
            while controller.state == AntennaState.MOVING:
                current = controller.current_position
                print(f"  Aktualna pozycja: Az={current.azimuth:.1f}°, El={current.elevation:.1f}°")
                time.sleep(1.0)

            print(f"✓ Osiągnięto pozycję: {controller.current_position}")
            time.sleep(0.5)  # Krótka pauza

        print("\n✓ Sekwencja ruchów zakończona pomyślnie")

    except Exception as e:
        print(f"✗ Błąd: {e}")
    finally:
        controller.shutdown()
        print("System wyłączony")


# =============================================================================
# PRZYKŁAD 2: Monitorowanie w czasie rzeczywistym
# =============================================================================

class AntennaMonitor:
    """Klasa do monitorowania stanu anteny"""

    def __init__(self):
        self.positions_history = []
        self.state_changes = []
        self.start_time = datetime.now()

    def position_callback(self, position: Position, state: AntennaState):
        """Callback wywoływany przy zmianie stanu"""
        timestamp = datetime.now()

        # Zapisz historię pozycji
        self.positions_history.append({
            'timestamp': timestamp,
            'azimuth': position.azimuth,
            'elevation': position.elevation,
            'state': state.value
        })

        # Wyświetl aktualizację
        elapsed = (timestamp - self.start_time).total_seconds()
        print(f"[{elapsed:6.1f}s] Az:{position.azimuth:6.1f}° El:{position.elevation:5.1f}° Stan:{state.value}")

    def get_statistics(self):
        """Zwraca statystyki ruchu"""
        if not self.positions_history:
            return {}

        azimuths = [p['azimuth'] for p in self.positions_history]
        elevations = [p['elevation'] for p in self.positions_history]

        return {
            'total_samples': len(self.positions_history),
            'azimuth_range': (min(azimuths), max(azimuths)),
            'elevation_range': (min(elevations), max(elevations)),
            'duration_seconds': (datetime.now() - self.start_time).total_seconds()
        }


def monitored_antenna_control():
    """Przykład z monitorowaniem w czasie rzeczywistym"""
    print("\n=== Monitorowanie w czasie rzeczywistym ===")

    # Tworzenie kontrolera i monitora
    controller = AntennaControllerFactory.create_simulator_controller(simulation_speed=2000.0)
    monitor = AntennaMonitor()

    try:
        # Przypisanie callbacku monitorowania
        controller.update_callback = monitor.position_callback
        controller.initialize()

        print("System z monitorowaniem uruchomiony")
        print("Format: [czas] Az:azymut° El:elewacja° Stan:stan")
        print("-" * 60)

        # Wykonaj kilka ruchów
        moves = [
            Position(90.0, 45.0),
            Position(180.0, 30.0),
            Position(270.0, 60.0),
            Position(0.0, 15.0)
        ]

        for pos in moves:
            controller.move_to(pos)

            # Czekaj na zakończenie z monitorowaniem
            while controller.state == AntennaState.MOVING:
                time.sleep(0.2)

            time.sleep(1)  # Pauza między ruchami

        # Wyświetl statystyki
        stats = monitor.get_statistics()
        print("\n" + "=" * 60)
        print("STATYSTYKI SESJI:")
        print(f"Próbek danych: {stats['total_samples']}")
        print(f"Zakres azymutu: {stats['azimuth_range'][0]:.1f}° - {stats['azimuth_range'][1]:.1f}°")
        print(f"Zakres elewacji: {stats['elevation_range'][0]:.1f}° - {stats['elevation_range'][1]:.1f}°")
        print(f"Czas trwania: {stats['duration_seconds']:.1f}s")

    finally:
        controller.shutdown()


# =============================================================================
# PRZYKŁAD 3: Skanowanie nieba w siatce
# =============================================================================

def grid_sky_scan():
    """Systematyczne skanowanie nieba w regularnej siatce"""
    print("\n=== Skanowanie nieba w siatce ===")

    controller = AntennaControllerFactory.create_simulator_controller(simulation_speed=5000.0)

    # Parametry skanowania
    az_start, az_end, az_step = 0, 360, 30  # Co 30° w azymucie
    el_start, el_end, el_step = 0, 30, 10  # Co 20° w elewacji

    # Generowanie siatki pozycji
    scan_positions = []
    for elevation in range(el_start, el_end + 1, el_step):
        for azimuth in range(az_start, az_end, az_step):
            scan_positions.append(Position(float(azimuth), float(elevation)))

    try:
        controller.initialize()

        print(f"Rozpoczynam skanowanie {len(scan_positions)} pozycji")
        print(f"Azymut: {az_start}°-{az_end}° co {az_step}°")
        print(f"Elewacja: {el_start}°-{el_end}° co {el_step}°")
        print("-" * 50)

        scan_start_time = time.time()

        for i, pos in enumerate(scan_positions, 1):
            print(f"[{i:2d}/{len(scan_positions)}] Skanowanie Az={pos.azimuth:3.0f}° El={pos.elevation:2.0f}°", end="")

            # Ruch do pozycji
            move_start = time.time()
            controller.move_to(pos)

            while controller.state == AntennaState.MOVING:
                time.sleep(0.1)

            move_time = time.time() - move_start

            measurement_time = 2.0  # 2 sekundy na pomiar
            print(f" (ruch: {move_time:.1f}s, pomiar: {measurement_time:.1f}s)")

            time.sleep(measurement_time)

        total_time = time.time() - scan_start_time
        print(f"\n✓ Skanowanie zakończone w {total_time:.1f}s")
        print(f"  Średni czas na pozycję: {total_time / len(scan_positions):.1f}s")

    finally:
        controller.shutdown()

# =============================================================================
# Uruchomienie przykładów
# =============================================================================
if __name__ == "__main__":
    # Uruchomienie przykładów
    basic_antenna_control()
    monitored_antenna_control()
    grid_sky_scan()

    print("\nWszystkie przykłady zakończone pomyślnie.")
