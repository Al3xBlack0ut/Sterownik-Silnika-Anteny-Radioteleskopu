"""
Test minimalny protokołu SPID
=============================

Prosty test komunikacji z rotatorami SPID za pomocą rotctl (Hamlib).
Testuje podstawowe funkcje: odczyt pozycji i ustawienie pozycji.

Autor: Aleks Czarnecki
"""

import subprocess
import sys
import time
import os

# Dodaj ścieżkę do głównego folderu projektu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import DEFAULT_SPID_PORT, DEFAULT_BAUDRATE, DEFAULT_ROTCTL_MODEL

def ustaw_pozycje(port: str, az: float, el: float, speed: int = DEFAULT_BAUDRATE):
    """Ustawia pozycję rotatora SPID MD-03 za pomocą rotctl (Hamlib)"""
    komenda = f"P {az % 360:.1f} {el:.1f}\n"
    
    proc = subprocess.Popen(
        ['rotctl', '-m', DEFAULT_ROTCTL_MODEL, '-r', port, '-s', str(speed), '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    _, stderr = proc.communicate(input=komenda)
    
    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl: {stderr.strip()}")

def odczytaj_pozycje(port: str, speed: int = DEFAULT_BAUDRATE):
    """Odczytuje aktualną pozycję rotatora za pomocą rotctl."""
    # Używamy komendy p (get_pos) do odczytu pozycji
    proc = subprocess.Popen(
        ['rotctl', '-m', DEFAULT_ROTCTL_MODEL, '-r', port, '-s', str(speed), '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    stdout, stderr = proc.communicate(input="p\n")
    
    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl: {stderr.strip()}")
    
    return stdout.strip()

if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv)>1 else DEFAULT_SPID_PORT
    print("Pozycja startowa:")
    print(odczytaj_pozycje(port))
    ustaw_pozycje(port, az=125, el=60)
    
    # Czekaj na osiągnięcie pozycji zamiast stałego czekania
    target_az, target_el = 125.0, 60.0
    start_time = time.time()
    timeout = 30.0  # 30 sekund timeout
    
    while time.time() - start_time < timeout:
        try:
            current_az, current_el = odczytaj_pozycje(port)
            
            # Sprawdź czy osiągnięto pozycję z tolerancją 2°
            az_diff = abs(current_az - target_az)
            if az_diff > 180:
                az_diff = 360 - az_diff
            el_diff = abs(current_el - target_el)
            
            if az_diff <= 2.0 and el_diff <= 2.0:
                print(f"Pozycja osiągnięta w {time.time() - start_time:.1f}s")
                break
                
            time.sleep(0.5)  # Sprawdzaj co 0.5s
        except Exception as e:
            print(f"Błąd podczas sprawdzania pozycji: {e}")
            time.sleep(0.5)
    else:
        print(f"Timeout po {timeout}s")
    
    print("Ustawiono. Teraz odczytuję pozycję:")
    print(odczytaj_pozycje(port))
