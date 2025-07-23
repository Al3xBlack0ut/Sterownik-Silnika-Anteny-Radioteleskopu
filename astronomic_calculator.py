"""
Kalkulator pozycji astronomicznych dla radioteleskopu
Obsługuje obliczanie pozycji Słońca, Księżyca, planet i gwiazd

Zaawansowany system astronomiczny wykorzystujący bibliotekę PyEphem do precyzyjnych obliczeń.
Zawiera klasy do śledzenia obiektów niebieskich, konwersji współrzędnych oraz predykcji ścieżek
ruchu dla celów obserwacyjnych i śledzenia automatycznego.

Autor: Aleks Czarnecki
"""

import math
import ephem
from datetime import datetime, timezone
from typing import Optional, Dict, Tuple
from dataclasses import dataclass
from enum import Enum

# Import z głównego modułu
from antenna_controller import Position


class AstronomicalObjectType(Enum):
    """Typy obiektów astronomicznych"""

    SUN = "sun"
    MOON = "moon"
    MERCURY = "mercury"
    VENUS = "venus"
    MARS = "mars"
    JUPITER = "jupiter"
    SATURN = "saturn"
    URANUS = "uranus"
    NEPTUNE = "neptune"
    STAR = "star"
    CUSTOM = "custom"


@dataclass
class ObserverLocation:
    """Lokalizacja obserwatora"""

    latitude: float  # Szerokość geograficzna w stopniach
    longitude: float  # Długość geograficzna w stopniach
    elevation: float  # Wysokość n.p.m. w metrach
    name: str = "Unknown"

    def __post_init__(self):
        """Walidacja współrzędnych"""
        if not (-90 <= self.latitude <= 90):
            raise ValueError("Szerokość geograficzna musi być w zakresie -90° do +90°")
        if not (-180 <= self.longitude <= 180):
            raise ValueError("Długość geograficzna musi być w zakresie -180° do +180°")


@dataclass
class AstronomicalPosition:
    """Pozycja astronomiczna obiektu"""

    azimuth: float  # Azymut w stopniach (0-360, 0 = północ)
    elevation: float  # Elewacja w stopniach (0 do +90)
    distance: float  # Odległość w AU (jednostki astronomiczne)
    ra: float  # Rektascensja w godzinach
    dec: float  # Deklinacja w stopniach
    is_visible: bool  # Czy obiekt jest nad horyzontem
    magnitude: float  # Jasność pozorna (jeśli dostępna)

    def to_antenna_position(self) -> Optional[Position]:
        """Konwertuje do pozycji anteny (tylko jeśli obiekt jest widoczny)"""
        if not self.is_visible or self.elevation < 0:
            return None

        # Konwersja azymutu z astronomicznego (0 = N) na techniczny (0 = E)
        antenna_azimuth = (90 - self.azimuth) % 360

        return Position(azimuth=antenna_azimuth, elevation=self.elevation)


