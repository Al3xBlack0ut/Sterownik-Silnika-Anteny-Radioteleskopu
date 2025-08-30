# Sterownik Silnika Anteny Radioteleskopu

Kompletny system sterowania pozycją anteny radioteleskopu z wykorzystaniem protokołu SPID i rotctl (Hamlib)

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-green.svg)](https://fastapi.tiangolo.com/)
[![Hamlib](https://img.shields.io/badge/Hamlib-rotctl-orange.svg)](https://hamlib.github.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Autor: **Aleks Czarnecki**

---

## Spis treści

1. [Wprowadzenie](#wprowadzenie)
2. [Architektura systemu](#architektura-systemu)  
3. [Struktura projektu](#struktura-projektu)
4. [Instalacja i konfiguracja](#instalacja-i-konfiguracja)
5. [API REST Server](#api-rest-server)
6. [Podstawowe użycie](#podstawowe-użycie)
7. [Protokół SPID i rotctl](#protokół-spid-i-rotctl)
8. [Kalkulator astronomiczny](#kalkulator-astronomiczny)
9. [Zarządzanie kalibracją](#zarządzanie-kalibracją)
10. [System bezpieczeństwa](#system-bezpieczeństwa)
11. [Przykłady użycia](#przykłady-użycia)
12. [Rozwiązywanie problemów](#rozwiązywanie-problemów)

---

## Wprowadzenie

**Sterownik Silnika Anteny Radioteleskopu** to zaawansowany system sterowania pozycją anteny z wykorzystaniem protokołu **SPID** przez **rotctl (Hamlib)**. System oferuje kompletne rozwiązanie do precyzyjnego pozycjonowania silnika anteny, śledzenia obiektów astronomicznych i zdalnego sterowania przez API.

### Główne funkcjonalności

- **Protokół SPID** — obsługa kontrolerów MD-01/02/03 przez rotctl (Hamlib)
- **REST API Server** — serwer FastAPI z nowoczesnym interfejsem webowym
- **Precyzyjne pozycjonowanie** — sterowanie azymutem i elewacją z dokładnością do 0.1°
- **Kalkulator astronomiczny** — PyEphem do obliczania pozycji Słońca, Księżyca, planet i gwiazd
- **Automatyczne śledzenie** — ciągłe śledzenie obiektów niebieskich
- **Zarządzanie kalibracją** — trwałe przechowywanie kalibracji w JSON
- **Monitorowanie czasu rzeczywistego** — ciągły monitoring pozycji i stanu
- **System bezpieczeństwa** — limity mechaniczne i awaryjne zatrzymanie
- **Tryb symulatora** — pełne testy bez fizycznego sprzętu
- **Interfejs webowy** — nowoczesny panel kontrolny w przeglądarce

---

## Architektura systemu

```text
┌──────────────────────────────────────┐
│       REST API Server (FastAPI)      │ ← HTTP API + Web Interface
├──────────────────────────────────────┤
│   AstronomicalCalculator (PyEphem)   │ ← Obliczenia astronomiczne  
├──────────────────────────────────────┤
│         AntennaController            │ ← Główny kontroler
├──────────────────────────────────────┤
│      RotctlMotorDriver (Hamlib)      │ ← Sterownik przez rotctl
├──────────────────────────────────────┤
│RotctlMotorDriver│SimulatedMotorDriver│ ← Sterowniki silnika (rzeczywisty/symulator)
└──────────────────────────────────────┘
            ↕ USB/RS232                 
┌──────────────────────────────────────┐
│      Kontroler SPID MD-01/02/03      │ ← Fizyczny kontroler silnika anteny
├──────────────────────────────────────┤
│     Silnik anteny radioteleskopu     │ ← Fizyczny silnik pozycjonujący
└──────────────────────────────────────┘
```

## Struktura projektu

```text
radioteleskop/
├── antenna_controller.py        # Główny kontroler silnika anteny (scentralizowane stałe)
├── astronomic_calculator.py     # Kalkulator astronomiczny PyEphem  
├── emergency_stop.py            # System awaryjnego zatrzymania
├── api_server/                  # REST API Server FastAPI
│   ├── main.py                  # Główny serwer API
│   ├── web_interface.html       # Interfejs webowy
│   ├── start_server.py          # Skrypt startowy
│   └── api_reference.md         # Dokumentacja API endpoints
├── calibrations/                # Kalibracje anteny (JSON)
│   └── antenna_calibration.json # Aktualna kalibracja pozycji
├── examples/                    # Przykłady użycia
│   ├── basic_usage.py           # Podstawowe sterowanie
│   ├── advanced_usage.py        # Zaawansowane funkcje
│   └── calibration_example.py   # Zarządzanie kalibracją
├── tests/                       # Testy jednostkowe
│   ├── tests.py                 # Główne testy systemu
│   ├── test_rotctl.py           # Testy protokołu SPID
│   ├── test_rotctl_min.py       # Test minimalny
│   └── test_calibration.py      # Testy kalibracji
├── requirements.txt             # Zależności Python
└── README.md                    # Ta dokumentacja
```

### Scentralizowane stałe konfiguracyjne

Wszystkie kluczowe parametry konfiguracyjne zostały scentralizowane w **antenna_controller.py**:

```python
# Główne stałe systemu
DEFAULT_SPID_PORT = "/dev/tty.usbserial-A10PDNT7"  # Port SPID
DEFAULT_BAUDRATE = 115200                          # Prędkość transmisji  
DEFAULT_ROTCTL_MODEL = "903"                       # Model SPID w rotctl
DEFAULT_TIMEOUT = 5                                # Timeout operacji
DEFAULT_CALIBRATION_FILE = "calibrations/antenna_calibration.json"
```

---

## Instalacja i konfiguracja

### Wymagania systemowe

- **Python 3.11+** (zalecane)
- **Hamlib** z rotctl
- **Kontroler SPID MD-01/02/03** (opcjonalnie, dostępny tryb symulatora)

### Instalacja krok po kroku

#### 1. Instalacja Hamlib (rotctl)

**Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install libhamlib-utils
```

**macOS:**
```bash
brew install hamlib
```

**Weryfikacja instalacji:**
```bash
rotctl --version
```

#### 2. Instalacja projektu

```bash
# Klonowanie repozytorium
git clone https://github.com/your-repo/radioteleskop.git
cd radioteleskop

# Utworzenie środowiska wirtualnego
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Instalacja zależności
pip install -r requirements.txt
```

#### 3. Test instalacji

```bash
# Test dostępności rotctl
python -c "from antenna_controller import sprawdz_rotctl; print('rotctl dostępny:', sprawdz_rotctl())"

# Test minimalny protokołu SPID (wymaga podłączonego kontrolera)
python tests/test_rotctl_min.py

# Uruchomienie serwera API
cd api_server
python start_server.py
```

---

## API REST Server

### Uruchomienie serwera

```bash
cd api_server
python start_server.py
```

Serwer zostanie uruchomiony pod adresem: **http://localhost:8000**

### Główne endpointy API

| Method | Endpoint | Opis |
|--------|----------|------|
| `GET` | `/` | Panel sterowania webowy |
| `POST` | `/connect` | Połączenie z anteną |
| `GET` | `/status` | Status i pozycja anteny |
| `POST` | `/move` | Ustawienie pozycji |
| `POST` | `/track` | Śledzenie obiektu astronomicznego |
| `POST` | `/stop` | Zatrzymanie ruchu |
| `GET` | `/calibration` | Aktualna kalibracja |
| `POST` | `/calibration` | Aktualizacja kalibracji |
| `GET` | `/diagnostic` | Diagnostyka połączenia |

### Przykłady wywołań API

```bash
# Status anteny
curl http://localhost:8000/status

# Ustawienie pozycji (azymut: 180°, elewacja: 45°)
curl -X POST http://localhost:8000/move \
  -H "Content-Type: application/json" \
  -d '{"azimuth": 180.0, "elevation": 45.0}'

# Śledzenie Słońca
curl -X POST http://localhost:8000/track \
  -H "Content-Type: application/json" \
  -d '{"object_name": "Sun", "object_type": "SUN", "update_interval": 5.0}'

# Zatrzymanie ruchu
curl -X POST http://localhost:8000/stop
```

---

## Podstawowe użycie

### Import głównych klas

```python
from antenna_controller import (
    AntennaControllerFactory, Position, 
    DEFAULT_SPID_PORT, DEFAULT_BAUDRATE
)
```

### Połączenie z anteną SPID

```python
# Utworzenie kontrolera dla prawdziwej anteny SPID
controller = AntennaControllerFactory.create_spid_controller(
    port=DEFAULT_SPID_PORT,
    baudrate=DEFAULT_BAUDRATE
)

# Alternatywnie: tryb symulatora
controller = AntennaControllerFactory.create_simulator_controller(
    simulation_speed=5000.0  # 5000x szybciej niż rzeczywisty ruch
)
```

### Podstawowe operacje

```python
# Ustawienie pozycji
await controller.move_to_position(azimuth=180.0, elevation=45.0)

# Odczyt aktualnej pozycji
position = await controller.get_current_position()
print(f"Pozycja: Az={position.azimuth:.1f}°, El={position.elevation:.1f}°")

# Zatrzymanie ruchu
await controller.stop()
```

---

## Protokół SPID i rotctl

### Obsługiwane modele kontrolerów

- **SPID MD-01** — model podstawowy
- **SPID MD-02** — model rozszerzony  
- **SPID MD-03** — model profesjonalny

### Konfiguracja rotctl

System używa **Hamlib rotctl** z modelem **903** (SPID MD-03 ROT2 mode):

```bash
# Podstawowe polecenia rotctl
rotctl -m 903 -r /dev/tty.usbserial-A10PDNT7 -s 115200 p        # odczyt pozycji
rotctl -m 903 -r /dev/tty.usbserial-A10PDNT7 -s 115200 P 180 45 # ustawienie pozycji
rotctl -m 903 -r /dev/tty.usbserial-A10PDNT7 -s 115200 S        # zatrzymanie
```

### Centralne funkcje rotctl

Wszystkie operacje rotctl zostały scentralizowane w **antenna_controller.py**:

```python
# Sprawdzenie dostępności rotctl
sprawdz_rotctl() -> bool

# Uniwersalna funkcja wywołania rotctl
run_rotctl_command(command: list[str], port: str, baudrate: int, timeout: int)

# Test połączenia ze SPID
test_spid_connection(port: str, baudrate: int) -> bool
```

---

## Kalkulator astronomiczny

### Obsługiwane obiekty

```python
from astronomic_calculator import AstronomicalCalculator, ObserverLocation

# Konfiguracja obserwatora
observer = ObserverLocation(
    latitude=52.2297,   # Warszawa (stopnie)
    longitude=21.0122,  # Warszawa (stopnie)
    elevation=100.0,    # wysokość npm (metry)
    name="Warszawa"
)

calculator = AstronomicalCalculator(observer)
```

### Obliczanie pozycji obiektów

```python
# Pozycja Słońca
sun_position = calculator.get_sun_position()
print(f"Słońce: Az={sun_position.azimuth:.1f}°, El={sun_position.elevation:.1f}°")

# Pozycja Księżyca
moon_position = calculator.get_moon_position()  
print(f"Księżyc: Az={moon_position.azimuth:.1f}°, El={moon_position.elevation:.1f}°")

# Pozycja planety
mars_position = calculator.get_planet_position("Mars")
print(f"Mars: Az={mars_position.azimuth:.1f}°, El={mars_position.elevation:.1f}°")
```

### Automatyczne śledzenie

```python
from astronomic_calculator import AstronomicalTracker

tracker = AstronomicalTracker(calculator)

# Funkcja śledzenia Słońca
track_sun = tracker.track_sun()

# Pętla śledzenia
while True:
    position = track_sun()
    if position.is_visible:
        await controller.move_to_position(position.azimuth, position.elevation)
        print(f"Śledzenie Słońca: Az={position.azimuth:.1f}°, El={position.elevation:.1f}°")
    else:
        print("Słońce poniżej horyzontu")
    
    await asyncio.sleep(10)  # Aktualizacja co 10 sekund
```

---

## Zarządzanie kalibracją

### Struktura pliku kalibracji

```json
{
  "azimuth_offset": 0.0,
  "elevation_offset": 60.0,
  "min_azimuth": 0.0,
  "max_azimuth": 360.0,
  "min_elevation": 0.0,
  "max_elevation": 180.0,
  "max_azimuth_speed": 5.0,
  "max_elevation_speed": 5.0
}
```

### Zarządzanie kalibracją w kodzie

```python
from antenna_controller import PositionCalibration

# Wczytanie kalibracji z pliku
calibration = PositionCalibration.load_from_file("calibrations/antenna_calibration.json")

# Aplikacja offsetu kalibracji
raw_position = Position(azimuth=120.0, elevation=45.0)
calibrated_position = calibration.apply_calibration(raw_position)

# Zapisanie kalibracji
calibration.save_to_file("calibrations/antenna_calibration.json")
```

### Kalibracja przez API

```bash
# Pobranie aktualnej kalibracji
curl http://localhost:8000/calibration

# Aktualizacja offsetu elewacji
curl -X POST http://localhost:8000/calibration \
  -H "Content-Type: application/json" \
  -d '{"elevation_offset": 60.0, "azimuth_offset": 0.0}'
```

---

## System bezpieczeństwa

### Limity mechaniczne

```python
class AntennaLimits:
    min_azimuth: float = 0.0      # Minimalny azymut (stopnie)
    max_azimuth: float = 360.0    # Maksymalny azymut (stopnie)
    min_elevation: float = 0.0    # Minimalna elewacja (stopnie)
    max_elevation: float = 90.0   # Maksymalna elewacja (stopnie)
    max_azimuth_speed: float = 5.0     # Maksymalna prędkość azymutu (°/s)
    max_elevation_speed: float = 5.0   # Maksymalna prędkość elewacji (°/s)
```

### Awaryjne zatrzymanie

```bash
# Skrypt awaryjnego zatrzymania
python emergency_stop.py

# Z niestandardowym portem
python emergency_stop.py /dev/ttyUSB0
```

### Centralna funkcja zatrzymania

```python
from antenna_controller import rotctl_zatrzymaj_rotor

# Zatrzymanie przez rotctl
result = rotctl_zatrzymaj_rotor(DEFAULT_SPID_PORT, DEFAULT_BAUDRATE)
```

---

## Przykłady użycia

### Przykład 1: Podstawowe sterowanie

```python
import asyncio
from antenna_controller import AntennaControllerFactory, DEFAULT_SPID_PORT, DEFAULT_BAUDRATE

async def basic_control():
    # Połączenie z anteną
    controller = AntennaControllerFactory.create_spid_controller(
        port=DEFAULT_SPID_PORT,
        baudrate=DEFAULT_BAUDRATE
    )
    
    # Ustawienie pozycji
    await controller.move_to_position(180.0, 45.0)
    
    # Odczyt pozycji
    position = await controller.get_current_position()
    print(f"Pozycja: Az={position.azimuth:.1f}°, El={position.elevation:.1f}°")
    
    # Zatrzymanie
    await controller.stop()

asyncio.run(basic_control())
```

### Przykład 2: Śledzenie Słońca

```python
import asyncio
from antenna_controller import AntennaControllerFactory
from astronomic_calculator import AstronomicalCalculator, ObserverLocation

async def track_sun():
    # Konfiguracja obserwatora (Warszawa)
    observer = ObserverLocation(52.2297, 21.0122, 100.0, "Warszawa")
    calculator = AstronomicalCalculator(observer)
    
    # Kontroler anteny
    controller = AntennaControllerFactory.create_spid_controller()
    
    while True:
        # Oblicz pozycję Słońca
        sun_position = calculator.get_sun_position()
        
        if sun_position.is_visible:
            # Przenieś antenę
            await controller.move_to_position(
                sun_position.azimuth, 
                sun_position.elevation
            )
            print(f"Śledzenie Słońca: Az={sun_position.azimuth:.1f}°, El={sun_position.elevation:.1f}°")
        else:
            print("Słońce poniżej horyzontu")
            
        await asyncio.sleep(30)  # Aktualizacja co 30 sekund

asyncio.run(track_sun())
```

### Przykład 3: Tryb symulatora

```python
async def simulator_test():
    # Symulator dla testów bez fizycznego sprzętu
    controller = AntennaControllerFactory.create_simulator_controller(
        simulation_speed=5000.0  # 5000x szybciej
    )
    
    # Identyczne API jak prawdziwa antena
    await controller.move_to_position(90.0, 30.0)
    
    position = await controller.get_current_position()
    print(f"Symulator: Az={position.azimuth:.1f}°, El={position.elevation:.1f}°")

asyncio.run(simulator_test())
```

---

## Rozwiązywanie problemów

### Błąd: "rotctl not found"

**Przyczyna:** Hamlib nie jest zainstalowany lub rotctl nie jest dostępny w PATH.

**Rozwiązanie:**
```bash
# Ubuntu/Debian
sudo apt-get install libhamlib-utils

# macOS
brew install hamlib

# Weryfikacja
rotctl --version
```

### Błąd: "Permission denied" na porcie szeregowym

**Przyczyna:** Brak uprawnień do portu szeregowego.

**Rozwiązanie (Linux):**
```bash
# Dodaj użytkownika do grupy dialout
sudo usermod -a -G dialout $USER
# Wyloguj się i zaloguj ponownie

# Sprawdź uprawnienia
ls -la /dev/tty.usbserial-*
```

### Błąd: "Antenna not responding"

**Przyczyna:** Kontroler SPID nie odpowiada lub błędna konfiguracja portu.

**Rozwiązanie:**
```bash
# Test bezpośredni rotctl
rotctl -m 903 -r /dev/tty.usbserial-A10PDNT7 -s 115200 -t 5 get_pos

# Sprawdzenie diagnostyczne przez API
curl http://localhost:8000/diagnostic

# Test minimalny
python tests/test_rotctl_min.py
```

### Debug mode

```python
import logging

# Włączenie szczegółowych logów
logging.basicConfig(level=logging.DEBUG)

# Test połączenia
from antenna_controller import test_spid_connection, DEFAULT_SPID_PORT, DEFAULT_BAUDRATE
result = test_spid_connection(DEFAULT_SPID_PORT, DEFAULT_BAUDRATE)
print(f"Połączenie SPID: {result}")
```

### Testy systemu

```bash
# Test minimalny protokołu SPID
python tests/test_rotctl_min.py

# Testy pełne systemu
python tests/test_rotctl.py

# Test kalibracji
python tests/test_calibration.py

# Uruchomienie wszystkich testów
python -m pytest tests/
```

---

## Wersja i historia zmian

**Wersja:** 1.313 (Sierpień 2025)

---

