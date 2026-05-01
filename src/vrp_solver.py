"""Solver VRP por tiempo con flota heterogenea (diesel + electrica).

A diferencia del proyecto historico (que minimizaba coste de capacidad), aqui
la dimension principal es TIEMPO. La jornada maxima del conductor es la
restriccion dura: ningun vehiculo puede acumular mas de ``max_workday_min``
minutos entre traslados y servicio.

A mayores, esta version soporta flota heterogenea:
- Diesel: sin restriccion de rango, coste fijo ligeramente mayor.
- Electrica: rango maximo por jornada (km) como dimension dura adicional,
  coste fijo ligeramente menor para que el solver la prefiera cuando cabe.

El objetivo del solver es minimizar el numero de vehiculos usados (via fixed
cost grande por vehiculo) y, secundariamente, minimizar el tiempo total de
los arcos. La mezcla optima diesel/electrica la decide el propio solver
respetando los limites de flota configurados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List

import numpy as np

from .fleet import FleetConfig, VehicleType

try:
    from ortools.constraint_solver import pywrapcp, routing_enums_pb2
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "ortools no esta instalado. Anade 'ortools' a tu entorno antes de ejecutar el solver."
    ) from exc


class SolverStrategy(str, Enum):
    """Estrategia de primera solucion del solver.

    Mapeo a OR-Tools FirstSolutionStrategy:
    - NEAREST_NEIGHBOR  -> PATH_CHEAPEST_ARC (vecino mas cercano por arco)
    - SWEEP             -> SWEEP (algoritmo de barrido por angulo polar)
    - SAVINGS           -> SAVINGS (Clarke-Wright)
    - INSERTION         -> PARALLEL_CHEAPEST_INSERTION (insercion paralela mas barata)
    - CHRISTOFIDES      -> CHRISTOFIDES (heuristica 3/2-aproximada, potente para
                           rutas largas; OR-Tools la generaliza para VRP)
    """

    NEAREST_NEIGHBOR = "nearest_neighbor"
    SWEEP = "sweep"
    SAVINGS = "savings"
    INSERTION = "insertion"
    CHRISTOFIDES = "christofides"


def _strategy_to_ortools(strategy: SolverStrategy) -> int:
    return {
        SolverStrategy.NEAREST_NEIGHBOR: routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC,
        SolverStrategy.SWEEP: routing_enums_pb2.FirstSolutionStrategy.SWEEP,
        SolverStrategy.SAVINGS: routing_enums_pb2.FirstSolutionStrategy.SAVINGS,
        SolverStrategy.INSERTION: routing_enums_pb2.FirstSolutionStrategy.PARALLEL_CHEAPEST_INSERTION,
        SolverStrategy.CHRISTOFIDES: routing_enums_pb2.FirstSolutionStrategy.CHRISTOFIDES,
    }[strategy]


@dataclass
class VrpStop:
    node_index: int
    node_name: str
    packages: int
    service_time_min: float
    arrival_time_min: float


@dataclass
class VrpRoute:
    vehicle_id: int
    vehicle_type: VehicleType
    stops: List[VrpStop]
    travel_time_min: float
    service_time_min: float
    travel_distance_km: float

    @property
    def total_time_min(self) -> float:
        return self.travel_time_min + self.service_time_min


@dataclass
class VrpResult:
    routes: List[VrpRoute] = field(default_factory=list)
    unassigned_nodes: List[int] = field(default_factory=list)
    total_travel_time_min: float = 0.0
    total_service_time_min: float = 0.0
    total_distance_km: float = 0.0
    objective_value: int = 0

    @property
    def total_time_min(self) -> float:
        return self.total_travel_time_min + self.total_service_time_min

    @property
    def vehicle_count(self) -> int:
        return len(self.routes)

    @property
    def diesel_count(self) -> int:
        return sum(1 for r in self.routes if r.vehicle_type == VehicleType.DIESEL)

    @property
    def electric_count(self) -> int:
        return sum(1 for r in self.routes if r.vehicle_type == VehicleType.ELECTRIC)


# Escala para convertir minutos -> unidades enteras (segundos).
_TIME_SCALE = 60
# Escala para convertir km -> unidades enteras (metros).
_DIST_SCALE = 1000
# Cota muy grande para vehiculos sin restriccion de distancia.
_LARGE_DIST = 10**12


def _sweep_initial_routes(
    *,
    customer_indices: List[int],
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    depot_index: int,
    time_matrix: np.ndarray,
    service_int: np.ndarray,
    horizon: int,
    n_diesel: int,
    n_electric: int,
    dist_int: np.ndarray,
    electric_range_int: int,
    time_scale: int,
) -> List[List[int]]:
    """Construye rutas iniciales por algoritmo de barrido (Gillett & Miller).

    Ordena los clientes por angulo polar respecto al deposito, recorre la
    secuencia y va abriendo rutas asignadas a vehiculos disponibles
    (primero electricos hasta agotar su rango, luego diesel) cuando la
    siguiente parada haria que se exceda la jornada o el rango electrico.
    Devuelve una lista (una entrada por vehiculo) con los nodos en orden;
    los vehiculos no usados quedan como listas vacias.
    """
    depot_lat = float(latitudes[depot_index])
    depot_lon = float(longitudes[depot_index])

    def polar_angle(idx: int) -> float:
        import math
        return math.atan2(
            float(latitudes[idx]) - depot_lat,
            float(longitudes[idx]) - depot_lon,
        )

    ordered = sorted(customer_indices, key=polar_angle)

    total_vehicles = n_diesel + n_electric
    routes: List[List[int]] = [[] for _ in range(total_vehicles)]
    # Estrategia de asignacion: arrancamos por electricos (vehicle_id >= n_diesel)
    # para favorecerlos cuando caben; si una ruta excede el rango electrico,
    # se vuelca en una diesel.
    electric_ids = list(range(n_diesel, total_vehicles))
    diesel_ids = list(range(n_diesel))

    def route_cost(route: List[int], next_node: int | None = None) -> tuple[int, int]:
        """Devuelve (tiempo_acumulado, distancia_acumulada) en unidades enteras."""
        seq = [depot_index, *route]
        if next_node is not None:
            seq.append(next_node)
        seq.append(depot_index)
        t = 0
        d = 0
        for a, b in zip(seq, seq[1:]):
            t += int(round(time_matrix[a, b] * time_scale))
            d += int(dist_int[a, b])
            if b != depot_index:
                t += int(service_int[b])
        return t, d

    def assign(node: int) -> bool:
        # Probar electricos primero.
        for vid in electric_ids:
            t, d = route_cost(routes[vid], node)
            if t <= horizon and d <= electric_range_int:
                routes[vid].append(node)
                return True
        for vid in diesel_ids:
            t, _ = route_cost(routes[vid], node)
            if t <= horizon:
                routes[vid].append(node)
                return True
        return False

    for node in ordered:
        if not assign(node):
            # Sin vehiculos disponibles: dejamos que OR-Tools intente reubicarlo.
            # No anadimos a ninguna ruta (saldra como faltante en initial, que
            # OR-Tools podra corregir via ReadAssignmentFromRoutes con
            # ignore_inactive_indices=True).
            pass

    return routes


def solve_vrp_by_time(
    *,
    names: list[str],
    distance_matrix: np.ndarray,
    time_matrix: np.ndarray,
    residual_packages: np.ndarray,
    residual_service_time: np.ndarray,
    depot_index: int,
    max_workday_min: float,
    fleet: FleetConfig,
    strategy: SolverStrategy = SolverStrategy.INSERTION,
    time_limit_seconds: int = 30,
    latitudes: np.ndarray | None = None,
    longitudes: np.ndarray | None = None,
) -> VrpResult:
    """Resuelve el VRP residual con flota mixta y dimension temporal.

    Cada arco tiene coste = tiempo_viaje(from->to) + servicio(to). El servicio
    en el depot es 0. La dimension ``Time`` impone que el acumulado al volver
    al deposito no supere ``max_workday_min``. La dimension ``Distance``
    impone que los vehiculos electricos no superen su rango maximo por
    jornada. Para minimizar el numero de vehiculos asignamos un coste fijo
    elevado por vehiculo activo, con la electrica ligeramente mas barata para
    que el solver la prefiera cuando cabe.
    """
    fleet.validate()

    n = len(names)
    if distance_matrix.shape != (n, n) or time_matrix.shape != (n, n):
        raise ValueError("Matrices distancia/tiempo no coinciden con names")
    if residual_packages.shape[0] != n or residual_service_time.shape[0] != n:
        raise ValueError("Tamanos inconsistentes entre residuales y names")
    if max_workday_min <= 0:
        raise ValueError("max_workday_min debe ser positivo")

    n_diesel = int(fleet.max_diesel)
    n_electric = int(fleet.max_electric)
    total_vehicles = n_diesel + n_electric

    customer_indices = [i for i in range(n) if i != depot_index and int(residual_packages[i]) > 0]
    if not customer_indices:
        return VrpResult()

    # OR-Tools trabaja con enteros. Convertimos minutos a segundos y km a metros.
    time_int = np.rint(time_matrix * _TIME_SCALE).astype(np.int64)
    service_int = np.rint(residual_service_time * _TIME_SCALE).astype(np.int64)
    dist_int = np.rint(distance_matrix * _DIST_SCALE).astype(np.int64)
    horizon = int(round(max_workday_min * _TIME_SCALE))
    electric_range_int = int(round(fleet.electric_max_range_km * _DIST_SCALE))

    manager = pywrapcp.RoutingIndexManager(n, total_vehicles, depot_index)
    routing = pywrapcp.RoutingModel(manager)

    def time_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        travel = int(time_int[from_node, to_node])
        service = int(service_int[to_node]) if to_node != depot_index else 0
        return travel + service

    def distance_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(dist_int[from_node, to_node])

    transit_idx = routing.RegisterTransitCallback(time_callback)
    dist_idx = routing.RegisterTransitCallback(distance_callback)

    # Coste de arco = tiempo (mismo callback para todos los vehiculos). La
    # diferenciacion diesel/electrica se hace via SetFixedCostOfVehicle.
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    # Dimension temporal: jornada uniforme para todos los vehiculos.
    routing.AddDimension(
        transit_idx,
        0,            # sin holgura
        horizon,      # capacidad maxima por vehiculo (jornada)
        True,         # forzar inicio en 0
        "Time",
    )

    # Dimension de distancia: capacidades por vehiculo. Diesel = ilimitado;
    # electrica = rango maximo por jornada.
    distance_caps = [
        _LARGE_DIST if fleet.vehicle_type_for(v) == VehicleType.DIESEL else electric_range_int
        for v in range(total_vehicles)
    ]
    routing.AddDimensionWithVehicleCapacity(
        dist_idx,
        0,
        distance_caps,
        True,
        "Distance",
    )

    # Coste fijo por vehiculo: distinto segun tipo para que el solver prefiera
    # electricas cuando caben.
    for vehicle_id in range(total_vehicles):
        if fleet.vehicle_type_for(vehicle_id) == VehicleType.DIESEL:
            routing.SetFixedCostOfVehicle(int(fleet.diesel_fixed_cost), vehicle_id)
        else:
            routing.SetFixedCostOfVehicle(int(fleet.electric_fixed_cost), vehicle_id)

    # Hacemos opcionales los nodos sin demanda y obligatorios los que tienen.
    BIG_PENALTY = 10**12
    for node in range(n):
        if node == depot_index:
            continue
        idx = manager.NodeToIndex(node)
        if int(residual_packages[node]) > 0:
            routing.AddDisjunction([idx], BIG_PENALTY)
        else:
            routing.AddDisjunction([idx], 0)

    def _build_search(strategy: int, metaheuristic: int) -> pywrapcp.RoutingSearchParameters:
        params = pywrapcp.DefaultRoutingSearchParameters()
        params.first_solution_strategy = strategy
        params.local_search_metaheuristic = metaheuristic
        params.time_limit.seconds = max(5, int(time_limit_seconds))
        return params

    # Para SWEEP construimos nosotros la solucion inicial por angulo polar y
    # dejamos que OR-Tools la lea via ReadAssignmentFromRoutes; el binding
    # Python de OR-Tools 9.x no expone SweepArranger asi que el SWEEP nativo
    # cae a fallback con un warning. Hacerlo nosotros es fiel al algoritmo
    # Gillett & Miller (1974) y lo complementa con la metaheuristica de mejora.
    if strategy == SolverStrategy.SWEEP:
        if latitudes is None or longitudes is None:
            raise ValueError(
                "La estrategia SWEEP necesita latitudes y longitudes para el barrido polar."
            )
        initial_routes = _sweep_initial_routes(
            customer_indices=customer_indices,
            latitudes=latitudes,
            longitudes=longitudes,
            depot_index=depot_index,
            time_matrix=time_matrix,
            service_int=service_int,
            horizon=horizon,
            n_diesel=n_diesel,
            n_electric=n_electric,
            dist_int=dist_int,
            electric_range_int=electric_range_int,
            time_scale=_TIME_SCALE,
        )
        initial_assignment = routing.ReadAssignmentFromRoutes(initial_routes, True)
        improvement = _build_search(
            routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC,
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH,
        )
        if initial_assignment is None:
            # La construccion barrido no fue compatible (p.ej. excede capacidad).
            # Reintenta con AUTOMATIC + mejora local.
            solution = routing.SolveWithParameters(improvement)
        else:
            solution = routing.SolveFromAssignmentWithParameters(initial_assignment, improvement)
    else:
        primary_strategy = _strategy_to_ortools(strategy)
        search = _build_search(
            primary_strategy,
            routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH,
        )
        solution = routing.SolveWithParameters(search)
    if solution is None:
        # Reintento con AUTOMATIC + PATH_CHEAPEST_ARC como salvaguarda. Si la
        # estrategia primaria ya era la mas conservadora, dejamos que OR-Tools
        # decida via AUTOMATIC.
        fallback_strategy = (
            routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC
            if strategy == SolverStrategy.NEAREST_NEIGHBOR
            else routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        )
        fallback = _build_search(
            fallback_strategy,
            routing_enums_pb2.LocalSearchMetaheuristic.AUTOMATIC,
        )
        solution = routing.SolveWithParameters(fallback)
    if solution is None:
        raise RuntimeError(
            "OR-Tools no encontro solucion factible. Revisa la jornada maxima, "
            "el tamano/composicion de la flota o el rango electrico."
        )

    result = VrpResult(objective_value=int(solution.ObjectiveValue()))
    visited: set[int] = set()

    for vehicle_id in range(total_vehicles):
        index = routing.Start(vehicle_id)
        if routing.IsEnd(solution.Value(routing.NextVar(index))):
            continue  # vehiculo no usado

        stops: list[VrpStop] = []
        travel_min = 0.0
        service_min = 0.0
        distance_km = 0.0
        cumulative_time_min = 0.0

        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            next_index = solution.Value(routing.NextVar(index))
            next_node = manager.IndexToNode(next_index)
            arc_travel = float(time_matrix[node, next_node])
            arc_distance = float(distance_matrix[node, next_node])
            travel_min += arc_travel
            distance_km += arc_distance
            cumulative_time_min += arc_travel

            if next_node != depot_index:
                arc_service = float(residual_service_time[next_node])
                service_min += arc_service
                cumulative_time_min += arc_service
                stops.append(
                    VrpStop(
                        node_index=int(next_node),
                        node_name=names[next_node],
                        packages=int(residual_packages[next_node]),
                        service_time_min=arc_service,
                        arrival_time_min=cumulative_time_min - arc_service,
                    )
                )
                visited.add(int(next_node))
            index = next_index

        if stops:
            result.routes.append(
                VrpRoute(
                    vehicle_id=int(vehicle_id),
                    vehicle_type=fleet.vehicle_type_for(int(vehicle_id)),
                    stops=stops,
                    travel_time_min=travel_min,
                    service_time_min=service_min,
                    travel_distance_km=distance_km,
                )
            )
            result.total_travel_time_min += travel_min
            result.total_service_time_min += service_min
            result.total_distance_km += distance_km

    expected = set(customer_indices)
    missing = sorted(expected - visited)
    result.unassigned_nodes = missing

    return result
