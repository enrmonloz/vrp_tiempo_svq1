"""Reparto horario de cada ruta: tramos mañana/tarde y pausa para comer.

El solver trabaja con un horizonte de tiempo efectivo (conduccion + servicio).
La pausa de la comida no consume jornada efectiva: se modela como tiempo de
descanso que se anade al reloj real del conductor cuando aplica.

Reglas operativas asumidas (basadas en la peticion del usuario):

- Cada ruta arranca en ``ScheduleConfig.start_hour:start_minute`` (08:00 por
  defecto).
- Si el tiempo efectivo de ruta no supera ``morning_max_min`` (4h por
  defecto), no hace falta pausa: toda la ruta cabe en la jornada de mañana.
- Si lo supera, se inserta una pausa de comida de ``lunch_break_min`` (30 min
  por defecto) **justo despues** de la primera parada cuyo final de servicio
  cruce el umbral. La pausa NO se imputa al horizonte del solver pero SI se
  suma al reloj real del conductor.
- Las paradas anteriores a la pausa son ``manana``; las posteriores son
  ``tarde``.

Para rutas dedicadas (depot -> nodo -> depot) hay una unica parada y la
pausa cae despues de ella si la ruta es lo suficientemente larga (en la
practica, casi nunca, porque el round-trip suele caber en una mañana).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ScheduleConfig:
    """Parametros del reparto horario.

    Atributos:
        start_hour, start_minute: hora a la que arranca cada ruta. La misma
            para toda la flota porque asumimos arranque sincronizado.
        lunch_break_min: duracion de la pausa para comer (minutos).
        morning_max_min: tiempo efectivo maximo continuado antes de tener
            que parar a comer.
    """

    start_hour: int = 8
    start_minute: int = 0
    lunch_break_min: float = 30.0
    morning_max_min: float = 240.0  # 4h sin pausa

    def validate(self) -> None:
        if not (0 <= self.start_hour <= 23):
            raise ValueError("start_hour debe estar en [0, 23]")
        if not (0 <= self.start_minute <= 59):
            raise ValueError("start_minute debe estar en [0, 59]")
        if self.lunch_break_min < 0:
            raise ValueError("lunch_break_min no puede ser negativo")
        if self.morning_max_min <= 0:
            raise ValueError("morning_max_min debe ser positivo")

    @property
    def start_min_of_day(self) -> int:
        return int(self.start_hour) * 60 + int(self.start_minute)


@dataclass
class StopSchedule:
    """Horario absoluto y tramo de una parada concreta de la ruta."""

    node_index: int
    node_name: str
    arrival_clock: str   # "HH:MM"
    leave_clock: str     # "HH:MM"
    period: str          # "manana" | "tarde"


@dataclass
class RouteSchedule:
    """Reparto horario de una ruta completa (VRP o dedicada)."""

    start_clock: str
    end_clock: str
    morning_end_clock: str  # cuando arranca la pausa (= end si no hay pausa)
    afternoon_start_clock: str  # cuando termina la pausa
    has_lunch_break: bool
    lunch_break_min: float
    morning_stops: int
    afternoon_stops: int
    stops: List[StopSchedule]

    @property
    def shift_label(self) -> str:
        if self.morning_stops == 0 and self.afternoon_stops == 0:
            return "Sin paradas"
        if not self.has_lunch_break:
            return "Solo mañana"
        if self.morning_stops > 0 and self.afternoon_stops > 0:
            return "Mañana + tarde"
        if self.afternoon_stops > 0:
            return "Solo tarde"
        # Hay pausa pero ya no quedan paradas tras comer: la tarde es solo el
        # viaje de regreso al deposito.
        return "Mañana + retorno tarde"


def _format_clock(minutes_from_midnight: float) -> str:
    total = int(round(float(minutes_from_midnight)))
    total = max(0, total)
    h = (total // 60) % 24
    m = total % 60
    return f"{h:02d}:{m:02d}"


@dataclass
class _StopInput:
    node_index: int
    node_name: str
    arrival_time_min: float  # min relativos al inicio de la ruta (sin pausa)
    service_time_min: float


def _compute_schedule(
    *,
    stops: List[_StopInput],
    total_route_time_min: float,
    cfg: ScheduleConfig,
) -> RouteSchedule:
    cfg.validate()
    start_abs = float(cfg.start_min_of_day)

    morning_stops: List[StopSchedule] = []
    afternoon_stops: List[StopSchedule] = []
    lunch_taken = False
    morning_end_rel = 0.0  # tiempo relativo (sin pausa) en el que arranca la pausa

    for stop in stops:
        arrival_rel = float(stop.arrival_time_min)
        leave_rel = arrival_rel + float(stop.service_time_min)

        if not lunch_taken:
            arrival_abs = start_abs + arrival_rel
            leave_abs = start_abs + leave_rel
            morning_stops.append(
                StopSchedule(
                    node_index=int(stop.node_index),
                    node_name=str(stop.node_name),
                    arrival_clock=_format_clock(arrival_abs),
                    leave_clock=_format_clock(leave_abs),
                    period="manana",
                )
            )
            # Si esta parada cruzo el umbral, la pausa empieza al terminar su
            # servicio.
            if leave_rel > cfg.morning_max_min:
                lunch_taken = True
                morning_end_rel = leave_rel
        else:
            # Tras la pausa: hora absoluta = start + relativo + lunch_break.
            arrival_abs = start_abs + arrival_rel + cfg.lunch_break_min
            leave_abs = start_abs + leave_rel + cfg.lunch_break_min
            afternoon_stops.append(
                StopSchedule(
                    node_index=int(stop.node_index),
                    node_name=str(stop.node_name),
                    arrival_clock=_format_clock(arrival_abs),
                    leave_clock=_format_clock(leave_abs),
                    period="tarde",
                )
            )

    if not lunch_taken:
        morning_end_rel = float(total_route_time_min)
        end_abs = start_abs + float(total_route_time_min)
        morning_end_abs = end_abs
        afternoon_start_abs = end_abs
        lunch_break_min = 0.0
    else:
        morning_end_abs = start_abs + morning_end_rel
        afternoon_start_abs = morning_end_abs + cfg.lunch_break_min
        end_abs = start_abs + float(total_route_time_min) + cfg.lunch_break_min
        lunch_break_min = float(cfg.lunch_break_min)

    return RouteSchedule(
        start_clock=_format_clock(start_abs),
        end_clock=_format_clock(end_abs),
        morning_end_clock=_format_clock(morning_end_abs),
        afternoon_start_clock=_format_clock(afternoon_start_abs),
        has_lunch_break=lunch_taken,
        lunch_break_min=lunch_break_min,
        morning_stops=len(morning_stops),
        afternoon_stops=len(afternoon_stops),
        stops=[*morning_stops, *afternoon_stops],
    )


def schedule_vrp_route(route, cfg: ScheduleConfig) -> RouteSchedule:
    """Calcula el horario de una ``VrpRoute``."""
    stops = [
        _StopInput(
            node_index=s.node_index,
            node_name=s.node_name,
            arrival_time_min=s.arrival_time_min,
            service_time_min=s.service_time_min,
        )
        for s in route.stops
    ]
    return _compute_schedule(
        stops=stops,
        total_route_time_min=route.total_time_min,
        cfg=cfg,
    )


def schedule_dedicated_route(route, cfg: ScheduleConfig) -> RouteSchedule:
    """Calcula el horario de una ``DedicatedRoute`` (depot -> nodo -> depot).

    Tiene una unica parada cuyo arrival_time_min es la mitad del round-trip
    (estimacion: ida).
    """
    one_way_time = float(route.travel_time_min) / 2.0
    stops = [
        _StopInput(
            node_index=route.node_index,
            node_name=route.node_name,
            arrival_time_min=one_way_time,
            service_time_min=route.service_time_min,
        )
    ]
    return _compute_schedule(
        stops=stops,
        total_route_time_min=route.total_time_min,
        cfg=cfg,
    )
