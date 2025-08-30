#!/usr/bin/env python3
"""
Emergency Stop dla rotatorów SPID za pomocą rotctl (Hamlib)

Używa rotctl do natychmiastowego zatrzymania ruchu anteny.
Model 903 dla SPID MD-03 ROT2 mode.

Autor: Aleks Czarnecki
"""

import sys
import logging
from antenna_controller import (
    DEFAULT_SPID_PORT, DEFAULT_BAUDRATE, sprawdz_rotctl, rotctl_zatrzymaj_rotor
)

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def emergency_stop(port: str = DEFAULT_SPID_PORT, speed: int = DEFAULT_BAUDRATE) -> bool:
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
        
        # Użyj funkcji z antenna_controller
        result = rotctl_zatrzymaj_rotor(port, speed)
        
        if "OK" in result or "STOP" in result:
            logger.info(f"ZATRZYMANO! Odpowiedź: {result.strip()}")
            return True
        else:
            logger.error(f"Błąd podczas zatrzymania: {result.strip()}")
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
