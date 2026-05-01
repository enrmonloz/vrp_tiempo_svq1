"""Solver de localización de centros de reparto.

Este módulo implementa diferentes técnicas de optimización para localizar
centros de distribución basándose en la población y coordenadas de los municipios.

Técnicas implementadas:
1. Centro de Gravedad Ponderado: Media simple ponderada por población.
2. Minimización de Distancia Total: Minimiza sum(población * distancia) → ubicación óptima según demanda.
3. Minimax: Minimiza la máxima distancia ponderada a cubrir → minimiza el servicio al peor cliente.
4. k-Mediana: Agrupa municipios y selecciona medianas ponderadas.
5. Análisis de múltiples centros: Evalúa ubicaciones alternativas.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize


class LocationMethod(str, Enum):
    """Estrategias de localización disponibles."""

    GRAVITY_CENTER = "gravity_center"
    MIN_TOTAL_DISTANCE = "min_total_distance"
    MINIMAX = "minimax"
    K_MEDIAN = "k_median"
    GEOGRAPHIC_CENTER = "geographic_center"


@dataclass
class LocationResult:
    """Resultado de un cálculo de localización.

    Atributos:
        method: técnica utilizada.
        longitude: coordenada X óptima.
        latitude: coordenada Y óptima.
        weighted_distance: métrica de coste total (significado depende del método).
        max_weighted_distance: distancia máxima ponderada a cualquier nodo.
        nearest_municipality: municipio más cercano a la ubicación óptima.
        distance_to_nearest_km: distancia en km al municipio más cercano.
        objective_value: valor de la función objetivo en la solución.
    """

    method: LocationMethod
    longitude: float
    latitude: float
    weighted_distance: float
    max_weighted_distance: float
    nearest_municipality: Optional[str] = None
    distance_to_nearest_km: Optional[float] = None
    objective_value: Optional[float] = None


class LocationSolver:
    """Solver de localización de centros de distribución."""

    def __init__(self, dataset):
        """
        Inicializa el solver con datos de municipios.

        Parámetros:
            dataset: objeto Dataset con nombres, coordenadas, población y matriz de distancias.
        """
        self.dataset = dataset
        self.names = dataset.names
        self.latitudes = dataset.latitudes
        self.longitudes = dataset.longitudes
        self.poblacion = dataset.poblacion
        self.distance_matrix = dataset.distance_matrix

        # Excluir centros logísticos (población=0) del cálculo de demanda
        self.demand_mask = self.poblacion > 0
        self.demand_indices = np.where(self.demand_mask)[0]

    def solve(self, method: LocationMethod = LocationMethod.MIN_TOTAL_DISTANCE) -> LocationResult:
        """Resuelve el problema de localización usando la técnica especificada.

        Parámetros:
            method: técnica de localización a utilizar.

        Retorna:
            LocationResult con la ubicación óptima y métricas asociadas.
        """
        if method == LocationMethod.GRAVITY_CENTER:
            return self._solve_gravity_center()
        elif method == LocationMethod.MIN_TOTAL_DISTANCE:
            return self._solve_min_total_distance()
        elif method == LocationMethod.MINIMAX:
            return self._solve_minimax()
        elif method == LocationMethod.GEOGRAPHIC_CENTER:
            return self._solve_geographic_center()
        elif method == LocationMethod.K_MEDIAN:
            return self._solve_k_median()
        else:
            raise ValueError(f"Método desconocido: {method}")

    def _solve_gravity_center(self) -> LocationResult:
        """Centro de gravedad ponderado por población."""
        demand_nodes = self.demand_indices
        weights = self.poblacion[demand_nodes]
        lats = self.latitudes[demand_nodes]
        lons = self.longitudes[demand_nodes]

        lat_optimal = np.sum(weights * lats) / np.sum(weights)
        lon_optimal = np.sum(weights * lons) / np.sum(weights)

        # Calcular métricas
        distances = self._calculate_distances_from_point(lon_optimal, lat_optimal)
        weighted_dist = np.sum(weights * distances[demand_nodes])
        max_weighted_dist = np.max(weights * distances[demand_nodes])

        nearest_idx = self._find_nearest_municipality(lon_optimal, lat_optimal)

        return LocationResult(
            method=LocationMethod.GRAVITY_CENTER,
            longitude=lon_optimal,
            latitude=lat_optimal,
            weighted_distance=weighted_dist,
            max_weighted_distance=max_weighted_dist,
            nearest_municipality=self.names[nearest_idx],
            distance_to_nearest_km=distances[nearest_idx],
            objective_value=weighted_dist,
        )

    def _solve_min_total_distance(self) -> LocationResult:
        """Minimiza la suma ponderada de distancias: sum(población * distancia)."""
        demand_nodes = self.demand_indices
        weights = self.poblacion[demand_nodes]
        lats = self.latitudes[demand_nodes]
        lons = self.longitudes[demand_nodes]

        # Punto inicial: centro de gravedad
        x0 = np.array([
            np.sum(weights * lons) / np.sum(weights),
            np.sum(weights * lats) / np.sum(weights),
        ])

        # Función objetivo
        def objective(xy):
            distances = np.sqrt((xy[0] - lons) ** 2 + (xy[1] - lats) ** 2)
            return np.sum(weights * distances)

        # Usar scipy.optimize.minimize (más robusto que fminunc en MATLAB)
        result = minimize(objective, x0, method="Nelder-Mead", options={"maxiter": 10000})
        lon_optimal, lat_optimal = result.x

        # Calcular métricas finales
        distances = self._calculate_distances_from_point(lon_optimal, lat_optimal)
        weighted_dist = np.sum(weights * distances[demand_nodes])
        max_weighted_dist = np.max(weights * distances[demand_nodes])
        nearest_idx = self._find_nearest_municipality(lon_optimal, lat_optimal)

        return LocationResult(
            method=LocationMethod.MIN_TOTAL_DISTANCE,
            longitude=lon_optimal,
            latitude=lat_optimal,
            weighted_distance=weighted_dist,
            max_weighted_distance=max_weighted_dist,
            nearest_municipality=self.names[nearest_idx],
            distance_to_nearest_km=distances[nearest_idx],
            objective_value=result.fun,
        )

    def _solve_minimax(self) -> LocationResult:
        """Minimax: Minimiza la máxima distancia ponderada.

        Objetivo: Minimizar el servicio al cliente peor servido (equidad).
        """
        demand_nodes = self.demand_indices
        weights = self.poblacion[demand_nodes]
        lats = self.latitudes[demand_nodes]
        lons = self.longitudes[demand_nodes]

        # Punto inicial
        x0 = np.array([
            np.sum(weights * lons) / np.sum(weights),
            np.sum(weights * lats) / np.sum(weights),
        ])

        # Función objetivo: vector de distancias ponderadas
        def objective_vector(xy):
            distances = np.sqrt((xy[0] - lons) ** 2 + (xy[1] - lats) ** 2)
            return weights * distances

        # Minimizar el máximo valor (minimax)
        def objective_max(xy):
            return np.max(objective_vector(xy))

        result = minimize(objective_max, x0, method="Nelder-Mead", options={"maxiter": 10000})
        lon_optimal, lat_optimal = result.x

        # Calcular métricas
        distances = self._calculate_distances_from_point(lon_optimal, lat_optimal)
        weighted_dist = np.sum(weights * distances[demand_nodes])
        max_weighted_dist = np.max(weights * distances[demand_nodes])
        nearest_idx = self._find_nearest_municipality(lon_optimal, lat_optimal)

        return LocationResult(
            method=LocationMethod.MINIMAX,
            longitude=lon_optimal,
            latitude=lat_optimal,
            weighted_distance=weighted_dist,
            max_weighted_distance=max_weighted_dist,
            nearest_municipality=self.names[nearest_idx],
            distance_to_nearest_km=distances[nearest_idx],
            objective_value=result.fun,
        )

    def _solve_geographic_center(self) -> LocationResult:
        """Centro geográfico simple (sin ponderación por población)."""
        demand_nodes = self.demand_indices
        weights = self.poblacion[demand_nodes]
        lats = self.latitudes[demand_nodes]
        lons = self.longitudes[demand_nodes]

        # Centro geográfico simple
        lat_optimal = np.mean(lats)
        lon_optimal = np.mean(lons)

        # Calcular métricas
        distances = self._calculate_distances_from_point(lon_optimal, lat_optimal)
        weighted_dist = np.sum(weights * distances[demand_nodes])
        max_weighted_dist = np.max(weights * distances[demand_nodes])
        nearest_idx = self._find_nearest_municipality(lon_optimal, lat_optimal)

        return LocationResult(
            method=LocationMethod.GEOGRAPHIC_CENTER,
            longitude=lon_optimal,
            latitude=lat_optimal,
            weighted_distance=weighted_dist,
            max_weighted_distance=max_weighted_dist,
            nearest_municipality=self.names[nearest_idx],
            distance_to_nearest_km=distances[nearest_idx],
            objective_value=weighted_dist,
        )

    def _solve_k_median(self, k: int = 1) -> LocationResult:
        """k-mediana: encuentra k ubicaciones óptimas (para k=1, es la mediana ponderada).

        Para k=1, es equivalente a encontrar la "mediana" que minimiza distancias.
        Aquí usamos k-means para agrupar y luego la mediana de cada grupo.
        """
        if k == 1:
            # Para k=1, usar min_total_distance
            return self._solve_min_total_distance()

        # Para k > 1, usar clustering simple k-means
        demand_nodes = self.demand_indices
        lats = self.latitudes[demand_nodes]
        lons = self.longitudes[demand_nodes]
        weights = self.poblacion[demand_nodes]

        # Datos de entrada para clustering
        X = np.column_stack([lons, lats])

        # K-means simple iterativo
        from sklearn.cluster import KMeans

        try:
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(X)

            # Encontrar la mediana ponderada de cada cluster
            centroids = []
            for i in range(k):
                cluster_mask = labels == i
                cluster_lons = lons[cluster_mask]
                cluster_lats = lats[cluster_mask]
                cluster_weights = weights[cluster_mask]

                # Mediana ponderada (usamos media como aproximación)
                lon_median = np.average(cluster_lons, weights=cluster_weights)
                lat_median = np.average(cluster_lats, weights=cluster_weights)
                centroids.append((lon_median, lat_median))

            # Para k > 1, retornar el centroide del cluster más grande
            largest_cluster = np.argmax(np.bincount(labels))
            lon_optimal, lat_optimal = centroids[largest_cluster]

        except ImportError:
            # Fallback si sklearn no está disponible
            return self._solve_min_total_distance()

        # Calcular métricas
        distances = self._calculate_distances_from_point(lon_optimal, lat_optimal)
        weighted_dist = np.sum(weights * distances[demand_nodes])
        max_weighted_dist = np.max(weights * distances[demand_nodes])
        nearest_idx = self._find_nearest_municipality(lon_optimal, lat_optimal)

        return LocationResult(
            method=LocationMethod.K_MEDIAN,
            longitude=lon_optimal,
            latitude=lat_optimal,
            weighted_distance=weighted_dist,
            max_weighted_distance=max_weighted_dist,
            nearest_municipality=self.names[nearest_idx],
            distance_to_nearest_km=distances[nearest_idx],
            objective_value=weighted_dist,
        )

    def _calculate_distances_from_point(
        self, longitude: float, latitude: float
    ) -> np.ndarray:
        """Calcula distancia en km (Haversine) entre un punto y todos los nodos."""
        # Aproximación rápida: asumir que los datos están en un plano pequeño
        # (provincia de Sevilla). Para mayor precisión, usar Haversine.
        R = 6371  # Radio de la Tierra en km

        lat1_rad = np.radians(latitude)
        lon1_rad = np.radians(longitude)
        lat2_rad = np.radians(self.latitudes)
        lon2_rad = np.radians(self.longitudes)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
        c = 2 * np.arcsin(np.sqrt(a))
        distances = R * c

        return distances

    def _find_nearest_municipality(
        self, longitude: float, latitude: float
    ) -> int:
        """Encuentra el municipio más cercano a una ubicación."""
        distances = self._calculate_distances_from_point(longitude, latitude)
        return np.argmin(distances)

    def get_all_solutions(self) -> dict:
        """Ejecuta todos los métodos y retorna un diccionario con los resultados."""
        solutions = {}
        for method in LocationMethod:
            solutions[method.value] = self.solve(method)
        return solutions

    def compare_solutions(self) -> pd.DataFrame:
        """Compara todas las soluciones en un DataFrame.

        Retorna:
            DataFrame con un fila por método, columnas con métricas clave.
        """
        solutions = self.get_all_solutions()

        rows = []
        for method_name, result in solutions.items():
            rows.append(
                {
                    "Método": method_name.replace("_", " ").title(),
                    "Latitud": result.latitude,
                    "Longitud": result.longitude,
                    "Dist. Total Ponderada": f"{result.weighted_distance:,.1f}",
                    "Dist. Máxima Pond.": f"{result.max_weighted_distance:,.1f}",
                    "Municipio Más Cercano": result.nearest_municipality,
                    "Distancia al Municipio (km)": f"{result.distance_to_nearest_km:.2f}",
                }
            )

        return pd.DataFrame(rows)