class AstronomicalCalculator:
    """Kalkulator pozycji astronomicznych"""

    def __init__(self, observer_location: ObserverLocation):
        self.observer_location = observer_location
        self.observer = ephem.Observer()
        self._setup_observer()

        # Słownik obiektów astronomicznych
        # pylint: disable=no-member  # ephem objects exist at runtime
        self._objects = {
            AstronomicalObjectType.SUN: ephem.Sun(),
            AstronomicalObjectType.MOON: ephem.Moon(),
            AstronomicalObjectType.MERCURY: ephem.Mercury(),
            AstronomicalObjectType.VENUS: ephem.Venus(),
            AstronomicalObjectType.MARS: ephem.Mars(),
            AstronomicalObjectType.JUPITER: ephem.Jupiter(),
            AstronomicalObjectType.SATURN: ephem.Saturn(),
            AstronomicalObjectType.URANUS: ephem.Uranus(),
            AstronomicalObjectType.NEPTUNE: ephem.Neptune(),
        }

        # Cache dla gwiazd
        self._star_cache: Dict[str, object] = {}

    def _setup_observer(self):
        """Konfiguruje obserwatora"""
        self.observer.lat = math.radians(self.observer_location.latitude)
        self.observer.lon = math.radians(self.observer_location.longitude)
        self.observer.elev = self.observer_location.elevation
        self.observer.pressure = 1013.25  # Ciśnienie atmosferyczne w hPa
        self.observer.temp = 15.0  # Temperatura w °C

    def get_position(
        self,
        object_type: AstronomicalObjectType,
        object_name: Optional[str] = None,
        star_coordinates: Optional[Tuple[float, float]] = None,
        observation_time: Optional[datetime] = None,
    ) -> AstronomicalPosition:
        """
        Oblicza pozycję obiektu astronomicznego

        Args:
            object_type: Typ obiektu astronomicznego
            object_name: Nazwa obiektu (dla gwiazd)
            star_coordinates: Współrzędne gwiazdy (RA w godzinach, Dec w stopniach)
            observation_time: Czas obserwacji (domyślnie: teraz)

        Returns:
            Pozycja astronomiczna obiektu
        """
        if observation_time is None:
            observation_time = datetime.now(timezone.utc)

        # Ustawienie czasu obserwacji
        self.observer.date = observation_time.strftime("%Y/%m/%d %H:%M:%S")

        # Wybór obiektu
        if object_type == AstronomicalObjectType.STAR:
            if object_name:
                astronomical_object = self._get_star_by_name(object_name)
            elif star_coordinates:
                astronomical_object = self._create_star_from_coordinates(
                    star_coordinates[0], star_coordinates[1]
                )
            else:
                raise ValueError("Dla gwiazd wymagana jest nazwa lub współrzędne")

        elif object_type == AstronomicalObjectType.CUSTOM:
            if not star_coordinates:
                raise ValueError("Dla obiektu custom wymagane są współrzędne")
            astronomical_object = self._create_star_from_coordinates(
                star_coordinates[0], star_coordinates[1]
            )

        else:
            if object_type not in self._objects:
                raise ValueError(f"Nieobsługiwany typ obiektu: {object_type}")
            astronomical_object = self._objects[object_type]

        # Obliczenie pozycji
        astronomical_object.compute(self.observer)

        # Konwersja do stopni
        azimuth = math.degrees(astronomical_object.az)
        elevation = math.degrees(astronomical_object.alt)

        # Dodatkowe informacje
        distance = (
            astronomical_object.earth_distance
            if hasattr(astronomical_object, "earth_distance")
            else 0.0
        )
        ra = math.degrees(astronomical_object.ra) / 15.0  # Konwersja do godzin
        dec = math.degrees(astronomical_object.dec)

        # Jasność pozorna (jeśli dostępna)
        magnitude = (
            astronomical_object.mag if hasattr(astronomical_object, "mag") else 0.0
        )

        return AstronomicalPosition(
            azimuth=azimuth,
            elevation=elevation,
            distance=distance,
            ra=ra,
            dec=dec,
            is_visible=elevation > 0,
            magnitude=magnitude,
        )

    def _get_star_by_name(self, star_name: str) -> object:
        """Pobiera gwiazdę po nazwie z cache lub tworzy nową"""
        if star_name in self._star_cache:
            return self._star_cache[star_name]

        # Próba znalezienia gwiazdy w katalogu
        try:
            star = ephem.star(star_name)
            self._star_cache[star_name] = star
            return star
        except Exception:
            raise ValueError(f"Nie znaleziono gwiazdy: {star_name}")

    @staticmethod
    def _create_star_from_coordinates(ra_hours: float, dec_degrees: float) -> object:
        """Tworzy obiekt gwiazdy ze współrzędnych"""
        star = ephem.FixedBody()
        star._ra = ephem.hours(ra_hours)
        star._dec = ephem.degrees(dec_degrees)
        star._epoch = ephem.J2000
        return star

    def get_sun_position(
        self, observation_time: Optional[datetime] = None
    ) -> AstronomicalPosition:
        """Skrócona metoda dla pozycji Słońca"""
        return self.get_position(
            AstronomicalObjectType.SUN, observation_time=observation_time
        )

    def get_moon_position(
        self, observation_time: Optional[datetime] = None
    ) -> AstronomicalPosition:
        """Skrócona metoda dla pozycji Księżyca"""
        return self.get_position(
            AstronomicalObjectType.MOON, observation_time=observation_time
        )

    def get_planet_position(
        self,
        planet: AstronomicalObjectType,
        observation_time: Optional[datetime] = None,
    ) -> AstronomicalPosition:
        """Skrócona metoda dla pozycji planet"""
        if planet not in [
            AstronomicalObjectType.MERCURY,
            AstronomicalObjectType.VENUS,
            AstronomicalObjectType.MARS,
            AstronomicalObjectType.JUPITER,
            AstronomicalObjectType.SATURN,
            AstronomicalObjectType.URANUS,
            AstronomicalObjectType.NEPTUNE,
        ]:
            raise ValueError(f"Nieprawidłowy typ planety: {planet}")

        return self.get_position(planet, observation_time=observation_time)

    def get_star_position(
        self, star_name: str, observation_time: Optional[datetime] = None
    ) -> AstronomicalPosition:
        """Skrócona metoda dla pozycji gwiazdy"""
        return self.get_position(
            AstronomicalObjectType.STAR,
            object_name=star_name,
            observation_time=observation_time,
        )

    def get_custom_position(
        self,
        ra_hours: float,
        dec_degrees: float,
        observation_time: Optional[datetime] = None,
    ) -> AstronomicalPosition:
        """Skrócona metoda dla pozycji obiektu o podanych współrzędnych"""
        return self.get_position(
            AstronomicalObjectType.CUSTOM,
            star_coordinates=(ra_hours, dec_degrees),
            observation_time=observation_time,
        )

    def calculate_rise_set_times(
        self,
        object_type: AstronomicalObjectType,
        object_name: Optional[str] = None,
        star_coordinates: Optional[Tuple[float, float]] = None,
        date: Optional[datetime] = None,
    ) -> Dict[str, Optional[datetime]]:
        """
        Oblicza czasy wschodu i zachodu obiektu

        Returns:
            Dict z kluczami: 'rise', 'set', 'transit'
        """
        if date is None:
            date = datetime.now(timezone.utc)

        self.observer.date = date.strftime("%Y/%m/%d")

        # Wybór obiektu
        if object_type == AstronomicalObjectType.STAR:
            if object_name:
                astronomical_object = self._get_star_by_name(object_name)
            elif star_coordinates:
                astronomical_object = self._create_star_from_coordinates(
                    star_coordinates[0], star_coordinates[1]
                )
            else:
                raise ValueError("Dla gwiazd wymagana jest nazwa lub współrzędne")
        else:
            astronomical_object = self._objects[object_type]

        try:
            rise_time = self.observer.next_rising(astronomical_object)
            set_time = self.observer.next_setting(astronomical_object)
            transit_time = self.observer.next_transit(astronomical_object)

            return {
                "rise": ephem.localtime(rise_time),
                "set": ephem.localtime(set_time),
                "transit": ephem.localtime(transit_time),
            }
        except Exception:
            return {"rise": None, "set": None, "transit": None}

    def is_object_visible(
        self,
        object_type: AstronomicalObjectType,
        object_name: Optional[str] = None,
        star_coordinates: Optional[Tuple[float, float]] = None,
        min_elevation: float = 0.0,
        observation_time: Optional[datetime] = None,
    ) -> bool:
        """Sprawdza, czy obiekt jest widoczny (nad horyzontem)"""
        position = self.get_position(
            object_type, object_name, star_coordinates, observation_time
        )
        return position.elevation >= min_elevation


