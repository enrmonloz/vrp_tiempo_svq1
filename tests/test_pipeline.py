"""Smoke tests sin dependencia de OR-Tools.

Verifica:
- Carga del dataset (121 nodos, deposito en SVQ1).
- Calculo de paquetes y tiempos de servicio.
- Split delivery por tiempo: nodos grandes generan rutas dedicadas.
- Validaciones basicas de input.

Uso: ``python tests/test_pipeline.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data_loader import load_dataset
from src.demand import DemandConfig, compute_node_service_time, compute_packages
from src.split_delivery import split_oversized_nodes


DATA_DIR = ROOT / "data"


def assert_eq(actual, expected, msg: str) -> None:
    if actual != expected:
        raise AssertionError(f"{msg}: esperado {expected}, obtenido {actual}")
    print(f"  OK {msg}")


def test_dataset_loads() -> None:
    print("test_dataset_loads")
    ds = load_dataset(
        poblacion_path=str(DATA_DIR / "poblacion.csv"),
        rutas_path=str(DATA_DIR / "rutasDistTiempo.csv"),
    )
    assert_eq(ds.n_nodes, 122, "Numero total de nodos")
    assert_eq(ds.names[ds.depot_index], "SVQ1", "Deposito")
    assert_eq(ds.distance_matrix.shape, (122, 122), "Forma matriz distancia")
    assert_eq(ds.time_matrix.shape, (122, 122), "Forma matriz tiempo")
    for capital_name in ("Cádiz", "Málaga", "Córdoba", "Huelva", "Granada"):
        if capital_name not in ds.names:
            raise AssertionError(f"Falta capital: {capital_name}")
    print("  OK Las capitales estan presentes")


def test_demand_and_split() -> None:
    print("test_demand_and_split")
    ds = load_dataset(
        poblacion_path=str(DATA_DIR / "poblacion.csv"),
        rutas_path=str(DATA_DIR / "rutasDistTiempo.csv"),
    )
    cfg = DemandConfig(
        market_penetration=0.001,
        service_time_per_package_min=2.0,
        inter_package_time_min=1.0,
    )
    pkgs = compute_packages(ds.poblacion, cfg, ds.depot_index)
    if pkgs[ds.depot_index] != 0:
        raise AssertionError("Deposito deberia tener 0 paquetes")
    if pkgs.sum() <= 0:
        raise AssertionError("La demanda total deberia ser > 0")
    print(f"  OK Paquetes totales: {int(pkgs.sum())}")

    service = compute_node_service_time(pkgs, cfg)
    if not np.allclose(service[ds.depot_index], 0.0):
        raise AssertionError("Servicio en deposito deberia ser 0")

    res = split_oversized_nodes(
        names=ds.names,
        packages=pkgs,
        service_time_per_node=service,
        distance_matrix=ds.distance_matrix,
        time_matrix=ds.time_matrix,
        depot_index=ds.depot_index,
        max_workday_min=8 * 60,
        service_time_per_package_min=cfg.service_time_per_package_min,
        inter_package_time_min=cfg.inter_package_time_min,
    )
    if not res.dedicated_routes:
        raise AssertionError("Con 0.1% de penetracion Malaga deberia generar rutas dedicadas")

    # Las rutas dedicadas deben ser para los nodos grandes y/o lejanos.
    big_nodes = {r.node_name for r in res.dedicated_routes}
    for expected in ("Málaga", "Córdoba"):
        if expected not in big_nodes:
            raise AssertionError(f"{expected} deberia aparecer entre las rutas dedicadas")
    print(f"  OK Rutas dedicadas generadas: {len(res.dedicated_routes)}")
    print(f"  OK Nodos con dedicada: {sorted(big_nodes)}")

    # Comprobar que ninguna ruta dedicada excede la jornada.
    for r in res.dedicated_routes:
        if r.total_time_min > 8 * 60 + 1e-6:
            raise AssertionError(
                f"Ruta dedicada de {r.node_name} excede jornada: {r.total_time_min:.1f} min"
            )
    print("  OK Ninguna ruta dedicada supera la jornada maxima")


def main() -> None:
    test_dataset_loads()
    test_demand_and_split()
    print("\nTodos los tests OK")


if __name__ == "__main__":
    main()
