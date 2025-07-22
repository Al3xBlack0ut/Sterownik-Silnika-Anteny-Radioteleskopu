"""
REST API dla sterownika anteny radioteleskopu
Wykorzystuje protokół SPID do sterowania anteną i kalkulator astronomiczny

Autor: Aleks Czarnecki
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import sys

# Import z głównego folderu
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from antenna_controller import (
    AntennaControllerFactory, AntennaController, SPIDMotorDriver,
    SimulatedMotorDriver, Position, AntennaError, MotorConfig, AntennaLimits,
    auto_detect_spid_ports, find_working_spid_port, AntennaState
)
from astronomic_calculator import (
    AstronomicalCalculator, ObserverLocation, AstronomicalObjectType
)

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Globalne instancje
antenna_controller: Optional[AntennaController] = None
astro_calculator: Optional[AstronomicalCalculator] = None
current_observer_location: Optional[ObserverLocation] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Uruchamianie API radioteleskopa...")
    yield
    # Shutdown
    global antenna_controller
    logger.info("Zamykanie API...")

    if antenna_controller:
        try:
            antenna_controller.stop()
            antenna_controller.shutdown()
        except Exception as e:
            logger.error(f"Błąd podczas zamykania: {e}")

# Inicjalizacja FastAPI
app = FastAPI(
    title="Sterownik Silnika Anteny Radioteleskopu API",
    description="REST API do sterowania anteną radioteleskopu z protokołem SPID",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Konfiguracja CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Modele Pydantic dla API
class PositionModel(BaseModel):
    azimuth: float = Field(..., ge=0, le=360, description="Azymut w stopniach (0-360)")
    elevation: float = Field(..., ge=-90, le=90, description="Elewacja w stopniach (-90 do 90)")

class ObserverLocationModel(BaseModel):
    latitude: float = Field(..., ge=-90, le=90, description="Szerokość geograficzna w stopniach")
    longitude: float = Field(..., ge=-180, le=180, description="Długość geograficzna w stopniach")
    elevation: float = Field(0, ge=0, description="Wysokość n.p.m. w metrach")
    name: str = Field("Observer", description="Nazwa lokalizacji")

class ConnectionConfigModel(BaseModel):
    port: Optional[str] = Field(None, description="Port szeregowy (auto-detect jeśli nie podano)")
    baudrate: int = Field(115200, description="Prędkość transmisji")
    use_simulator: bool = Field(False, description="Użyj symulatora zamiast prawdziwego sprzętu")

class StatusResponse(BaseModel):
    connected: bool
    current_position: Optional[PositionModel]
    is_moving: bool
    last_error: Optional[str]
    observer_location: Optional[ObserverLocationModel]

class AstronomicalObjectModel(BaseModel):
    name: str = Field(..., description="Nazwa obiektu astronomicznego")
    object_type: AstronomicalObjectType = Field(..., description="Typ obiektu")

# Pomocnicze funkcje
def get_antenna_controller() -> AntennaController:
    global antenna_controller
    if antenna_controller is None:
        raise HTTPException(status_code=503, detail="Kontroler anteny nie jest zainicjalizowany. Użyj /connect")
    return antenna_controller

def get_astro_calculator() -> AstronomicalCalculator:
    global astro_calculator, current_observer_location
    if astro_calculator is None or current_observer_location is None:
        raise HTTPException(status_code=503, detail="Kalkulator astronomiczny nie jest skonfigurowany. Ustaw lokalizację obserwatora")
    return astro_calculator

# Endpointy API

@app.get("/", summary="Status API")
async def root():
    """Podstawowe informacje o API"""
    return {
        "name": "Sterownik Silnika Anteny Radioteleskopu API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }

@app.get("/web_interface.html")
async def get_web_interface():
    """Serwuj interfejs webowy"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_file = os.path.join(current_dir, "web_interface.html")
    if os.path.exists(html_file):
        return FileResponse(html_file)
    else:
        raise HTTPException(status_code=404, detail="Interfejs webowy nie został znaleziony")

@app.get("/status", response_model=StatusResponse, summary="Status systemu")
async def get_status():
    """Pobierz aktualny status systemu anteny"""
    global antenna_controller, current_observer_location

    connected = antenna_controller is not None and hasattr(antenna_controller.motor_driver, 'connected') and antenna_controller.motor_driver.connected
    current_position = None
    is_moving = False
    last_error = None

    if connected:
        try:
            pos = antenna_controller.current_position
            if pos:
                current_position = PositionModel(azimuth=pos.azimuth, elevation=pos.elevation)
            is_moving = antenna_controller.state == AntennaState.MOVING
        except Exception as e:
            last_error = str(e)
            logger.error(f"Błąd pobierania statusu: {e}")

    observer_loc = None
    if current_observer_location:
        observer_loc = ObserverLocationModel(
            latitude=current_observer_location.latitude,
            longitude=current_observer_location.longitude,
            elevation=current_observer_location.elevation,
            name=current_observer_location.name
        )

    return StatusResponse(
        connected=connected,
        current_position=current_position,
        is_moving=is_moving,
        last_error=last_error,
        observer_location=observer_loc
    )

