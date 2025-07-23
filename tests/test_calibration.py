#!/usr/bin/env python3
"""
Testy jednostkowe dla funkcjonalności zapisywania i odczytywania kalibracji

Test suite dla nowych funkcji zarządzania kalibracją w systemie antenna_controller.
"""

import unittest
import tempfile
import os
import json
import sys

# Dodaj ścieżkę do głównego folderu projektu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import PositionCalibration, AntennaControllerFactory


class TestCalibrationPersistence(unittest.TestCase):
    """Testy dla funkcji zapisywania/odczytywania kalibracji"""

    def setUp(self):
        """Przygotowanie testów"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "test_calibration.json")

    def tearDown(self):
        """Czyszczenie po testach"""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        os.rmdir(self.temp_dir)

    def test_save_and_load_calibration(self):
        """Test zapisywania i wczytywania kalibracji"""
        # Utwórz testową kalibrację
        original = PositionCalibration(
            azimuth_inverted=True,
            azimuth_offset=45.5,
            elevation_inverted=False,
            elevation_offset=-12.3
        )

        # Zapisz do pliku
        original.save_to_file(self.test_file)
        self.assertTrue(os.path.exists(self.test_file))

        # Wczytaj z pliku
        loaded = PositionCalibration.load_from_file(self.test_file)

        # Sprawdź czy wartości są identyczne
        self.assertEqual(original.azimuth_inverted, loaded.azimuth_inverted)
        self.assertAlmostEqual(original.azimuth_offset, loaded.azimuth_offset, places=1)
        self.assertEqual(original.elevation_inverted, loaded.elevation_inverted)
        self.assertAlmostEqual(original.elevation_offset, loaded.elevation_offset, places=1)

    def test_load_nonexistent_file(self):
        """Test wczytywania nieistniejącego pliku (powinna zwrócić domyślną kalibrację)"""
        nonexistent_file = os.path.join(self.temp_dir, "nonexistent.json")
        
        # Should return default calibration without raising exception
        calibration = PositionCalibration.load_from_file(nonexistent_file)
        
        # Check default values
        self.assertFalse(calibration.azimuth_inverted)
        self.assertEqual(calibration.azimuth_offset, 0.0)
        self.assertTrue(calibration.elevation_inverted)
        self.assertEqual(calibration.elevation_offset, 0.0)

    def test_invalid_json_file(self):
        """Test wczytywania nieprawidłowego pliku JSON"""
        # Napisz nieprawidłowy JSON
        with open(self.test_file, 'w', encoding='utf-8') as f:
            f.write("{ invalid json content")

        # Powinien rzucić wyjątek
        with self.assertRaises(Exception):
            PositionCalibration.load_from_file(self.test_file)

    def test_export_import_dict(self):
        """Test eksportu/importu do/z słownika"""
        original = PositionCalibration(
            azimuth_inverted=True,
            azimuth_offset=30.0,
            elevation_inverted=False,
            elevation_offset=5.5
        )

        # Export do słownika
        data_dict = original.export_to_dict()
        
        # Sprawdź czy słownik zawiera wszystkie pola
        expected_keys = ['azimuth_inverted', 'azimuth_offset', 'elevation_inverted', 'elevation_offset']
        for key in expected_keys:
            self.assertIn(key, data_dict)

        # Import ze słownika
        imported = PositionCalibration.import_from_dict(data_dict)

        # Sprawdź czy wartości są identyczne
        self.assertEqual(original.azimuth_inverted, imported.azimuth_inverted)
        self.assertAlmostEqual(original.azimuth_offset, imported.azimuth_offset, places=1)
        self.assertEqual(original.elevation_inverted, imported.elevation_inverted)
        self.assertAlmostEqual(original.elevation_offset, imported.elevation_offset, places=1)

    def test_json_file_format(self):
        """Test formatu pliku JSON"""
        calibration = PositionCalibration(
            azimuth_inverted=True,
            azimuth_offset=60.0,
            elevation_inverted=False,
            elevation_offset=-5.0
        )

        # Zapisz do pliku
        calibration.save_to_file(self.test_file)

        # Odczytaj bezpośrednio jako JSON i sprawdź strukturę
        with open(self.test_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Sprawdź czy wszystkie wymagane pola są obecne
        self.assertIn('azimuth_inverted', data)
        self.assertIn('azimuth_offset', data)
        self.assertIn('elevation_inverted', data)
        self.assertIn('elevation_offset', data)
        self.assertIn('created_at', data)
        self.assertIn('version', data)

        # Sprawdź wartości
        self.assertEqual(data['azimuth_inverted'], True)
        self.assertEqual(data['azimuth_offset'], 60.0)
        self.assertEqual(data['elevation_inverted'], False)
        self.assertEqual(data['elevation_offset'], -5.0)
        self.assertEqual(data['version'], '1.0')


class TestAntennaControllerCalibration(unittest.TestCase):
    """Testy dla funkcji kalibracji w AntennaController"""

    def setUp(self):
        """Przygotowanie testów"""
        self.temp_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.temp_dir, "controller_calibration.json")
        
        # Utwórz kontroler symulatora
        self.controller = AntennaControllerFactory.create_simulator_controller(
            simulation_speed=5000.0,
            calibration_file=self.test_file
        )
        self.controller.initialize()

    def tearDown(self):
        """Czyszczenie po testach"""
        self.controller.shutdown()
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        os.rmdir(self.temp_dir)

    def test_automatic_calibration_save_on_set(self):
        """Test automatycznego zapisywania kalibracji przy ustawianiu"""
        new_calibration = PositionCalibration(
            azimuth_inverted=True,
            azimuth_offset=90.0,
            elevation_inverted=False,
            elevation_offset=10.0
        )

        # Ustaw kalibrację (z automatycznym zapisem)
        self.controller.set_position_calibration(new_calibration, save_to_file=True)

        # Sprawdź czy plik został utworzony
        self.assertTrue(os.path.exists(self.test_file))

        # Wczytaj z pliku i sprawdź wartości
        loaded = PositionCalibration.load_from_file(self.test_file)
        self.assertEqual(loaded.azimuth_inverted, True)
        self.assertAlmostEqual(loaded.azimuth_offset, 90.0, places=1)
        self.assertEqual(loaded.elevation_inverted, False)
        self.assertAlmostEqual(loaded.elevation_offset, 10.0, places=1)

    def test_manual_save_load(self):
        """Test ręcznego zapisywania i wczytywania"""
        # Zmień kalibrację
        self.controller.position_calibration.azimuth_offset = 45.0
        self.controller.position_calibration.elevation_inverted = False

        # Zapisz ręcznie
        self.controller.save_calibration()
        self.assertTrue(os.path.exists(self.test_file))

        # Zmień kalibrację w pamięci
        self.controller.position_calibration.azimuth_offset = 0.0
        self.controller.position_calibration.elevation_inverted = True

        # Wczytaj z pliku
        self.controller.load_calibration()

        # Sprawdź czy wartości zostały przywrócone
        self.assertAlmostEqual(self.controller.position_calibration.azimuth_offset, 45.0, places=1)
        self.assertEqual(self.controller.position_calibration.elevation_inverted, False)

    def test_reset_calibration(self):
        """Test resetowania kalibracji"""
        # Zmień kalibrację
        self.controller.position_calibration.azimuth_offset = 123.0
        self.controller.position_calibration.azimuth_inverted = True

        # Resetuj
        self.controller.reset_calibration(save_to_file=True)

        # Sprawdź czy wartości są domyślne
        self.assertAlmostEqual(self.controller.position_calibration.azimuth_offset, 0.0, places=1)
        self.assertEqual(self.controller.position_calibration.azimuth_inverted, False)

        # Sprawdź czy zostało zapisane do pliku
        loaded = PositionCalibration.load_from_file(self.test_file)
        self.assertAlmostEqual(loaded.azimuth_offset, 0.0, places=1)
        self.assertEqual(loaded.azimuth_inverted, False)

    def test_status_includes_calibration(self):
        """Test czy status zawiera informacje o kalibracji"""
        # Ustaw testową kalibrację
        test_cal = PositionCalibration(
            azimuth_inverted=True,
            azimuth_offset=30.0,
            elevation_inverted=False,
            elevation_offset=15.0
        )
        self.controller.set_position_calibration(test_cal, save_to_file=False)

        # Pobierz status
        status = self.controller.get_status()

        # Sprawdź czy zawiera informacje o kalibracji
        self.assertIn('calibration', status)
        self.assertIn('calibration_file', status)

        cal_info = status['calibration']
        self.assertEqual(cal_info['azimuth_inverted'], True)
        self.assertAlmostEqual(cal_info['azimuth_offset'], 30.0, places=1)
        self.assertEqual(cal_info['elevation_inverted'], False)
        self.assertAlmostEqual(cal_info['elevation_offset'], 15.0, places=1)


if __name__ == '__main__':
    # Uruchom testy
    unittest.main(verbosity=2)
