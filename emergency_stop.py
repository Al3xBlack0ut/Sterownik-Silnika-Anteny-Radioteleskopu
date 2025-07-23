#!/usr/bin/env python3
"""
Emergency Stop dla rotatorów SPID za pomocą rotctl (Hamlib)

Używa rotctl do natychmiastowego zatrzymania ruchu anteny.
Model 903 dla SPID MD-03 ROT2 mode.

Autor: Aleks Czarnecki
"""

import subprocess
import sys
import logging

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Model SPID dla rotctl (903 = SPID MD-03 ROT2 mode)
ROTCTL_SPID_MODEL = '903'

# Domyślny port szeregowy dla kontrolera SPID
DEFAULT_SPID_PORT = "/dev/tty.usbserial-A10PDNT7"


def sprawdz_rotctl() -> bool:
    """Sprawdza czy rotctl jest dostępne w systemie."""
    try:
        result = subprocess.run(['rotctl', '--version'], 
                              capture_output=True, text=True, timeout=5, check=False)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def emergency_stop(port: str = DEFAULT_SPID_PORT, speed: int = 115200) -> bool:
    """
    Awaryjne zatrzymanie rotatora SPID za pomocą rotctl.
    
    Args:
        port: Port szeregowy kontrolera SPID
        speed: Prędkość portu szeregowego
        
    Returns:
        True jeśli zatrzymanie się powiodło, False w przeciwnym razie
    """
    if not sprawdz_rotctl():
        logger.error("rotctl (Hamlib) nie jest dostępne w systemie")
        return False
    
    try:
        logger.info(f"AWARYJNE ZATRZYMANIE - wysyłanie komendy STOP do portu {port}")
        
        proc = subprocess.Popen(
            ['rotctl', '-m', ROTCTL_SPID_MODEL, '-r', port, '-s', str(speed), '-'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = proc.communicate(input="S\n", timeout=10)
        
        if proc.returncode != 0:
            logger.error(f"Błąd rotctl STOP: {stderr.strip()}")
            return False
            
        logger.info(f"ZATRZYMANO! Odpowiedź: {stdout.strip()}")
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("Timeout podczas awaryjnego zatrzymania")
        proc.kill()
        return False
    except Exception as e:
        logger.error(f"Błąd podczas awaryjnego zatrzymania: {e}")
        return False


def main():
    """Główna funkcja - wykonuje awaryjne zatrzymanie."""
    print("=== AWARYJNE ZATRZYMANIE ROTATORA SPID ===")
    print("Używa rotctl (Hamlib) z modelem 903 dla SPID MD-01/02")
    print()
    
    # Sprawdź argumenty
    port = DEFAULT_SPID_PORT
    if len(sys.argv) > 1:
        port = sys.argv[1]
        print(f"Używam podanego portu: {port}")
    else:
        print(f"Używam domyślnego portu: {port}")
    
    print("Wysyłanie komendy STOP...")
    
    # Wykonaj awaryjne zatrzymanie
    success = emergency_stop(port)
    
    if success:
        print("ZATRZYMANIE WYKONANE POMYŚLNIE")
        sys.exit(0)
    else:
        print("BŁĄD PODCZAS ZATRZYMANIA")
        sys.exit(1)


if __name__ == "__main__":
    main()