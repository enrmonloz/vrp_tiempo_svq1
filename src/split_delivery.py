"""Preprocesado de split-delivery por tiempo.

Algunos nodos (especialmente las nuevas capitales como Malaga o Cordoba) pueden
tener tantos paquetes que su tiempo total nodal sobrepase la jornada maxima
del conductor. En esos casos generamos una o varias "rutas dedicadas" que
parten del deposito, entregan un trozo del nodo y vuelven, hasta dejar un
remanente que SI cabe dentro de una jornada normal y entra al solver general.

Existen dos modos de servicio para las rutas dedicadas:

- **Furgoneta** (modo por defecto): paga ``per_pkg`` por cada paquete (suma
  ``service_time_per_package`` + ``inter_package_time``) y la limitacion es
  el tiempo de jornada disponible despues del round-trip.
- **Trailer**: solo se usa cuando ``TrailerConfig.applies_to(nodo)`` es True
  (por defecto, los 4 nodos grandes). El trailer descarga en bloque en el
  nodo: paga un ``unloading_time_min`` fijo independientemente del numero de
  paquetes y tiene una ``packages_capacity`` por viaje. Esto reduce
  drasticamente el numero de rutas dedicadas necesarias.

Tras el split, los paquetes que no se llevan en rutas dedicadas se devuelven
como demanda residual para el VRP general.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .trailer import TrailerConfig


@dataclass
class DedicatedRoute:
    """Una ruta dedicada deposito -> nodo -> deposito para un nodo grande."""

    node_index: int
    node_name: str
    packages: int
    service_time_min: float
    travel_time_min: float
    travel_distance_km: float
    vehicle_type: str = "furgoneta"  # "furgoneta" | "trailer"

    @property
    def total_time_min(self) -> float:
        return self.service_time_min + self.travel_time_min


@dataclass
class SplitDeliveryResult:
    """Resultado del preprocesado de split-delivery por tiempo."""

    dedicated_routes: List[DedicatedRoute]
    residual_packages: np.ndarray
    residual_service_time: np.ndarray


def _split_node_with_trailer(
    *,
    node_index: int,
    node_name: str,
    node_pkgs: int,
    round_trip_time: float,
    round_trip_dist: float,
    max_workday_min: float,
    trailer: TrailerConfig,
) -> List[DedicatedRoute]:
    """Genera las rutas dedicadas con trailer para un nodo grande.

    El trailer realiza tantos viajes como sea necesario para cubrir todos los
    paquetes, distribuidos balanceadamente para igualar la carga entre
    viajes. Cada viaje paga round-trip + ``unloading_time_min``.
    """
    capacity = int(trailer.packages_capacity)
    cycle_time = round_trip_time + float(trailer.unloading_time_min)
    if cycle_time > max_workday_min:
        raise RuntimeError(
            f"El nodo '{node_name}' no es viable con trailer: round-trip "
            f"({round_trip_time:.1f} min) + descarga ({trailer.unloading_time_min:.1f} min) "
            f"= {cycle_time:.1f} min supera la jornada maxima ({max_workday_min:.1f} min)."
        )

    # Numero minimo de viajes necesarios y reparto balanceado.
    n_routes = -(-int(node_pkgs) // capacity)  # ceil(node_pkgs / capacity)
    base = int(node_pkgs) // n_routes
    extra = int(node_pkgs) % n_routes

    routes: List[DedicatedRoute] = []
    for k in range(n_routes):
        chunk = base + (1 if k < extra else 0)
        if chunk <= 0:
            continue
        routes.append(
            DedicatedRoute(
                node_index=int(node_index),
                node_name=node_name,
                packages=int(chunk),
                service_time_min=float(trailer.unloading_time_min),
                travel_time_min=float(round_trip_time),
                travel_distance_km=float(round_trip_dist),
                vehicle_type="trailer",
            )
        )
    return routes


def _split_node_with_van(
    *,
    node_index: int,
    node_name: str,
    node_pkgs: int,
    node_service: float,
    round_trip_time: float,
    round_trip_dist: float,
    max_workday_min: float,
    per_pkg: float,
) -> tuple[List[DedicatedRoute], int]:
    """Genera rutas dedicadas con furgoneta y devuelve (rutas, residual_pkgs)."""
    if node_service + round_trip_time <= max_workday_min:
        return [], int(node_pkgs)  # cabe en una jornada normal, no hay split

    available_service = max_workday_min - round_trip_time
    if available_service <= 0:
        raise RuntimeError(
            f"El nodo '{node_name}' es inviable: el viaje de ida y vuelta "
            f"({round_trip_time:.1f} min) ya supera la jornada maxima "
            f"({max_workday_min:.1f} min)."
        )

    max_pkgs_per_route = int(available_service // per_pkg)
    if max_pkgs_per_route <= 0:
        raise RuntimeError(
            f"El nodo '{node_name}' es inviable: ni un paquete cabe "
            f"despues de descontar viaje ({round_trip_time:.1f} min)."
        )

    routes: List[DedicatedRoute] = []
    excess = int(node_pkgs) - max_pkgs_per_route
    if excess <= 0:
        # Una sola ruta dedicada cubre todo; no queda residual.
        routes.append(
            DedicatedRoute(
                node_index=int(node_index),
                node_name=node_name,
                packages=int(node_pkgs),
                service_time_min=float(node_pkgs) * per_pkg,
                travel_time_min=float(round_trip_time),
                travel_distance_km=float(round_trip_dist),
                vehicle_type="furgoneta",
            )
        )
        return routes, 0

    n_dedicated = -(-excess // max_pkgs_per_route)  # ceil(excess / max)
    base = excess // n_dedicated
    extra = excess % n_dedicated
    for k in range(n_dedicated):
        chunk = base + (1 if k < extra else 0)
        if chunk <= 0:
            continue
        routes.append(
            DedicatedRoute(
                node_index=int(node_index),
                node_name=node_name,
                packages=int(chunk),
                service_time_min=float(chunk) * per_pkg,
                travel_time_min=float(round_trip_time),
                travel_distance_km=float(round_trip_dist),
                vehicle_type="furgoneta",
            )
        )

    residual = int(node_pkgs) - excess  # = max_pkgs_per_route, cabe en jornada
    return routes, residual


def split_oversized_nodes(
    *,
    names: list[str],
    packages: np.ndarray,
    service_time_per_node: np.ndarray,
    distance_matrix: np.ndarray,
    time_matrix: np.ndarray,
    depot_index: int,
    max_workday_min: float,
    service_time_per_package_min: float,
    inter_package_time_min: float,
    trailer: TrailerConfig | None = None,
) -> SplitDeliveryResult:
    """Divide nodos cuya entrega completa no cabe en una jornada.

    Para nodos a los que aplica un ``TrailerConfig`` activo (por defecto los
    nodos grandes Cadiz/Malaga/Cordoba/Huelva/Granada), todas las rutas dedicadas se
    hacen con trailer y el residual queda a 0.

    Para el resto de nodos, si la entrega completa no cabe en jornada, se
    generan rutas dedicadas con furgoneta balanceadas y se devuelve un
    residual que SI cabe en una jornada normal para que entre al VRP general.
    """
    n = len(names)
    if packages.shape[0] != n or service_time_per_node.shape[0] != n:
        raise ValueError("Tamanos inconsistentes entre packages, service_time y names")
    if distance_matrix.shape != (n, n) or time_matrix.shape != (n, n):
        raise ValueError("Matrices distancia/tiempo no son cuadradas o no coinciden con n")
    if max_workday_min <= 0:
        raise ValueError("max_workday_min debe ser positivo")

    if trailer is not None:
        trailer.validate()

    per_pkg = float(service_time_per_package_min) + float(inter_package_time_min)

    residual_pkgs = packages.astype(int).copy()
    residual_service = service_time_per_node.astype(float).copy()
    dedicated: list[DedicatedRoute] = []

    for i in range(n):
        if i == depot_index:
            continue
        node_pkgs = int(residual_pkgs[i])
        if node_pkgs <= 0:
            continue
        node_service = float(residual_service[i])
        round_trip_time = float(time_matrix[depot_index, i]) + float(time_matrix[i, depot_index])
        round_trip_dist = float(distance_matrix[depot_index, i]) + float(distance_matrix[i, depot_index])

        # Caso A: trailer aplica a este nodo -> todas las rutas dedicadas
        # las hace el trailer y el residual queda a 0.
        if trailer is not None and trailer.applies_to(names[i]):
            routes = _split_node_with_trailer(
                node_index=i,
                node_name=names[i],
                node_pkgs=node_pkgs,
                round_trip_time=round_trip_time,
                round_trip_dist=round_trip_dist,
                max_workday_min=max_workday_min,
                trailer=trailer,
            )
            dedicated.extend(routes)
            residual_pkgs[i] = 0
            residual_service[i] = 0.0
            continue

        # Caso B: per_pkg = 0 -> sin tiempo por paquete no hay split posible.
        if per_pkg <= 0:
            continue  # todo queda como residual sin split

        # Caso C: furgoneta. Solo se generan rutas dedicadas si no cabe todo
        # en una jornada normal.
        routes, residual = _split_node_with_van(
            node_index=i,
            node_name=names[i],
            node_pkgs=node_pkgs,
            node_service=node_service,
            round_trip_time=round_trip_time,
            round_trip_dist=round_trip_dist,
            max_workday_min=max_workday_min,
            per_pkg=per_pkg,
        )
        dedicated.extend(routes)
        residual_pkgs[i] = int(residual)
        residual_service[i] = float(residual) * per_pkg

    return SplitDeliveryResult(
        dedicated_routes=dedicated,
        residual_packages=residual_pkgs,
        residual_service_time=residual_service,
    )
