import subprocess
import sys
import time

def ustaw_pozycje(port: str, az: float, el: float, speed: int = 115200):
    """Ustawia pozycję rotatora SPID MD-03 za pomocą rotctl (Hamlib)"""
    komenda = f"P {az % 360:.1f} {el:.1f}\n"
    
    proc = subprocess.Popen(
        ['rotctl', '-m', '903', '-r', port, '-s', str(speed), '-'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    _, stderr = proc.communicate(input=komenda)
    
    if proc.returncode != 0:
        raise RuntimeError(f"Błąd rotctl: {stderr.strip()}")

def odczytaj_pozycje(port: str, speed: int = 115200):
    # Używamy komendy p (get_pos) do odczytu pozycji
    proc = subprocess.Popen(
        ['rotctl', '-m', '903', '-r', port, '-s', str(speed), '-'],
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
    port = sys.argv[1] if len(sys.argv)>1 else '/dev/tty.usbserial-A10PDNT7'
    print("Pozycja startowa:")
    print(odczytaj_pozycje(port))
    ustaw_pozycje(port, az=274-180, el=30)
    time.sleep(20)
    print("Ustawiono. Teraz odczytuję pozycję:")
    print(odczytaj_pozycje(port))

