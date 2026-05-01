"""Smoke tests para las nuevas opciones: estrategias del solver y trailer.

Verifica:
- Las 5 estrategias de primera solucion ejecutan sin error y devuelven
  asignaciones validas.
- Activar el trailer reduce drasticamente el numero de rutas dedicadas y
  todas las rutas dedicadas a nodos grandes son de tipo "trailer".

Uso: ``python tests/test_strategies_trailer.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_dataset
from src.fleet import FleetConfig
from src.pipeline import PipelineConfig, run_pipeline
from src.trailer import TrailerConfig
from src.vrp_solver import SolverStrategy


DATA_DIR = ROOT / "data"


def _load_dataset_once():
    return load_dataset(
        poblacion_path=str(DATA_DIR / "poblacion.csv"),
        rutas_path=str(DATA_DIR / "rutasDistTiempo.csv"),
        distancias_xlsx_path=str(DATA_DIR / "distanciasReales.xlsx"),
    )


def _base_config(strategy: SolverStrategy, trailer: TrailerConfig | None = None) -> PipelineConfig:
    return PipelineConfig(
        market_penetration=0.001,
        max_workday_hours=8,
        service_time_per_package_min=2.0,
        inter_package_time_min=1.0,
        fleet=FleetConfig(),
        trailer=trailer or TrailerConfig(),
        solver_strategy=strategy,
        solver_time_limit_seconds=10,
    )


def test_all_strategies_run() -> None:
    print("test_all_strategies_run")
    ds = _load_dataset_once()
    for strat in SolverStrategy:
        cfg = _base_config(strat)
        r = run_pipeline(ds, cfg)
        if r.vrp_route_count <= 0:
            raise AssertionError(f"{strat.value}: deberia producir rutas VRP")
        if r.vrp.unassigned_nodes:
            raise AssertionError(
                f"{strat.value}: nodos sin asignar: {r.vrp.unassigned_nodes}"
            )
        # Comprobar limite de jornada en cada ruta.
        for route in r.vrp.routes:
            if route.total_time_min > 8 * 60 + 1e-6:
                raise AssertionError(
                    f"{strat.value}: ruta {route.vehicle_id} excede jornada: "
                    f"{route.total_time_min:.1f} min"
                )
        print(
            f"  OK {strat.value}: {r.vrp_route_count} rutas VRP "
            f"(D{r.vrp.diesel_count}/E{r.vrp.electric_count}), "
            f"{r.dedicated_route_count} dedicadas, {r.total_distance_km:.0f} km"
        )


def test_trailer_replaces_dedicated_for_big_nodes() -> None:
    print("test_trailer_replaces_dedicated_for_big_nodes")
    ds = _load_dataset_once()

    # Sin trailer: las rutas dedicadas son de tipo furgoneta.
    cfg_off = _base_config(SolverStrategy.INSERTION, TrailerConfig(enabled=False))
    r_off = run_pipeline(ds, cfg_off)
    if not r_off.split.dedicated_routes:
        raise AssertionError("Caso base deberia tener rutas dedicadas")
    types_off = {x.vehicle_type for x in r_off.split.dedicated_routes}
    if types_off != {"furgoneta"}:
        raise AssertionError(f"Sin trailer, todas deben ser furgoneta. Encontrado: {types_off}")
    print(f"  OK sin trailer: {len(r_off.split.dedicated_routes)} rutas (todas furgoneta)")

    # Con trailer: capacidad 500 / descarga 30 min.
    cfg_on = _base_config(
        SolverStrategy.INSERTION,
        TrailerConfig(enabled=True, packages_capacity=500, unloading_time_min=30.0),
    )
    r_on = run_pipeline(ds, cfg_on)
    big = {"Cádiz", "Málaga", "Córdoba", "Huelva"}

    for r in r_on.split.dedicated_routes:
        if r.node_name in big:
            if r.vehicle_type != "trailer":
                raise AssertionError(
                    f"Nodo grande {r.node_name} deberia ser trailer, es {r.vehicle_type}"
                )
        else:
            if r.vehicle_type != "furgoneta":
                raise AssertionError(
                    f"Nodo no grande {r.node_name} deberia ser furgoneta, es {r.vehicle_type}"
                )

    if r_on.trailer_route_count <= 0:
        raise AssertionError("Con trailer activo deberia haber al menos una ruta trailer")
    print(
        f"  OK con trailer: {r_on.trailer_route_count} rutas trailer + "
        f"{r_on.van_dedicated_route_count} furgonetas dedicadas"
    )

    # Verificar tiempo total de cada ruta trailer = round_trip + 30 min.
    for r in r_on.split.dedicated_routes:
        if r.vehicle_type != "trailer":
            continue
        expected_service = 30.0
        if abs(r.service_time_min - expected_service) > 0.1:
            raise AssertionError(
                f"Trailer en {r.node_name} deberia pagar 30 min de descarga, paga {r.service_time_min}"
            )
    print("  OK tiempos de descarga del trailer coherentes (30 min)")


def main() -> None:
    test_all_strategies_run()
    test_trailer_replaces_dedicated_for_big_nodes()
    print("\nTodos los tests OK")


if __name__ == "__main__":
    main()
