"""
Test protokołu SPID dla Sterownika Anteny Radioteleskopu
Protokół komunikacji: SPID

Narzędzie diagnostyczne do testowania komunikacji z kontrolerem SPID.
Zawiera funkcje testowe dla komend MOVE, STATUS i STOP.
Przydatne do weryfikacji połączenia i debugowania problemów komunikacyjnych.

Autor: Aleks Czarnecki
"""

import serial
import time

port = "/dev/tty.usbserial-A10PDNT7"

def wyslij_komende_set():
    ser = serial.Serial(port, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=1)

    az = 20
    el = 80
    az_str = f"{az:04d}"  # formatowanie do 4 cyfr
    el_str = f"{el:04d}"

    cmd = (
            b'\x57' +
            az_str.encode() +
            b'\x00' +
            el_str.encode() +
            b'\x00' +
            b'\x2F' +
            b'\x20'
    )

    print(f"Wysyłanie komendy MOVE: {cmd.hex().upper()}")
    ser.write(cmd)
    time.sleep(0.1)
    resp = ser.read(12)  # oczekiwana odpowiedź 12-bajtowa
    print("Odpowiedź:", resp.hex().upper())

    ser.close()


def wyslij_komende_stop():
    ser = serial.Serial(port, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=1)

    cmd = b'\x57' + b'\x00' * 10 + b'\x0F' + b'\x20'

    print(f"Wysyłanie komendy STOP: {cmd.hex().upper()}")
    ser.write(cmd)
    time.sleep(0.1)
    resp = ser.read(12)
    print("Odpowiedź:", resp.hex().upper())

    ser.close()


def wyslij_komende_status():
    ser = serial.Serial(port, baudrate=115200, bytesize=8, parity='N', stopbits=1, timeout=1)

    cmd = b'\x57' + b'\x00' * 10 + b'\x1F' + b'\x20'

    print(f"Wysyłanie komendy STATUS: {cmd.hex().upper()}")
    ser.write(cmd)
    time.sleep(0.1)
    resp = ser.read(12)
    print("Odpowiedź:", resp.hex().upper())

    ser.close()


if __name__ == "__main__":
    try:
        print("=== Test protokołu SPID ===")
        print("\n1. Test komendy MOVE (Az=20°, El=80°):")
        wyslij_komende_set()

        print("\n2. Test komendy STATUS:")
        wyslij_komende_status()

        print("\n3. Test komendy STOP:")
        wyslij_komende_stop()

        print("\nWszystkie testy zakończone")

    except Exception as e:
        print(f"Błąd: {e}")