@app.post("/connect", summary="Połącz z anteną")
async def connect_antenna(config: ConnectionConfigModel):
    """Nawiąż połączenie z anteną"""
    global antenna_controller

    try:
        if config.use_simulator:
            logger.info("Łączę z symulatorem...")
            antenna_controller = AntennaControllerFactory.create_simulator_controller(
                simulation_speed=2000.0,
                motor_config=MotorConfig(),
                limits=AntennaLimits()
            )
        else:
            port = config.port
            if not port:
                # Auto-detect port
                logger.info("Szukam portów sprzętowych...")
                ports = auto_detect_spid_ports()
                logger.info(f"Znalezione porty: {ports}")

                if not ports:
                    raise HTTPException(status_code=404, detail="Nie znaleziono portów SPID")

                working_port = find_working_spid_port(config.baudrate)
                if not working_port:
                    raise HTTPException(status_code=404, detail="Nie znaleziono działającego portu SPID")
                port = working_port

            logger.info(f"Łączę z portem {port}...")
            antenna_controller = AntennaControllerFactory.create_spid_controller(
                port=port,
                baudrate=config.baudrate,
                motor_config=MotorConfig(),
                limits=AntennaLimits()
            )

        # Inicjalizuj kontroler
        antenna_controller.initialize()

        logger.info("Połączenie nawiązane pomyślnie")
        return {"status": "connected", "port": config.port, "simulator": config.use_simulator}

    except Exception as e:
        logger.error(f"Błąd połączenia: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd połączenia: {str(e)}")

@app.post("/disconnect", summary="Rozłącz z anteną")
async def disconnect_antenna():
    """Rozłącz z anteną"""
    global antenna_controller

    try:
        if antenna_controller:
            antenna_controller.stop()
            antenna_controller.shutdown()
            antenna_controller = None

        logger.info("Rozłączono z anteną")
        return {"status": "disconnected"}

    except Exception as e:
        logger.error(f"Błąd rozłączania: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd rozłączania: {str(e)}")

@app.get("/position", response_model=PositionModel, summary="Aktualna pozycja")
async def get_position():
    """Pobierz aktualną pozycję anteny"""
    controller = get_antenna_controller()

    try:
        pos = controller.current_position
        if pos is None:
            raise HTTPException(status_code=404, detail="Nie można pobrać pozycji")

        return PositionModel(azimuth=pos.azimuth, elevation=pos.elevation)

    except Exception as e:
        logger.error(f"Błąd pobierania pozycji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd pobierania pozycji: {str(e)}")

@app.post("/position", summary="Ustaw pozycję")
async def set_position(position: PositionModel):
    """Ustaw nową pozycję anteny"""
    controller = get_antenna_controller()

    try:
        target_pos = Position(position.azimuth, position.elevation)
        controller.move_to(target_pos)

        return {"status": "moving", "target": position.model_dump()}

    except Exception as e:
        logger.error(f"Błąd ustawiania pozycji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd ustawiania pozycji: {str(e)}")

@app.post("/stop", summary="Zatrzymaj antenę")
async def stop_antenna():
    """Natychmiastowe zatrzymanie anteny"""
    controller = get_antenna_controller()

    try:
        controller.stop()
        logger.info("Antena zatrzymana")
        return {"status": "stopped"}

    except Exception as e:
        logger.error(f"Błąd zatrzymywania: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd zatrzymywania: {str(e)}")

@app.post("/observer", summary="Ustaw lokalizację obserwatora")
async def set_observer_location(location: ObserverLocationModel):
    """Ustaw lokalizację obserwatora dla obliczeń astronomicznych"""
    global astro_calculator, current_observer_location

    try:
        current_observer_location = ObserverLocation(
            latitude=location.latitude,
            longitude=location.longitude,
            elevation=location.elevation,
            name=location.name
        )

        astro_calculator = AstronomicalCalculator(current_observer_location)

        logger.info(f"Ustawiono lokalizację obserwatora: {location.name}")
        return {"status": "set", "location": location.model_dump()}

    except Exception as e:
        logger.error(f"Błąd ustawiania lokalizacji: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd ustawiania lokalizacji: {str(e)}")

@app.get("/observer", response_model=ObserverLocationModel, summary="Pobierz lokalizację obserwatora")
async def get_observer_location():
    """Pobierz aktualną lokalizację obserwatora"""
    global current_observer_location

    if current_observer_location is None:
        raise HTTPException(status_code=404, detail="Lokalizacja obserwatora nie jest ustawiona")

    return ObserverLocationModel(
        latitude=current_observer_location.latitude,
        longitude=current_observer_location.longitude,
        elevation=current_observer_location.elevation,
        name=current_observer_location.name
    )