class AstronomicalTracker:
    """Klasa do śledzenia obiektów astronomicznych"""

    def __init__(self, calculator: AstronomicalCalculator):
        self.calculator = calculator
        self.tracking_active = False
        self.current_target = None
        self.tracking_precision = 0.1  # Stopnie

    def create_position_function(
        self,
        object_type: AstronomicalObjectType,
        object_name: Optional[str] = None,
        star_coordinates: Optional[Tuple[float, float]] = None,
        min_elevation: float = 10.0,
    ):
        """
        Tworzy funkcję pozycji do użycia z kontrolerem anteny
        """

        def get_position() -> Optional[Position]:
            try:
                # Pobierz aktualną pozycję astronomiczną
                ast_position = self.calculator.get_position(
                    object_type, object_name, star_coordinates
                )

                # Sprawdź widoczność
                if (
                    not ast_position.is_visible
                    or ast_position.elevation < min_elevation
                ):
                    return None

                # Konwertuj na pozycję anteny
                antenna_position = ast_position.to_antenna_position()
                return antenna_position

            except Exception as e:
                print(f"Błąd obliczania pozycji: {e}")
                return None

        return get_position

    def track_sun(self, min_elevation: float = 10.0):
        """Zwraca funkcję śledzenia Słońca"""
        return self.create_position_function(
            AstronomicalObjectType.SUN, min_elevation=min_elevation
        )

    def track_moon(self, min_elevation: float = 10.0):
        """Zwraca funkcję śledzenia Księżyca"""
        return self.create_position_function(
            AstronomicalObjectType.MOON, min_elevation=min_elevation
        )

    def track_planet(self, planet: AstronomicalObjectType, min_elevation: float = 10.0):
        """Zwraca funkcję śledzenia planety"""
        return self.create_position_function(planet, min_elevation=min_elevation)

    def track_star(self, star_name: str, min_elevation: float = 10.0):
        """Zwraca funkcję śledzenia gwiazdy"""
        return self.create_position_function(
            AstronomicalObjectType.STAR,
            object_name=star_name,
            min_elevation=min_elevation,
        )

    def track_coordinates(
        self, ra_hours: float, dec_degrees: float, min_elevation: float = 10.0
    ):
        """Zwraca funkcję śledzenia współrzędnych"""
        return self.create_position_function(
            AstronomicalObjectType.CUSTOM,
            star_coordinates=(ra_hours, dec_degrees),
            min_elevation=min_elevation,
        )


