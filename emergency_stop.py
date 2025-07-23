"""
Awaryjny STOP dla Sterownika Anteny Radioteleskopu
Protokół komunikacji: SPID

Ten skrypt można uruchomić w każdej chwili, aby natychmiast zatrzymać ruch anteny.
Można go uruchamiać niezależnie od głównego programu sterującego.

Autor: Aleks Czarnecki
"""

import serial
import time
import sys
import argparse
from typing import Optional

# Domyślny port szeregowy dla kontrolera SPID
DEFAULT_PORT = "/dev/tty.usbserial-A10PDNT7"


def decode_spid_response(response: bytes) -> dict:
    """Dekoduje odpowiedź z kontrolera SPID"""
    if len(response) < 12:
        return {'error': f'Niepełna odpowiedź: {len(response)} bajtów', 'raw_hex': response.hex().upper()}

    try:
        result = {
            'raw_hex': response.hex().upper(),
            'start_byte': f'0x{response[0]:02X}',
            'azimuth_data': response[1:5].decode('ascii', errors='ignore'),
            'separator1': f'0x{response[5]:02X}',
            'elevation_data': response[6:10].decode('ascii', errors='ignore'),
            'separator2': f'0x{response[10]:02X}',
            'command_byte': f'0x{response[10]:02X}',
            'end_byte': f'0x{response[11]:02X}'
        }

        # Interpretacja bajtów komend
        command_descriptions = {
            0x0F: "STOP Command Response",
            0x1F: "STATUS Query Response",
            0x2F: "MOVE Command Response",
            0x00: "Separator"
        }

        result['command_description'] = command_descriptions.get(response[10], f"Unknown command: 0x{response[10]:02X}")

        # Dekodowanie pozycji, jeśli możliwe
        try:
            if result['azimuth_data'].isdigit() and result['elevation_data'].isdigit():
                result['azimuth_degrees'] = float(result['azimuth_data']) / 10.0
                result['elevation_degrees'] = float(result['elevation_data']) / 10.0
        except (ValueError, AttributeError):
            pass

        return result

    except Exception as e:
        return {'error': f'Błąd dekodowania: {e}', 'raw_hex': response.hex().upper()}


def send_emergency_stop(port: str, verbose: bool = True) -> bool:
    """ Wysyła awaryjną komendę STOP do kontrolera SPID """
    try:
        # Nawiąż połączenie z kontrolerem SPID
        if verbose:
            print(f"Łączenie z kontrolerem SPID na porcie: {port}")

        ser = serial.Serial(
            port=port,
            baudrate=115200,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=2
        )

        # Wyczyść bufory
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # Komenda STOP zgodnie z protokołem SPID
        # Struktura: START(0x57) + 10x NULL + STOP_CMD(0x0F) + END(0x20)
        stop_cmd = b'\x57' + b'\x00' * 10 + b'\x0F' + b'\x20'

        if verbose:
            print(f"Wysyłanie komendy EMERGENCY STOP: {stop_cmd.hex().upper()}")

        # Wyślij komendę STOP
        ser.write(stop_cmd)
        time.sleep(0.1)

        # Odbierz odpowiedź
        response = ser.read(12)

        if verbose:
            print(f"Otrzymana odpowiedź ({len(response)} bajtów): {response.hex().upper()}")

        # Dekoduj odpowiedź
        decoded = decode_spid_response(response)

        if verbose:
            print("Analiza odpowiedzi:")
            for key, value in decoded.items():
                print(f"   {key}: {value}")

        # Sprawdź, czy odpowiedź wskazuje na pomyślne wykonanie STOP
        success = len(response) >= 12 and response[0] == 0x57

        if success:
            if verbose:
                print("AWARYJNY STOP wykonany pomyślnie!")
                if 'azimuth_degrees' in decoded and 'elevation_degrees' in decoded:
                    print(f"Pozycja po zatrzymaniu: Az={decoded['azimuth_degrees']:.1f}°, El={decoded['elevation_degrees']:.1f}°")
        else:
            if verbose:
                print("Błąd podczas wykonywania STOP!")

        ser.close()
        return success

    except serial.SerialException as e:
        if verbose:
            print(f"Błąd połączenia szeregowego: {e}")
            print(f"Sprawdź czy port {port} jest poprawny i dostępny")
        return False

    except Exception as e:
        if verbose:
            print(f"Nieoczekiwany błąd: {e}")
        return False


