"""Calculo de demanda (paquetes) y tiempo nodal por municipio.

A partir de la poblacion y unos parametros de usuario (penetracion de mercado,
tiempo de servicio por paquete y tiempo medio de conduccion entre paquetes
dentro del municipio) se obtiene:

- ``packages_per_node``: paquetes a entregar en cada nodo (entero).
- ``service_time_per_node``: minutos totales que se gastan dentro del nodo
  para entregar todos sus paquetes.

El deposito siempre tiene 0 paquetes y 0 tiempo de servicio.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DemandConfig:
    """Parametros de usuario para el calculo de demanda.

    - ``market_penetration``: fraccion de la poblacion que recibe paquete (0..1).
    - ``service_time_per_package_min``: minutos por paquete (entrega).
    - ``inter_package_time_min``: minutos medios de conduccion entre paquetes
      dentro del mismo municipio.
    """

    market_penetration: float
    service_time_per_package_min: float
    inter_package_time_min: float

    def validate(self) -> None:
        if not (0.0 <= self.market_penetration <= 1.0):
            raise ValueError("market_penetration debe estar en [0, 1]")
        if self.service_time_per_package_min < 0:
            raise ValueError("service_time_per_package_min no puede ser negativo")
        if self.inter_package_time_min < 0:
            raise ValueError("inter_package_time_min no puede ser negativo")


def compute_packages(poblacion: np.ndarray, config: DemandConfig, depot_index: int) -> np.ndarray:
    """Devuelve un vector entero de paquetes por nodo.

    El deposito tiene 0 paquetes. El resto se calcula como round(pop * pen).
    """
    config.validate()
    pkgs = np.rint(np.asarray(poblacion, dtype=float) * float(config.market_penetration)).astype(int)
    pkgs = np.maximum(pkgs, 0)
    if 0 <= depot_index < len(pkgs):
        pkgs[depot_index] = 0
    return pkgs


def compute_node_service_time(packages: np.ndarray, config: DemandConfig) -> np.ndarray:
    """Tiempo (min) que cuesta servir todos los paquetes de cada nodo.

    Modelo simple: cada paquete suma ``service_time_per_package_min`` y
    ``inter_package_time_min``. El deposito siempre tiene 0.
    """
    config.validate()
    per_pkg = float(config.service_time_per_package_min) + float(config.inter_package_time_min)
    return np.asarray(packages, dtype=float) * per_pkg
