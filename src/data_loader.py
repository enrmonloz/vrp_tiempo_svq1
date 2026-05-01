"""Carga y validacion de datos para VRP por tiempo SVQ1.

Este modulo carga y valida los datos desde dos fuentes CSV sincronizadas:

- ``poblacion.csv``: lista de municipios con poblacion y coordenadas (122 nodos: SVQ1, DQA4, 120 municipios/provincias).
- ``rutasDistTiempo.csv``: matriz OD completa con distancia (km) y tiempo (min) para los 122 nodos.

Ambos archivos estan sincronizados y tienen el mismo numero de filas de datos (122 nodos,
sin contar la cabecera).

El resultado de :func:`load_dataset` es una :class:`Dataset` con todo lo que
necesita el solver: nombres, coordenadas, restricciones, poblacion y dos
matrices NxN (distancia y tiempo) ya alineadas y consistentes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

# Nombres de los nodos especiales (deposito y centro logistico secundario).
DEPOT_NAME = "SVQ1"
SECONDARY_HUB_NAME = "DQA4"


@dataclass(frozen=True)
class Dataset:
    """Estructura de datos lista para el solver.

    Atributos:
        names: nombre de cada nodo, alineado con los indices 0..N-1.
        latitudes / longitudes: coordenadas geograficas de cada nodo.
        restringe_camion: 1 si el nodo restringe acceso a camion, 0 si no.
        poblacion: habitantes por nodo.
        distance_matrix: matriz NxN en km.
        time_matrix: matriz NxN en minutos.
        depot_index: indice del deposito (SVQ1).
    """

    names: List[str]
    latitudes: np.ndarray
    longitudes: np.ndarray
    restringe_camion: np.ndarray
    poblacion: np.ndarray
    distance_matrix: np.ndarray
    time_matrix: np.ndarray
    depot_index: int

    @property
    def n_nodes(self) -> int:
        return len(self.names)


def _read_poblacion(path: Path) -> pd.DataFrame:
    """Lee poblacion.csv tolerando BOM y separador ';'."""
    if not path.exists():
        raise FileNotFoundError(f"No se encuentra el archivo de poblacion: {path}")

    df = pd.read_csv(path, sep=";", encoding="utf-8-sig")
    expected_cols = {"Municipio", "Población", "Latitud (Y)", "Longitud (X)", "Restringe camion"}
    missing = expected_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"Faltan columnas en poblacion.csv: {sorted(missing)}. "
            f"Encontradas: {df.columns.tolist()}"
        )

    df = df.copy()
    df["Municipio"] = df["Municipio"].astype(str).str.strip()
    df["Población"] = pd.to_numeric(df["Población"], errors="coerce").fillna(0).astype(int)
    df["Latitud (Y)"] = pd.to_numeric(df["Latitud (Y)"], errors="coerce")
    df["Longitud (X)"] = pd.to_numeric(df["Longitud (X)"], errors="coerce")
    df["Restringe camion"] = pd.to_numeric(df["Restringe camion"], errors="coerce").fillna(0).astype(int)

    if df[["Latitud (Y)", "Longitud (X)"]].isna().any().any():
        bad = df[df[["Latitud (Y)", "Longitud (X)"]].isna().any(axis=1)]["Municipio"].tolist()
        raise ValueError(f"Coordenadas invalidas en poblacion.csv para: {bad}")

    return df.reset_index(drop=True)


def _read_routes(path: Path, n_expected: int) -> Tuple[np.ndarray, np.ndarray]:
    """Lee rutasDistTiempo.csv y devuelve (dist_matrix, time_matrix) NxN.

    El CSV tiene formato largo (origen_id, destino_id, distancia_km, tiempo_min).
    Se valida que la matriz este completa para los IDs 0..n_expected-1.
    """
    if not path.exists():
        raise FileNotFoundError(f"No se encuentra el archivo de rutas: {path}")

    df = pd.read_csv(path, encoding="utf-8-sig")
    expected_cols = {"origen_id", "destino_id", "distancia_km", "tiempo_min"}
    missing = expected_cols - set(df.columns)
    if missing:
        raise ValueError(
            f"Faltan columnas en rutasDistTiempo.csv: {sorted(missing)}. "
            f"Encontradas: {df.columns.tolist()}"
        )

    df = df.copy()
    for col in ("origen_id", "destino_id"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ("distancia_km", "tiempo_min"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df[["origen_id", "destino_id", "distancia_km", "tiempo_min"]].isna().any().any():
        raise ValueError("Hay valores no numericos o nulos en rutasDistTiempo.csv")

    if (df["distancia_km"] < 0).any() or (df["tiempo_min"] < 0).any():
        raise ValueError("Hay distancias o tiempos negativos en rutasDistTiempo.csv")

    ids = pd.unique(pd.concat([df["origen_id"], df["destino_id"]]))
    if int(ids.min()) != 0 or int(ids.max()) != n_expected - 1:
        raise ValueError(
            f"IDs fuera de rango en rutasDistTiempo.csv. Esperado 0..{n_expected - 1}, "
            f"encontrado {int(ids.min())}..{int(ids.max())}"
        )

    expected_pairs = n_expected * n_expected
    if len(df) != expected_pairs:
        raise ValueError(
            f"La matriz OD de rutasDistTiempo.csv esta incompleta. "
            f"Esperado {expected_pairs} pares, encontrado {len(df)}"
        )

    dist = np.zeros((n_expected, n_expected), dtype=float)
    tim = np.zeros((n_expected, n_expected), dtype=float)
    for o, d, km, mn in df[["origen_id", "destino_id", "distancia_km", "tiempo_min"]].itertuples(index=False):
        dist[int(o), int(d)] = float(km)
        tim[int(o), int(d)] = float(mn)

    return dist, tim


def load_dataset(
    poblacion_path: str | Path = "data/poblacion.csv",
    rutas_path: str | Path = "data/rutasDistTiempo.csv",
) -> Dataset:
    """Carga y valida todos los datos desde los CSVs sincronizados.
    
    Espera que poblacion.csv y rutasDistTiempo.csv tengan el mismo numero de
    nodos (122) en el mismo orden.
    """
    poblacion_path = Path(poblacion_path)
    rutas_path = Path(rutas_path)

    pob_df = _read_poblacion(poblacion_path)
    n_pob = len(pob_df)

    csv_dist, csv_time = _read_routes(rutas_path, n_expected=n_pob)

    # Construir vectores alineados con nombres de poblacion.csv.
    names = pob_df["Municipio"].tolist()
    latitudes = pob_df["Latitud (Y)"].to_numpy(dtype=float)
    longitudes = pob_df["Longitud (X)"].to_numpy(dtype=float)
    restringe = pob_df["Restringe camion"].to_numpy(dtype=int)
    poblacion = pob_df["Población"].to_numpy(dtype=int)

    if DEPOT_NAME not in names:
        raise ValueError(f"No se encontro el deposito '{DEPOT_NAME}' en los datos cargados")
    depot_index = names.index(DEPOT_NAME)

    return Dataset(
        names=names,
        latitudes=latitudes,
        longitudes=longitudes,
        restringe_camion=restringe,
        poblacion=poblacion,
        distance_matrix=csv_dist,
        time_matrix=csv_time,
        depot_index=depot_index,
    )