def get_antenna_status(port: str, verbose: bool = True) -> Optional[dict]:
    """
    Pobiera aktualny status anteny z kontrolera SPID
    """
    try:
        if verbose:
            print(f"Łączenie z kontrolerem SPID na porcie: {port}")

        ser = serial.Serial(
            port=port,
            baudrate=115200,
            bytesize=8,
            parity='N',
            stopbits=1,
            timeout=2
        )

        # Wyczyść bufory
        ser.reset_input_buffer()
        ser.reset_output_buffer()

        # Komenda STATUS zgodnie z protokołem SPID
        status_cmd = b'\x57' + b'\x00' * 10 + b'\x1F' + b'\x20'

        if verbose:
            print(f"Wysyłanie zapytania o STATUS: {status_cmd.hex().upper()}")

        ser.write(status_cmd)
        time.sleep(0.1)

        response = ser.read(12)

        if verbose:
            print(f"Otrzymana odpowiedź ({len(response)} bajtów): {response.hex().upper()}")

        decoded = decode_spid_response(response)

        if verbose:
            print("Status anteny:")
            for key, value in decoded.items():
                print(f"   {key}: {value}")

        ser.close()
        return decoded

    except Exception as e:
        if verbose:
            print(f"Błąd podczas pobierania statusu: {e}")
        return None


def main():
    """Główna funkcja programu"""
    parser = argparse.ArgumentParser(
        description="Awaryjny STOP dla Sterownika Anteny Radioteleskopu (protokół SPID)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Przykłady użycia:
  python emergency_stop.py                    # Awaryjny STOP z domyślnym portem
  python emergency_stop.py --port COM10       # STOP z określonym portem
  python emergency_stop.py --status           # Sprawdź tylko status anteny
  python emergency_stop.py --quiet            # Tryb cichy (minimal output)
  
Domyślny port: """ + DEFAULT_PORT
    )

    parser.add_argument(
        "--port", "-p",
        default=DEFAULT_PORT,
        help=f"Port szeregowy kontrolera SPID (domyślnie: {DEFAULT_PORT})"
    )

    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Sprawdź tylko status anteny (bez wysyłania STOP)"
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Tryb cichy - wyświetl tylko najważniejsze informacje"
    )

    args = parser.parse_args()

    if not args.quiet:
        print("AWARYJNY STOP ANTENY RADIOTELESKOPU")
        print("=" * 50)
        print(f"Port: {args.port}")
        print("Protokół: SPID")
        print("=" * 50)

    try:
        if args.status:
            # Tylko sprawdź status
            status = get_antenna_status(args.port, verbose=not args.quiet)
            if status and 'azimuth_degrees' in status and 'elevation_degrees' in status:
                print(f"\nAktualna pozycja: Az={status['azimuth_degrees']:.1f}°, El={status['elevation_degrees']:.1f}°")
                sys.exit(0)
            else:
                print("\nNie udało się pobrać statusu anteny")
                sys.exit(1)
        else:
            # Wykonaj awaryjny STOP
            success = send_emergency_stop(args.port, verbose=not args.quiet)

            if success:
                if args.quiet:
                    print("STOP OK")
                sys.exit(0)
            else:
                if args.quiet:
                    print("STOP FAILED")
                sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nPrzerwano przez użytkownika")
        sys.exit(130)
    except Exception as e:
        print(f"\nKrytyczny błąd: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
