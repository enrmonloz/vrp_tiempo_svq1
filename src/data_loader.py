"""Carga y validacion de datos para VRP por tiempo SVQ1.

Este modulo unifica las tres fuentes de datos del proyecto:

- ``poblacion.csv``: lista de municipios con poblacion y coordenadas (IDs 0..116).
- ``rutasDistTiempo.csv``: matriz OD completa con distancia (km) y tiempo (min)
  para los 117 nodos originales.
- ``distanciasReales.xlsx``: matriz de distancias 121x121 que ANADE 4 nuevos
  nodos al final (Cadiz, Malaga, Cordoba, Huelva) sin tiempos.

Para los 4 nodos nuevos se estima el tiempo a partir de la distancia usando
la velocidad media calculada sobre los pares cuyo tiempo si conocemos. La
poblacion de los nodos nuevos se rellena con valores INE de referencia, pero
se exponen en ``DEFAULT_NEW_NODE_POPULATIONS`` por si se quieren ajustar.

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


# Poblaciones por defecto para los nuevos nodos. Se usan los valores
# provinciales (no solo capital) porque la furgoneta dedicada/trailer atiende
# toda el area de influencia. El usuario puede sobreescribirlos en
# :func:`load_dataset` o desde la UI.
DEFAULT_NEW_NODE_POPULATIONS: Dict[str, int] = {
    "Cádiz": 1_258_881,
    "Málaga": 1_778_275,
    "Córdoba": 770_952,
    "Huelva": 535_836,
}

# Nodos esperados al final del XLSX (en este orden). Si el archivo cambia,
# la validacion lanza un error claro.
EXPECTED_NEW_NODES: Tuple[str, ...] = ("Cádiz", "Málaga", "Córdoba", "Huelva")

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


def _read_distance_xlsx(path: Path) -> Tuple[List[str], np.ndarray]:
    """Lee distanciasReales.xlsx y devuelve (labels, matrix MxM)."""
    if not path.exists():
        raise FileNotFoundError(f"No se encuentra el archivo XLSX: {path}")

    df = pd.read_excel(path, sheet_name="Matriz_Distancias")
    if df.shape[0] + 1 != df.shape[1]:
        raise ValueError(
            f"La matriz del XLSX no es cuadrada (forma {df.shape}). "
            "Se espera la primera columna con etiquetas y el resto con distancias."
        )

    label_col = df.columns[0]
    row_labels = df[label_col].astype(str).str.strip().tolist()
    col_labels = [str(c).strip() for c in df.columns[1:]]

    if row_labels != col_labels:
        raise ValueError("Las etiquetas de filas y columnas del XLSX no coinciden")

    matrix = df.iloc[:, 1:].to_numpy(dtype=float)
    if (matrix < 0).any():
        raise ValueError("Hay distancias negativas en la matriz del XLSX")

    return row_labels, matrix


def _build_unified_matrices(
    poblacion_names: List[str],
    csv_dist: np.ndarray,
    csv_time: np.ndarray,
    xlsx_labels: List[str],
    xlsx_dist: np.ndarray,
) -> Tuple[List[str], np.ndarray, np.ndarray, List[int]]:
    """Une la matriz CSV (NxN con tiempos) con los nuevos nodos del XLSX.

    Estrategia:
    1. Mantener los primeros len(poblacion_names) nodos en el orden del CSV de
       poblacion (que coincide con los IDs 0..N-1 del CSV de rutas).
    2. Anadir al final los nodos del XLSX que NO estan en poblacion (los nuevos:
       Cadiz, Malaga, Cordoba, Huelva).
    3. Para los pares (existente, nuevo) y (nuevo, nuevo), tomar la distancia
       del XLSX y estimar el tiempo a partir de la velocidad media derivada de
       los pares conocidos (CSV) por rango de distancia.
    """
    n_old = len(poblacion_names)
    new_nodes = [name for name in xlsx_labels if name not in poblacion_names]

    if not new_nodes:
        # Nada que anadir: devolver matrices originales tal cual.
        return list(poblacion_names), csv_dist.copy(), csv_time.copy(), []

    for name in EXPECTED_NEW_NODES:
        if name not in new_nodes:
            raise ValueError(
                f"El nodo nuevo esperado '{name}' no aparece en el XLSX. "
                f"Encontrados: {new_nodes}"
            )

    # Calcular velocidad media a partir del CSV (km/h), por bandas de distancia.
    # Esto da una estimacion mas realista que un unico promedio: las distancias
    # cortas son urbanas y las largas son autovia.
    dist_flat = csv_dist[csv_dist > 0]
    time_flat = csv_time[csv_dist > 0]
    speeds = dist_flat / (time_flat / 60.0)  # km/h
    speed_long = float(np.median(speeds[dist_flat > 50])) if (dist_flat > 50).any() else 80.0
    # Fallback si no hubiera datos largos.
    if not np.isfinite(speed_long) or speed_long <= 0:
        speed_long = 80.0

    # Construir nombres y mapping al XLSX.
    all_names = list(poblacion_names) + list(new_nodes)
    n_total = len(all_names)
    new_indices = list(range(n_old, n_total))

    name_to_xlsx_idx = {name: idx for idx, name in enumerate(xlsx_labels)}

    dist_full = np.zeros((n_total, n_total), dtype=float)
    time_full = np.zeros((n_total, n_total), dtype=float)

    # Bloque 1: copiar matriz CSV en la esquina superior izquierda.
    dist_full[:n_old, :n_old] = csv_dist
    time_full[:n_old, :n_old] = csv_time

    # Bloque 2: pares que involucran al menos un nodo nuevo. Distancia desde
    # XLSX, tiempo estimado por velocidad media (km/h) considerando que las
    # distancias a estas capitales son largas (>50 km en su mayoria).
    for i in range(n_total):
        for j in range(n_total):
            if i < n_old and j < n_old:
                continue  # ya copiado
            name_i = all_names[i]
            name_j = all_names[j]
            if name_i not in name_to_xlsx_idx or name_j not in name_to_xlsx_idx:
                # Nodo no presente en el XLSX: no hay distancia disponible.
                # Como salvaguarda dejamos ceros y el solver lo detectara.
                continue
            km = float(xlsx_dist[name_to_xlsx_idx[name_i], name_to_xlsx_idx[name_j]])
            dist_full[i, j] = km
            # Tiempo estimado: km / velocidad media * 60 minutos.
            time_full[i, j] = (km / speed_long) * 60.0 if i != j else 0.0

    return all_names, dist_full, time_full, new_indices


def load_dataset(
    poblacion_path: str | Path = "data/poblacion.csv",
    rutas_path: str | Path = "data/rutasDistTiempo.csv",
    distancias_xlsx_path: str | Path = "data/distanciasReales.xlsx",
    new_node_populations: Dict[str, int] | None = None,
) -> Dataset:
    """Carga y unifica todas las fuentes en un :class:`Dataset` listo para usar."""
    poblacion_path = Path(poblacion_path)
    rutas_path = Path(rutas_path)
    distancias_xlsx_path = Path(distancias_xlsx_path)

    pob_df = _read_poblacion(poblacion_path)
    n_pob = len(pob_df)

    csv_dist, csv_time = _read_routes(rutas_path, n_expected=n_pob)

    xlsx_labels, xlsx_dist = _read_distance_xlsx(distancias_xlsx_path)

    poblacion_names = pob_df["Municipio"].tolist()
    all_names, dist_full, time_full, new_indices = _build_unified_matrices(
        poblacion_names=poblacion_names,
        csv_dist=csv_dist,
        csv_time=csv_time,
        xlsx_labels=xlsx_labels,
        xlsx_dist=xlsx_dist,
    )

    # Construir vectores alineados con all_names.
    n_total = len(all_names)
    latitudes = np.zeros(n_total, dtype=float)
    longitudes = np.zeros(n_total, dtype=float)
    restringe = np.zeros(n_total, dtype=int)
    poblacion = np.zeros(n_total, dtype=int)

    for i, name in enumerate(all_names):
        if i < n_pob:
            row = pob_df.iloc[i]
            latitudes[i] = float(row["Latitud (Y)"])
            longitudes[i] = float(row["Longitud (X)"])
            restringe[i] = int(row["Restringe camion"])
            poblacion[i] = int(row["Población"])
        else:
            # Nodo nuevo: poblacion configurable, coordenadas aproximadas conocidas.
            pop_lookup = (new_node_populations or {})
            default_pop = DEFAULT_NEW_NODE_POPULATIONS.get(name, 0)
            poblacion[i] = int(pop_lookup.get(name, default_pop))
            # Coordenadas centro de cada capital (referencia).
            new_coords = {
                "Cádiz": (36.5298, -6.2926),
                "Málaga": (36.7213, -4.4214),
                "Córdoba": (37.8882, -4.7794),
                "Huelva": (37.2614, -6.9447),
            }
            lat, lon = new_coords.get(name, (0.0, 0.0))
            latitudes[i] = float(lat)
            longitudes[i] = float(lon)
            # Las nuevas capitales NO restringen camion por defecto (son centros logisticos).
            restringe[i] = 0

    if DEPOT_NAME not in all_names:
        raise ValueError(f"No se encontro el deposito '{DEPOT_NAME}' en los datos cargados")
    depot_index = all_names.index(DEPOT_NAME)

    return Dataset(
        names=all_names,
        latitudes=latitudes,
        longitudes=longitudes,
        restringe_camion=restringe,
        poblacion=poblacion,
        distance_matrix=dist_full,
        time_matrix=time_full,
        depot_index=depot_index,
    )
