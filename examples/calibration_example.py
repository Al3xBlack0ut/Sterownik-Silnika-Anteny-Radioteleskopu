#!/usr/bin/env python3
"""
Przykład użycia funkcji zapisywania i odczytywania kalibracji anteny

Ten skrypt demonstruje jak używać nowych funkcji zarządzania kalibracją
w systemie sterowania anteną radioteleskopu.

Autor: Aleks Czarnecki
"""

import time
import logging
import sys
import os

# Dodaj ścieżkę do głównego folderu projektu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import (
    AntennaControllerFactory, PositionCalibration,
    Position, AntennaState
)

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def demonstrate_calibration_management():
    """Demonstracja zarządzania kalibracją"""
    
    print("=== Demonstracja zarządzania kalibracją anteny ===\n")
    
    # 1. Utworzenie kontrolera (z automatycznym wczytaniem kalibracji)
    print("1. Tworzenie kontrolera z automatycznym wczytaniem kalibracji...")
    controller = AntennaControllerFactory.create_simulator_controller(
        simulation_speed=2000.0,
        calibration_file="calibrations/example_calibration.json"
    )
    
    controller.initialize()
    print(f"   Kontroler utworzony. Plik kalibracji: {controller.calibration_file}")
    
    # Wyświetl aktualną kalibrację
    current_cal = controller.position_calibration
    print("   Aktualna kalibracja:")
    print(f"     - Azymut odwrócony: {current_cal.azimuth_inverted}")
    print(f"     - Offset azymutu: {current_cal.azimuth_offset:.2f}°")
    print(f"     - Elewacja odwrócona: {current_cal.elevation_inverted}")  
    print(f"     - Offset elewacji: {current_cal.elevation_offset:.2f}°")
    print()
    
    # 2. Ustawienie własnej kalibracji
    print("2. Ustawienie własnej kalibracji...")
    custom_calibration = PositionCalibration(
        azimuth_inverted=True,
        azimuth_offset=45.0,
        elevation_inverted=False,
        elevation_offset=-10.0
    )
    
    controller.set_position_calibration(custom_calibration, save_to_file=True)
    print("   Własna kalibracja została ustawiona i zapisana do pliku")
    print()
    
    # 3. Test ruchu z kalibracją
    print("3. Test ruchu z kalibracją...")
    test_position = Position(90.0, 45.0)
    print(f"   Zadana pozycja: Az={test_position.azimuth}°, El={test_position.elevation}°")
    
    # Pokaż jak kalibracja wpływa na pozycję
    calibrated_pos = controller.position_calibration.apply_calibration(test_position)
    print(f"   Pozycja po kalibracji: Az={calibrated_pos.azimuth:.1f}°, El={calibrated_pos.elevation:.1f}°")
    
    controller.move_to(test_position)
    while controller.state == AntennaState.MOVING:
        time.sleep(0.1)
    print("   Ruch zakończony")
    print()
    
    # 4. Demonstracja kalibracji referencji azymutu
    print("4. Kalibracja referencji azymutu...")
    print("   Symulacja pozycji azymutu na 135°...")
    controller.current_position = Position(135.0, 30.0)  # Symulacja pozycji
    
    print(f"   Aktualna pozycja azymutu: {controller.current_position.azimuth}°")
    controller.calibrate_azimuth_reference(save_to_file=True)
    
    new_cal = controller.position_calibration
    print(f"   Nowy offset azymutu: {new_cal.azimuth_offset:.2f}°")
    print("   Kalibracja zapisana do pliku")
    print()
    
    # 5. Resetowanie kalibracji
    print("5. Resetowanie kalibracji do wartości domyślnych...")
    controller.reset_calibration(save_to_file=True)
    
    reset_cal = controller.position_calibration
    print("   Kalibracja po resecie:")
    print(f"     - Azymut odwrócony: {reset_cal.azimuth_inverted}")
    print(f"     - Offset azymutu: {reset_cal.azimuth_offset:.2f}°")
    print(f"     - Elewacja odwrócona: {reset_cal.elevation_inverted}")
    print(f"     - Offset elewacji: {reset_cal.elevation_offset:.2f}°")
    print()
    
    # 6. Wczytanie kalibracji z pliku
    print("6. Demonstracja ręcznego wczytania kalibracji...")
    
    # Najpierw ustawmy jakąś kalibrację i zapiszmy
    test_cal = PositionCalibration(
        azimuth_inverted=False,
        azimuth_offset=30.0,
        elevation_inverted=True,
        elevation_offset=5.0
    )
    
    test_cal.save_to_file("calibrations/test_calibration.json")
    print("   Zapisano testową kalibrację do calibrations/test_calibration.json")
    
    # Teraz wczytaj z pliku
    controller.load_calibration("calibrations/test_calibration.json")
    loaded_cal = controller.position_calibration
    print("   Wczytana kalibracja:")
    print(f"     - Azymut odwrócony: {loaded_cal.azimuth_inverted}")
    print(f"     - Offset azymutu: {loaded_cal.azimuth_offset:.2f}°")
    print(f"     - Elewacja odwrócona: {loaded_cal.elevation_inverted}")
    print(f"     - Offset elewacji: {loaded_cal.elevation_offset:.2f}°")
    print()
    
    # 7. Status z informacjami o kalibracji
    print("7. Status kontrolera z informacjami o kalibracji...")
    status = controller.get_status()
    print(f"   Stan: {status['state']}")
    print(f"   Plik kalibracji: {status['calibration_file']}")
    print(f"   Parametry kalibracji: {status['calibration']}")
    print()
    
    # 8. Export/import kalibracji do/z słownika
    print("8. Export/import kalibracji...")
    cal_dict = controller.position_calibration.export_to_dict()
    print(f"   Eksport do słownika: {cal_dict}")
    
    # Modyfikuj słownik
    cal_dict['azimuth_offset'] = 60.0
    cal_dict['elevation_inverted'] = False
    
    # Import ze słownika
    imported_cal = PositionCalibration.import_from_dict(cal_dict)
    controller.set_position_calibration(imported_cal)
    print(f"   Import ze zmodyfikowanego słownika - nowy offset azymutu: {imported_cal.azimuth_offset:.2f}°")
    print()
    
    # Wyłączenie kontrolera
    controller.shutdown()
    print("=== Demonstracja zakończona ===")


def show_calibration_file_format():
    """Pokazuje format pliku kalibracji"""
    print("\n=== Format pliku kalibracji ===")
    
    # Utwórz przykładową kalibrację
    example_cal = PositionCalibration(
        azimuth_inverted=True,
        azimuth_offset=45.5,
        elevation_inverted=False,
        elevation_offset=-12.3
    )
    
    # Zapisz do pliku
    example_cal.save_to_file("calibrations/example_format.json")
    print("Przykładowy plik kalibracji został zapisany jako 'calibrations/example_format.json'")
    
    # Przeczytaj i wyświetl zawartość
    try:
        with open("calibrations/example_format.json", 'r', encoding='utf-8') as f:
            content = f.read()
            print("Zawartość pliku:")
            print(content)
    except Exception as e:
        print(f"Błąd odczytu pliku: {e}")


if __name__ == "__main__":
    try:
        demonstrate_calibration_management()
        show_calibration_file_format()
        
    except KeyboardInterrupt:
        print("\nPrzerwano przez użytkownika")
    except Exception as e:
        logger.error(f"Błąd podczas demonstracji: {e}")
        print(f"Wystąpił błąd: {e}")