@app.post("/track/{object_name}", summary="Śledź obiekt astronomiczny")
async def track_object(object_name: str, object_type: AstronomicalObjectType = AstronomicalObjectType.SUN):
    """Rozpocznij śledzenie obiektu astronomicznego"""
    controller = get_antenna_controller()
    calculator = get_astro_calculator()

    try:
        # Oblicz pozycję obiektu
        if object_type == AstronomicalObjectType.SUN:
            position = calculator.get_sun_position()
        elif object_type == AstronomicalObjectType.MOON:
            position = calculator.get_moon_position()
        elif object_name.lower() in ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]:
            planet_type = AstronomicalObjectType(object_name.lower())
            position = calculator.get_planet_position(planet_type)
        else:
            position = calculator.get_star_position(object_name)

        if position is None or not position.is_visible:
            raise HTTPException(status_code=404, detail=f"Obiekt {object_name} nie jest widoczny")

        # Konwertuj na pozycję anteny i przesuń
        antenna_position = position.to_antenna_position()
        if antenna_position:
            controller.move_to(antenna_position)
        else:
            raise HTTPException(status_code=400, detail=f"Obiekt {object_name} jest poza zasięgiem anteny")

        logger.info(f"Przesunięto antenę do obiektu: {object_name}")
        return {
            "status": "moved_to_object",
            "object": object_name,
            "type": object_type.value,
            "position": {"azimuth": position.azimuth, "elevation": position.elevation}
        }

    except Exception as e:
        logger.error(f"Błąd pozycjonowania na obiekt: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd pozycjonowania na obiekt: {str(e)}")

@app.post("/stop_tracking", summary="Zatrzymaj śledzenie")
async def stop_tracking():
    """Zatrzymaj śledzenie obiektu"""
    controller = get_antenna_controller()

    try:
        controller.stop()
        logger.info("Zatrzymano śledzenie")
        return {"status": "tracking_stopped"}

    except Exception as e:
        logger.error(f"Błąd zatrzymywania śledzenia: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd zatrzymywania śledzenia: {str(e)}")

@app.get("/ports", summary="Lista dostępnych portów")
async def list_ports():
    """Lista dostępnych portów szeregowych"""
    try:
        ports = auto_detect_spid_ports()
        return {"ports": ports}

    except Exception as e:
        logger.error(f"Błąd listowania portów: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd listowania portów: {str(e)}")

@app.get("/astronomical/position/{object_name}", summary="Pozycja obiektu astronomicznego")
async def get_astronomical_position(object_name: str):
    """Pobierz aktualną pozycję obiektu astronomicznego"""
    calculator = get_astro_calculator()

    try:
        object_name_lower = object_name.lower()

        # Mapowanie obiektów na właściwe typy
        if object_name_lower == "sun":
            position = calculator.get_sun_position()
        elif object_name_lower == "moon":
            position = calculator.get_moon_position()
        elif object_name_lower in ["mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune"]:
            # Konwertuj nazwę na AstronomicalObjectType
            planet_type = AstronomicalObjectType(object_name_lower)
            position = calculator.get_planet_position(planet_type)
        else:
            # Dla gwiazd i innych obiektów
            position = calculator.get_star_position(object_name)

        if position is None:
            raise HTTPException(status_code=404, detail=f"Nie można obliczyć pozycji dla obiektu: {object_name}")

        if not position.is_visible:
            logger.warning(f"Obiekt {object_name} jest pod horyzontem")

        return {
            "azimuth": position.azimuth,
            "elevation": position.elevation,
            "distance": position.distance,
            "ra": position.ra,
            "dec": position.dec,
            "is_visible": position.is_visible,
            "magnitude": position.magnitude if hasattr(position, 'magnitude') else None
        }

    except ValueError as e:
        logger.error(f"Nieprawidłowy obiekt astronomiczny: {object_name}")
        raise HTTPException(status_code=400, detail=f"Nieprawidłowy obiekt astronomiczny: {object_name}")
    except Exception as e:
        logger.error(f"Błąd obliczania pozycji obiektu {object_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Błąd obliczania pozycji: {str(e)}")

# Obsługa błędów
@app.exception_handler(AntennaError)
async def antenna_error_handler(request, exc: AntennaError):
    logger.error(f"Błąd anteny: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Błąd anteny: {str(exc)}"}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    import traceback
    tb_str = traceback.format_exc()
    logger.error(f"Nieoczekiwany błąd: {exc}\n{tb_str}")
    return JSONResponse(
        status_code=500,
        content={"detail": f"Błąd serwera: {str(exc)}"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
