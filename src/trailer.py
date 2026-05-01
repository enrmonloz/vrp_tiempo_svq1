"""Configuracion de trailers para nodos grandes.

Cuando esta activado, las rutas dedicadas hacia los nodos grandes (Cadiz,
Malaga, Cordoba, Huelva) las realizan trailers en lugar de furgonetas. La
diferencia operativa relevante para el modelo:

- El trailer descarga **en bloque** en un hub local del nodo (no entrega
  casa por casa). El tiempo en el nodo es un ``unloading_time_min`` fijo,
  no proporcional al numero de paquetes.
- El trailer tiene una ``packages_capacity`` configurable que limita los
  paquetes por viaje. Si la capacidad es alta y todo cabe en un viaje, el
  numero de rutas dedicadas se reduce drasticamente.
- La jornada maxima del conductor sigue siendo la misma; lo que cambia es
  como se reparte el servicio.

El ultimo viaje del trailer puede tener menos paquetes que la capacidad
porque distribuimos los chunks balanceadamente para igualar carga entre
trailers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


# Nombres exactos (con tilde) tal como aparecen en data/distanciasReales.xlsx.
DEFAULT_BIG_NODES: Tuple[str, ...] = ("Cádiz", "Málaga", "Córdoba", "Huelva", "Granada")


@dataclass(frozen=True)
class TrailerConfig:
    """Configuracion del servicio con trailer.

    Atributos:
        enabled: si False, todas las rutas dedicadas usan furgoneta (como
            antes); si True, los nodos en ``big_nodes`` usan trailer.
        packages_capacity: capacidad maxima de paquetes por viaje del trailer.
        unloading_time_min: tiempo (min) que el trailer pasa en el nodo
            descargando en bloque. No depende del numero de paquetes.
        big_nodes: tupla de nombres de nodos a los que aplica el trailer.
            Por defecto las 4 capitales (Cadiz, Malaga, Cordoba, Huelva).
    """

    enabled: bool = False
    packages_capacity: int = 500
    unloading_time_min: float = 30.0
    big_nodes: Tuple[str, ...] = DEFAULT_BIG_NODES

    def applies_to(self, node_name: str) -> bool:
        return bool(self.enabled) and node_name in self.big_nodes

    def validate(self) -> None:
        if self.packages_capacity <= 0:
            raise ValueError("packages_capacity debe ser positivo")
        if self.unloading_time_min < 0:
            raise ValueError("unloading_time_min no puede ser negativo")