# Predefiniowane lokalizacje obserwatoriów
OBSERVATORIES = {
    "poznan": ObserverLocation(
        52.40030228321106, 16.955077591791788, 75, "Poznań Polanka"
    )
}

# Jasne gwiazdy do testów
BRIGHT_STARS = {
    "sirius": "Sirius",
    "vega": "Vega",
    "arcturus": "Arcturus",
    "capella": "Capella",
    "rigel": "Rigel",
    "procyon": "Procyon",
    "betelgeuse": "Betelgeuse",
    "aldebaran": "Aldebaran",
    "spica": "Spica",
    "antares": "Antares",
    "pollux": "Pollux",
    "fomalhaut": "Fomalhaut",
    "deneb": "Deneb",
    "regulus": "Regulus",
}

# Przykład użycia
if __name__ == "__main__":
    observer_location = OBSERVATORIES["poznan"]
    calculator = AstronomicalCalculator(observer_location)
    tracker = AstronomicalTracker(calculator)

    print(f"Obserwator: {observer_location.name}")
    print(
        f"Współrzędne: {observer_location.latitude:.4f}°N, {observer_location.longitude:.4f}°E"
    )
    print(f"Wysokość: {observer_location.elevation}m n.p.m.\n")

    # Test pozycji różnych obiektów
    objects_to_test = [
        (AstronomicalObjectType.SUN, "Słońce"),
        (AstronomicalObjectType.MOON, "Księżyc"),
        (AstronomicalObjectType.MARS, "Mars"),
        (AstronomicalObjectType.JUPITER, "Jowisz"),
        (AstronomicalObjectType.VENUS, "Wenus"),
    ]

    current_time = datetime.now(timezone.utc)
    print(f"Czas obserwacji: {current_time.strftime('%d/%m/%Y %H:%M:%S UTC+0')}\n")

    for obj_type, obj_name in objects_to_test:
        try:
            position = calculator.get_position(obj_type)
            antenna_pos = position.to_antenna_position()

            print(f"{obj_name}:")
            print(f"  Azymut: {position.azimuth:.2f}°")
            print(f"  Elewacja: {position.elevation:.2f}°")
            print(f"  Widoczny: {'Tak' if position.is_visible else 'Nie'}")
            print(f"  Jasność: {position.magnitude:.1f}m")
            if antenna_pos:
                print(
                    f"  Pozycja anteny: Az={antenna_pos.azimuth:.2f}°, El={antenna_pos.elevation:.2f}°"
                )
            print()

        except Exception as e:
            print(f"Błąd dla {obj_name}: {e}\n")

    # Test śledzenia Słońca
    print("Test funkcji śledzenia Słońca:")
    sun_tracker = tracker.track_sun(min_elevation=0.0)
    sun_position = sun_tracker()

    if sun_position:
        print(
            f"Słońce - pozycja anteny: Az={sun_position.azimuth:.2f}°, El={sun_position.elevation:.2f}°"
        )
    else:
        print("Słońce nie jest widoczne lub jest zbyt nisko")

    # Test czasu wschodu/zachodu Słońca
    print("\nCzasy wschodu/zachodu Słońca:")
    sun_times = calculator.calculate_rise_set_times(AstronomicalObjectType.SUN)
    for event, time_val in sun_times.items():
        if time_val:
            print(f"  {event}: {time_val.strftime('%H:%M:%S')}")
        else:
            print(f"  {event}: Brak")
