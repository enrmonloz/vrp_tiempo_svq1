"""Configuracion de flota heterogenea (diesel + electrica).

Basado en los datos de DQA4 del enunciado: 120 vehiculos repartidos en diesel
y electrico. La furgoneta electrica tiene un rango maximo por jornada (sin
recargas) que la diesel no tiene; en cambio, su uso es preferible por motivos
operativos y de sostenibilidad.

El solver decide la combinacion optima de vehiculos a usar dentro de las
cotas configuradas. Para preferir electricos cuando caben, su coste fijo es
ligeramente menor que el del diesel; el coste fijo total (alto) sigue
penalizando fuertemente cada vehiculo activo, por lo que el numero total de
vehiculos sigue siendo el criterio principal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VehicleType(str, Enum):
    DIESEL = "diesel"
    ELECTRIC = "electric"


@dataclass(frozen=True)
class FleetConfig:
    """Cotas de flota y caracteristicas tecnicas.

    Atributos:
        max_diesel: cota maxima de furgonetas diesel disponibles.
        max_electric: cota maxima de furgonetas electricas disponibles.
        electric_max_range_km: rango maximo (km) que una electrica puede
            recorrer en una sola jornada sin recargar. Las diesel no tienen
            restriccion (mas alla de la jornada).
        diesel_fixed_cost: coste fijo en la funcion objetivo por cada diesel
            usada. Hace que el solver minimice numero de vehiculos.
        electric_fixed_cost: coste fijo por cada electrica usada. Si es
            menor que el de la diesel, el solver prefiere electricas cuando
            caben.
    """

    max_diesel: int = 75
    max_electric: int = 45
    electric_max_range_km: float = 180.0
    diesel_fixed_cost: int = 1_050_000
    electric_fixed_cost: int = 1_000_000

    @property
    def total_capacity(self) -> int:
        return int(self.max_diesel) + int(self.max_electric)

    def validate(self) -> None:
        if self.max_diesel < 0 or self.max_electric < 0:
            raise ValueError("Las cotas de flota no pueden ser negativas")
        if self.total_capacity <= 0:
            raise ValueError("Debe haber al menos un vehiculo disponible")
        if self.electric_max_range_km <= 0:
            raise ValueError("El rango electrico debe ser positivo")
        if self.diesel_fixed_cost < 0 or self.electric_fixed_cost < 0:
            raise ValueError("Los costes fijos no pueden ser negativos")

    def vehicle_type_for(self, vehicle_id: int) -> VehicleType:
        """Devuelve el tipo asociado a un vehicle_id.

        Convencion: los primeros ``max_diesel`` ids son diesel; los siguientes
        son electricos.
        """
        if vehicle_id < 0 or vehicle_id >= self.total_capacity:
            raise IndexError(f"vehicle_id {vehicle_id} fuera de rango")
        return VehicleType.DIESEL if vehicle_id < self.max_diesel else VehicleType.ELECTRIC
