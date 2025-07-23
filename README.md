# Sterownik Silnika Anteny Radioteleskopu

Kompletny system sterowania pozycją anteny radioteleskopu z wykorzystaniem protokołu SPID i rotctl

Autor: **Aleks Czarnecki**

---

## Spis treści

1. [Wprowadzenie](#wprowadzenie)
2. [Architektura systemu](#architektura-systemu)  
3. [Struktura projektu](#struktura-projektu)
4. [Instalacja i konfiguracja](#instalacja-i-konfiguracja)
5. [API REST Server](#api-rest-server)
6. [Podstawowe użycie](#podstawowe-użycie)
7. [Protokol SPID i rotctl](#protokol-spid-i-rotctl)
8. [Kalkulator astronomiczny](#kalkulator-astronomiczny)
9. [Zarządzanie kalibracją](#zarządzanie-kalibracją)
10. [System bezpieczeństwa](#system-bezpieczeństwa)
11. [Przykłady użycia](#przykłady-użycia)
12. [Rozwiązywanie problemów](#rozwiazywanie-problemow)

---

## Wprowadzenie

**Sterownik Silnika Anteny Radioteleskopu** to zaawansowany system sterowania pozycją anteny z wykorzystaniem protokołu **SPID** przez **rotctl (Hamlib)**. System oferuje kompletne rozwiązanie do precyzyjnego pozycjonowania silnika anteny, śledzenia obiektów astronomicznych i zdalnego sterowania przez API.

### Główne funkcjonalności

- Protokół SPID — obsługa kontrolerów MD-01/02/03 przez rotctl (Hamlib)
- REST API Server — serwer FastAPI z nowoczesnym interfejsem webowym
- Precyzyjne pozycjonowanie — sterowanie azymutem i elewacją z dokładnością do 0.1°
- Kalkulator astronomiczny — PyEphem do obliczania pozycji Słońca, Księżyca, planet i gwiazd
- Automatyczne śledzenie — ciągłe śledzenie obiektów niebieskich
- Zarządzanie kalibracją — trwałe przechowywanie kalibracji w JSON
- Monitorowanie czasu rzeczywistego — ciągły monitoring pozycji i stanu
- System bezpieczeństwa — limity mechaniczne i awaryjne zatrzymanie
- Tryb symulatora — pełne testy bez fizycznego sprzętu
- Interfejs webowy — nowoczesny panel kontrolny w przeglądarce

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
├── antenna_controller.py        # Główny kontroler silnika anteny
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
│   ├── test_spid_protocol.py    # Testy protokołu SPID
│   ├── test_calibration.py      # Testy kalibracji
│   └── test_spid_protocol.py    # Minimalne testy
├── requirements.txt             # Zależności Python
└── README.md                    # Ta dokumentacja
```

---

## Instalacja i konfiguracja

### Wymagania systemowe

- **Python 3.8+** (zalecane 3.11+)
- **rotctl (Hamlib)** — narzędzie do komunikacji z kontrolerem SPID
- **Port USB/RS232** — wymagany do połączenia z kontrolerem SPID
- **System operacyjny:** Linux/macOS/Windows

### Instalacja rotctl (Hamlib)

**WAŻNE:** rotctl musi być zainstalowany systemowo przed instalacją Python packages!

#### Linux

```bash
sudo apt-get update
sudo apt-get install hamlib-utils
```

#### macOS (Homebrew)

```bash
brew install hamlib
```

#### Windows

```bash
winget install hamlib
```

#### Weryfikacja instalacji

```bash
rotctl --version
# Powinno wyświetlić: rotctl(d) Hamlib 4.x
```

### Instalacja pakietów Python

**1. Środowisko wirtualne (zalecane):**

```bash
# Utwórz środowisko wirtualne
python3 -m venv venv

# Aktywuj (Linux/macOS)
source venv/bin/activate

# Aktywuj (Windows)
venv\Scripts\activate
```

**2. Instalacja zależności:**

```bash
# Podstawowe zależności
pip install -r requirements.txt

# Weryfikacja instalacji
python -c "import serial, ephem, fastapi; print('Wszystkie pakiety zainstalowane')"
```

### Konfiguracja sprzętu SPID

**1. Podłącz kontroler SPID:**

- Użyj kabla USB lub RS232 → USB adapter  
- Upewnij się, że kontroler jest zasilony

**2. Sprawdź dostępne porty:**

```bash
python -c "
import serial.tools.list_ports
ports = [p.device for p in serial.tools.list_ports.comports()]
print('Dostępne porty:', ports)
"
```

**3. Test komunikacji z rotctl:**

```bash
# Test podstawowej komunikacji (zmień port na właściwy)
rotctl -m 903 -r /dev/tty.usbserial-A10PDNT7 -s 115200 p
```

**Uwagi:**

- Model 903 = SPID MD-01/02/03 ROT2 mode
- Standardowa prędkość: 115200 bps
- Linux: może wymagać uprawnień: `sudo usermod -a -G dialout $USER`

---

## API REST Server

### Szybki start

**Linux/macOS:**

```bash
# 1. Aktywuj środowisko wirtualne
source venv/bin/activate

# 2. Uruchom serwer API
cd api_server
python start_server.py

# Lub bezpośrednio:
python main.py
```

**Windows:**

```bash
# 1. Aktywuj środowisko wirtualne
venv\Scripts\activate

# 2. Uruchom serwer API
cd api_server
python start_server.py

# Lub bezpośrednio:
python main.py
```

### Dostęp do interfejsów

| Interfejs | URL | Opis |
|-----------|-----|------|
| **Interfejs webowy** | `http://localhost:8000/web_interface.html` | Główny panel sterowania |
| **Dokumentacja API** | `http://localhost:8000/docs` | Swagger UI dokumentacja |
| **API Endpoint** | `http://localhost:8000/api/` | REST API base URL |
| **Health check** | `http://localhost:8000/health` | Status serwera |

### Funkcjonalności interfejsu webowego

- **Połączenie z silnikiem anteny** (sprzęt/symulator)
- **Sterowanie pozycją** silnika anteny (azymut/elewacja)
- **Monitorowanie statusu** w czasie rzeczywistym
- **Konfiguracja lokalizacji** obserwatora (współrzędne geograficzne)
- **Śledzenie obiektów** astronomicznych
- **System logów** z auto-scroll
- **Awaryjne zatrzymanie** (SPACJA lub przycisk)

### Główne endpoints API

| HTTP Method | Endpoint | Opis |
|-------------|----------|------|
| `POST` | `/api/connect` | Połącz z kontrolerem silnika anteny |
| `POST` | `/api/disconnect` | Rozłącz kontroler |
| `GET` | `/api/status` | Pobierz aktualny status |
| `POST` | `/api/move` | Ustaw pozycję silnika anteny |
| `POST` | `/api/stop` | Zatrzymaj ruch anteny |
| `GET` | `/api/position` | Pobierz aktualną pozycję |
| `POST` | `/api/calibration` | Zarządzaj kalibracją |
| `POST` | `/api/track` | Śledź obiekt astronomiczny |

---

## Użycie biblioteki Python

### Podstawowy przykład

```python
from antenna_controller import AntennaController
from astronomic_calculator import AstronomicalCalculator
import ephem

# 1. Inicjalizacja kontrolera
controller = AntennaController()

# 2. Połączenie z silnikiem anteny (sprzęt)
success = controller.connect("/dev/tty.usbserial-A10PDNT7")
if success:
    print("Połączono z kontrolerem SPID")
else:
    print("Błąd połączenia - użyj symulatora")
    controller.connect("simulator")

# 3. Podstawowe sterowanie
controller.move_to_position(180.0, 45.0)  # Azymut 180°, Elewacja 45°
print(f"Pozycja: {controller.get_current_position()}")

# 4. Śledzenie obiektu astronomicznego
calculator = AstronomicalCalculator()
calculator.set_observer_location(50.0614, 19.9365, 220)  # Kraków

# Oblicz pozycję Słońca
sun_az, sun_el = calculator.calculate_sun_position()
if sun_el > 0:  # Słońce nad horyzontem
    controller.move_to_position(sun_az, sun_el)
    print(f"Śledzi Słońce: {sun_az:.1f}°, {sun_el:.1f}°")

# 5. Rozłączenie systemu
controller.disconnect()
```

---

## Podstawowe użycie

### Inicjalizacja kontrolera

```python
from antenna_controller import AntennaController

# Utwórz kontroler anteny
controller = AntennaController()
```

### Połączenie ze sprzętem

```python
# Połączenie z fizycznym kontrolerem SPID
success = controller.connect("/dev/tty.usbserial-A10PDNT7")

# Lub użyj symulatora do testów
controller.connect("simulator")
```

### Podstawowe sterowanie

```python
# Przesuń antenę do określonej pozycji
controller.move_to_position(azimuth=180.0, elevation=45.0)

# Sprawdź aktualną pozycję
position = controller.get_current_position()
print(f"Azymut: {position.azimuth}°, Elewacja: {position.elevation}°")

# Zatrzymaj ruch anteny
controller.stop()
```

### Zaawansowane funkcje

```python
from antenna_controller import AntennaController, PositionCalibration

# Kalibracja silnika anteny
calibration = PositionCalibration(
    azimuth_offset=2.5,    # Korekta azymutu o +2.5°
    elevation_offset=-1.2   # Korekta elewacji o -1.2°
)

controller = AntennaController(calibration=calibration)
controller.connect("/dev/tty.usbserial-A10PDNT7")

# Płynne sterowanie z progiem tolerancji
controller.move_to_position(
    azimuth=270.0, 
    elevation=30.0,
    tolerance=0.5  # Zatrzymaj w promieniu 0.5°
)

# Monitoring w czasie rzeczywistym
import time
for i in range(10):
    pos = controller.get_current_position()
    status = controller.get_status()
    print(f"Pozycja: {pos}, Status: {status}")
    time.sleep(1)
```

---

## Zarządzanie kalibracją

### Kalibracja pozycji północy

```python
from antenna_controller import AntennaController

controller = AntennaController()
controller.connect("/dev/tty.usbserial-A10PDNT7")

# Kalibruj pozycję północy (0° azymut)
controller.calibrate_north()
```

### Ustawienia offsetu

```python
from antenna_controller import PositionCalibration

# Definicja kalibracji z offsetami
calibration = PositionCalibration(
    azimuth_offset=2.5,     # Korekta azymutu +2.5°
    elevation_offset=-1.0   # Korekta elewacji -1.0°
)

# Zastosuj kalibrację
controller = AntennaController(calibration=calibration)
```

### Zarządzanie plikami kalibracji

```python
# Zapisz kalibrację do pliku JSON
controller.save_calibration("calibrations/antenna_calibration.json")

# Wczytaj kalibrację z pliku
controller.load_calibration("calibrations/antenna_calibration.json")
```

---

## System bezpieczeństwa

### Limity mechaniczne

System automatycznie sprawdza limity mechaniczne anteny przed każdym ruchem:

```python
from antenna_controller import AntennaLimits

# Definicja limitów anteny
limits = AntennaLimits(
    min_azimuth=0.0,      # Minimalny azymut
    max_azimuth=360.0,    # Maksymalny azymut  
    min_elevation=0.0,    # Minimalna elewacja
    max_elevation=90.0    # Maksymalna elewacja
)

controller = AntennaController(limits=limits)
```

### Awaryjne zatrzymanie

```python
# Natychmiastowe zatrzymanie anteny
controller.emergency_stop()

# Sprawdzenie stanu awaryjnego
if controller.is_emergency_stop_active():
    print("Antenowa w stanie awaryjnym!")
    
# Reset stanu awaryjnego
controller.reset_emergency_stop()
```

### Monitoring bezpieczeństwa

```python
# Sprawdź status bezpieczeństwa
safety_status = controller.get_safety_status()
print(f"Status: {safety_status}")

# Sprawdź czy pozycja jest bezpieczna
is_safe = controller.is_position_safe(azimuth=180.0, elevation=45.0)
if not is_safe:
    print("Pozycja poza limitami bezpieczeństwa!")
```

---

## Testy i jakość kodu

### Uruchamianie testów

```bash
# Wszystkie testy
python -m pytest tests/ -v

# Konkretne testy
python -m pytest tests/tests.py -v
python -m pytest tests/test_spid_protocol.py -v

# Test z pokryciem
python -m pytest tests/ --cov=. --cov-report=html
```

---

## Przykłady użycia

### Przykład 1: Basic Usage

```python
# examples/basic_usage.py
from antenna_controller import AntennaController

# Podstawowe sterowanie silnikiem anteny
controller = AntennaController()
controller.connect("simulator")  # lub port USB
controller.move_to_position(180.0, 45.0)
print(f"Pozycja: {controller.get_current_position()}")
```

### Przykład 2: Advanced Usage

```python
# examples/advanced_usage.py
from antenna_controller import AntennaController, PositionCalibration
from astronomic_calculator import AstronomicalCalculator
import time

# Zaawansowane funkcje z kalibracją i śledzeniem Słońca

# Ustawienie kalibracji pozycji
calibration = PositionCalibration(
    azimuth_offset=2.0,    # Korekta azymutu
    elevation_offset=-1.0  # Korekta elewacji
)

# Inicjalizacja kontrolera z kalibracją
controller = AntennaController(calibration=calibration)
controller.connect("/dev/tty.usbserial-A10PDNT7")  # lub "simulator"

# Śledzenie pozycji Słońca
calculator = AstronomicalCalculator()
calculator.set_observer_location(52.40030228321106, 16.955077591791788, 75)  # Poznań

sun_az, sun_el = calculator.calculate_sun_position()
if sun_el > 0:
    controller.move_to_position(sun_az, sun_el, tolerance=0.5)
    print(f"Śledzenie Słońca: {sun_az:.1f}°, {sun_el:.1f}°")

# Monitoring statusu przez 5 sekund
for _ in range(5):
    pos = controller.get_current_position()
    status = controller.get_status()
    print(f"Pozycja: {pos}, Status: {status}")
    time.sleep(1)

controller.disconnect()
```

---

## Protokol SPID i rotctl

System obsługuje natywnie protokół **SPID MD-01/02/03** przez **rotctl (Hamlib)**:

### Komendy rotctl

| Komenda rotctl | Opis | Przykład użycia |
|----------------|------|-----------------|
| `rotctl -m 903 -r PORT p` | Pobiera aktualną pozycję | `180.0 45.0` |
| `rotctl -m 903 -r PORT P 180 45` | Ustawia pozycję | Az = 180°, El = 45° |
| `rotctl -m 903 -r PORT S` | Zatrzymuje ruch | Awaryjny stop |
| `rotctl -m 903 -r PORT --version` | Wersja hamlib | Sprawdź połączenie |

### Konfiguracja komunikacji

- **Model rotctl:** 903 (SPID MD-01/02/03 ROT2)
- **Prędkość:** 115200 bps (`-s 115200`)
- **Port:** `/dev/tty.usbserial-XXX` (`-r PORT`)
- **Format:** 8N1 (8 bitów danych, brak parzystości, 1 bit stop)
- **Kontrola przepływu:** Brak

### Przykład pełnej komendy rotctl

```bash
# Pobierz pozycję
rotctl -m 903 -r /dev/tty.usbserial-A10PDNT7 -s 115200 p

# Ustaw pozycję na azymut 180°, elewacja 45°
rotctl -m 903 -r /dev/tty.usbserial-A10PDNT7 -s 115200 P 180 45

# Zatrzymaj ruch
rotctl -m 903 -r /dev/tty.usbserial-A10PDNT7 -s 115200 S
```

### System współrzędnych SPID

- **Azymut:** 0-360° (0° = północ, 90° = wschód)
- **Elewacja:** 0-90° (0° = zenit, 90° = horyzont)
- **Konwersja:** Automatyczna przez `AstronomicalCalculator`

---

## Kalkulator astronomiczny

### Obsługiwane obiekty

| Kategoria | Obiekty | Sposób użycia |
|-----------|---------|---------------|
| **Słońce** | Sun | `AstronomicalObjectType.SUN` |
| **Księżyc** | Moon | `AstronomicalObjectType.MOON` |
| **Planety** | Mercury, Venus, Mars, Jupiter, Saturn, Uranus, Neptune | `AstronomicalObjectType.MARS`, itp. |
| **Gwiazdy** | Katalog PyEphem (Sirius, Vega, Arcturus, Capella, itp.) | `AstronomicalObjectType.STAR` + nazwa |
| **Obiekt własny** | Współrzędne RA/Dec | `AstronomicalObjectType.CUSTOM` + współrzędne |

### Przykład użycia

```python
from astronomic_calculator import AstronomicalCalculator, ObserverLocation, AstronomicalObjectType
from datetime import datetime, timezone

# Konfiguracja obserwatora (Poznań)
observer_location = ObserverLocation(52.40030228321106, 16.955077591791788, 75, "Poznań")
calc = AstronomicalCalculator(observer_location)

# Pozycja Słońca
sun_position = calc.get_position(AstronomicalObjectType.SUN)
print(f"Słońce: {sun_position.azimuth:.1f}°, {sun_position.elevation:.1f}°")
if sun_position.is_visible:
    antenna_pos = sun_position.to_antenna_position()
    print(f"Pozycja SPID: Az={antenna_pos.azimuth:.1f}°, El={antenna_pos.elevation:.1f}°")

# Pozycja Księżyca  
moon_position = calc.get_position(AstronomicalObjectType.MOON)
print(f"Księżyc: {moon_position.azimuth:.1f}°, {moon_position.elevation:.1f}°")

# Pozycja planety Mars
mars_position = calc.get_position(AstronomicalObjectType.MARS)
print(f"Mars: {mars_position.azimuth:.1f}°, {mars_position.elevation:.1f}°")

# Pozycja gwiazdy Sirius
sirius_position = calc.get_position(AstronomicalObjectType.STAR, object_name="Sirius")
print(f"Sirius: {sirius_position.azimuth:.1f}°, {sirius_position.elevation:.1f}°")

# Czasy wschodu/zachodu Słońca
sun_times = calc.calculate_rise_set_times(AstronomicalObjectType.SUN)
print(f"Wschód Słońca: {sun_times.get('next_rising')}")
print(f"Zachód Słońca: {sun_times.get('next_setting')}")
```

---

## Rozwiazywanie problemow

### Częste problemy

#### Problem: "rotctl: command not found"

```bash
# Sprawdź, czy rotctl jest zainstalowany
which rotctl

# Jeśli nie - zainstaluj Hamlib
# macOS:
brew install hamlib

# Linux (Ubuntu/Debian):
sudo apt-get update && sudo apt-get install hamlib-utils

# Windows:
winget install hamlib
```

#### Problem: "Permission denied" na porcie USB

**Linux (Ubuntu/Debian/CentOS/RHEL/Fedora):**

```bash
# Dodaj użytkownika do grupy dialout
sudo usermod -a -G dialout $USER
# Alternatywnie dla niektórych dystrybucji:
sudo usermod -a -G uucp $USER

# Wyloguj się i zaloguj ponownie lub uruchom:
newgrp dialout

# Sprawdź uprawnienia portu
ls -la /dev/ttyUSB* /dev/ttyACM*
```

**macOS:**

```bash
# Sprawdź uprawnienia portu
ls -la /dev/tty.usbserial*

# Jeśli problem nadal występuje, sprawdź sterowniki USB
system_profiler SPUSBDataType | grep -A 10 "Serial"

# Restart usługi USB (jeśli konieczne)
sudo kextunload -b com.apple.driver.AppleUSBFTDI
sudo kextload -b com.apple.driver.AppleUSBFTDI
```

**Windows:**

```bash
# Sprawdź dostępne porty COM w Device Manager
# Lub w PowerShell:
Get-WmiObject Win32_SerialPort | Select-Object Name,DeviceID

# Uruchom jako Administrator jeśli problem z uprawnieniami
# Sprawdź sterowniki USB w Device Manager

# Alternatywnie w Command Prompt:
mode
```

#### Problem: "No response from controller"

1. **Sprawdź połączenia:**
   - Kabel USB poprawnie podłączony
   - Kontroler SPID zasilony
   - Prawidłowy port w konfiguracji

2. **Test komunikacji:**

   ```bash
   # Test bezpośredni z rotctl
   rotctl -m 903 -r /dev/tty.usbserial-YOUR_PORT -s 115200 p
   ```

3. **Sprawdź model SPID:**
   - MD-01: model 903
   - MD-02: model 903  
   - MD-03: model 903

#### Problem: API serwer nie startuje

```bash
# Sprawdź port 8000
netstat -an | grep 8000

# Uruchom na innym porcie
export PORT=8080
python api_server/main.py
```

### Diagnostyka

```bash
# Test wszystkich komponentów
python -c "
import serial.tools.list_ports
import subprocess
import sys

print('Diagnostyka systemu radioteleskop')
print('='*50)

# 1. Porty szeregowe
print('Dostępne porty szeregowe:')
ports = list(serial.tools.list_ports.comports())
for port in ports:
    print(f'  - {port.device}: {port.description}')

# 2. rotctl
try:
    result = subprocess.run(['rotctl', '--version'], capture_output=True, text=True)
    print(f'rotctl: {result.stdout.strip().split()[1]}')
except FileNotFoundError:
    print('rotctl: nie znaleziono - zainstaluj Hamlib')

# 3. Python packages
try:
    import serial, ephem, fastapi
    print('Python packages: wszystkie zainstalowane')
except ImportError as e:
    print(f'Python packages: brakuje {e.name}')

print('='*50)
"
```

---

## Podziękowania

**Autor:** Aleks Czarnecki
**Licencja:** MIT License
**Wersja:** 1.32 (2025)

### Wykorzystane biblioteki

- **[PyEphem](https://pyephem.readthedocs.io/)** — obliczenia astronomiczne
- **[FastAPI](https://fastapi.tiangolo.com/)** — nowoczesny web framework
- **[PySerial](https://pyserial.readthedocs.io/)** — komunikacja szeregowa
- **[Hamlib](https://hamlib.github.io/)** — protokoły kontrolerów silników anten
