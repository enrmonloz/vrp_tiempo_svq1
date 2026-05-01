"""Pipeline: union de carga + demanda + split + solver en una sola llamada.

La idea es que la app de Streamlit y los tests llamen a una unica funcion que
orquesta todas las fases. Asi es facil cambiar el modelo internamente sin
tocar la UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .data_loader import Dataset
from .demand import DemandConfig, compute_node_service_time, compute_packages
from .fleet import FleetConfig
from .schedule import (
    RouteSchedule,
    ScheduleConfig,
    schedule_dedicated_route,
    schedule_vrp_route,
)
from .split_delivery import SplitDeliveryResult, split_oversized_nodes
from .trailer import TrailerConfig
from .vrp_solver import SolverStrategy, VrpResult, solve_vrp_by_time


@dataclass
class PipelineConfig:
    """Parametros de toda la corrida."""

    market_penetration: float
    max_workday_hours: float
    service_time_per_package_min: float
    inter_package_time_min: float
    fleet: FleetConfig = field(default_factory=FleetConfig)
    trailer: TrailerConfig = field(default_factory=TrailerConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    solver_strategy: SolverStrategy = SolverStrategy.INSERTION
    solver_time_limit_seconds: int = 30

    @property
    def max_workday_min(self) -> float:
        return float(self.max_workday_hours) * 60.0

    def to_demand_config(self) -> DemandConfig:
        return DemandConfig(
            market_penetration=self.market_penetration,
            service_time_per_package_min=self.service_time_per_package_min,
            inter_package_time_min=self.inter_package_time_min,
        )


@dataclass
class PipelineResult:
    """Resultado completo del pipeline."""

    dataset: Dataset
    packages: np.ndarray
    service_time: np.ndarray
    split: SplitDeliveryResult
    vrp: VrpResult
    config: PipelineConfig
    vrp_schedules: list[RouteSchedule] = field(default_factory=list)
    dedicated_schedules: list[RouteSchedule] = field(default_factory=list)

    @property
    def dedicated_route_count(self) -> int:
        return len(self.split.dedicated_routes)

    @property
    def trailer_route_count(self) -> int:
        return sum(1 for r in self.split.dedicated_routes if r.vehicle_type == "trailer")

    @property
    def van_dedicated_route_count(self) -> int:
        return sum(1 for r in self.split.dedicated_routes if r.vehicle_type == "furgoneta")

    @property
    def vrp_route_count(self) -> int:
        return self.vrp.vehicle_count

    @property
    def total_routes(self) -> int:
        return self.dedicated_route_count + self.vrp_route_count

    @property
    def total_time_min(self) -> float:
        dedicated_time = sum(r.total_time_min for r in self.split.dedicated_routes)
        return float(dedicated_time + self.vrp.total_time_min)

    @property
    def total_distance_km(self) -> float:
        dedicated_dist = sum(r.travel_distance_km for r in self.split.dedicated_routes)
        return float(dedicated_dist + self.vrp.total_distance_km)


def run_pipeline(dataset: Dataset, config: PipelineConfig) -> PipelineResult:
    """Ejecuta el pipeline entero sobre un dataset ya cargado."""
    demand_cfg = config.to_demand_config()
    packages = compute_packages(dataset.poblacion, demand_cfg, dataset.depot_index)
    service_time = compute_node_service_time(packages, demand_cfg)

    split_result = split_oversized_nodes(
        names=dataset.names,
        packages=packages,
        service_time_per_node=service_time,
        distance_matrix=dataset.distance_matrix,
        time_matrix=dataset.time_matrix,
        depot_index=dataset.depot_index,
        max_workday_min=config.max_workday_min,
        service_time_per_package_min=config.service_time_per_package_min,
        inter_package_time_min=config.inter_package_time_min,
        trailer=config.trailer,
    )

    vrp_result = solve_vrp_by_time(
        names=dataset.names,
        distance_matrix=dataset.distance_matrix,
        time_matrix=dataset.time_matrix,
        residual_packages=split_result.residual_packages,
        residual_service_time=split_result.residual_service_time,
        depot_index=dataset.depot_index,
        max_workday_min=config.max_workday_min,
        fleet=config.fleet,
        strategy=config.solver_strategy,
        time_limit_seconds=config.solver_time_limit_seconds,
        latitudes=dataset.latitudes,
        longitudes=dataset.longitudes,
    )

    vrp_schedules = [schedule_vrp_route(r, config.schedule) for r in vrp_result.routes]
    dedicated_schedules = [
        schedule_dedicated_route(r, config.schedule) for r in split_result.dedicated_routes
    ]

    return PipelineResult(
        dataset=dataset,
        packages=packages,
        service_time=service_time,
        split=split_result,
        vrp=vrp_result,
        config=config,
        vrp_schedules=vrp_schedules,
        dedicated_schedules=dedicated_schedules,
    )
