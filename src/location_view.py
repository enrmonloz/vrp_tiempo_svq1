"""Visualización interactiva de resultados de localización.

Este módulo proporciona funciones para visualizar en mapas (Folium) y gráficos
(Plotly) los resultados de localización de centros de reparto.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import folium
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


from .location_solver import LocationResult, LocationSolver


def build_location_map(
    dataset,
    result: LocationResult,
    show_distance_rings: bool = False,
    include_hubs: bool = True,
) -> folium.Map:
    """Construye un mapa Folium con la localización óptima y los municipios.

    Parámetros:
        dataset: Dataset con coordenadas y población de municipios.
        result: LocationResult con la ubicación óptima.
        show_distance_rings: si True, dibuja anillos de distancia concéntricos.
        include_hubs: si True, marca los centros logísticos (SVQ1, DQA4).

    Retorna:
        Mapa Folium listo para renderizar.
    """
    # Centro geográfico del mapa
    center_lat = np.mean(dataset.latitudes)
    center_lon = np.mean(dataset.longitudes)

    # Crear mapa centrado
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles="OpenStreetMap",
    )

    # Identificar centros logísticos y municipios de demanda
    is_hub = dataset.poblacion == 0
    is_demand = dataset.poblacion > 0

    # 1. Dibujar municipios de demanda como burbujas (tamaño proporcional a población)
    demand_indices = np.where(is_demand)[0]
    poblacion_norm = dataset.poblacion[demand_indices] / dataset.poblacion[demand_indices].max()
    for idx_pos, i in enumerate(demand_indices):
        radius = max(10, float(poblacion_norm[idx_pos]) * 30)
        folium.CircleMarker(
            location=[dataset.latitudes[i], dataset.longitudes[i]],
            radius=radius,
            popup=f"{dataset.names[i]}<br>Población: {int(dataset.poblacion[i]):,}",
            tooltip=dataset.names[i],
            color="#5B9BD5",
            fill=True,
            fillColor="#5B9BD5",
            fillOpacity=0.6,
            weight=1,
        ).add_to(m)

    # 2. Dibujar centros logísticos (si include_hubs=True)
    if include_hubs:
        for i in np.where(is_hub)[0]:
            icon_color = "#EDB120" if dataset.names[i] == "DQA4" else "#FF0000"
            folium.Marker(
                location=[dataset.latitudes[i], dataset.longitudes[i]],
                popup=f"{dataset.names[i]} (Centro Logístico)",
                tooltip=dataset.names[i],
                icon=folium.Icon(color=icon_color, icon="warehouse", prefix="fa"),
            ).add_to(m)

    # 3. Dibujar ubicación óptima
    folium.Marker(
        location=[result.latitude, result.longitude],
        popup=(
            f"<b>Óptimo ({result.method.value.replace('_', ' ').title()})</b><br>"
            f"Municipio más cercano: {result.nearest_municipality}<br>"
            f"Distancia: {result.distance_to_nearest_km:.2f} km<br>"
            f"Dist. total ponderada: {result.weighted_distance:,.1f}<br>"
            f"Dist. máxima ponderada: {result.max_weighted_distance:,.1f}"
        ),
        tooltip="Ubicación óptima calculada",
        icon=folium.Icon(color="green", icon="star", prefix="fa"),
    ).add_to(m)

    # 4. Dibujar anillos de distancia (opcional)
    if show_distance_rings:
        distances_km = [50, 100, 150]
        colors = ["#90EE90", "#FFD700", "#FF6347"]
        for dist_km, color in zip(distances_km, colors):
            folium.Circle(
                location=[result.latitude, result.longitude],
                radius=dist_km * 1000,  # Convertir a metros
                popup=f"{dist_km} km",
                color=color,
                fill=False,
                weight=1,
                opacity=0.5,
            ).add_to(m)

    return m


def build_comparison_map(
    dataset,
    solutions: dict,  # dict de LocationResult por método
) -> folium.Map:
    """Construye un mapa con múltiples soluciones superpuestas (una por cada método).

    Parámetros:
        dataset: Dataset con coordenadas.
        solutions: Diccionario {método: LocationResult}.

    Retorna:
        Mapa Folium con todas las soluciones marcadas.
    """
    center_lat = np.mean(dataset.latitudes)
    center_lon = np.mean(dataset.longitudes)

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles="OpenStreetMap",
    )

    # Colores para cada método
    colors = {
        "gravity_center": "blue",
        "min_total_distance": "purple",
        "minimax": "red",
        "geographic_center": "gray",
        "k_median": "orange",
    }

    # Dibujar cada solución
    for method_name, result in solutions.items():
        color = colors.get(method_name, "gray")
        folium.Marker(
            location=[result.latitude, result.longitude],
            popup=(
                f"<b>{method_name.replace('_', ' ').title()}</b><br>"
                f"Municipio: {result.nearest_municipality}<br>"
                f"Dist. total: {result.weighted_distance:,.1f}"
            ),
            tooltip=method_name,
            icon=folium.Icon(color=color, icon="map-pin", prefix="fa"),
        ).add_to(m)

    # Dibujar municipios de demanda
    is_demand = dataset.poblacion > 0
    demand_indices = np.where(is_demand)[0]
    poblacion_norm = dataset.poblacion[demand_indices] / dataset.poblacion[demand_indices].max()
    for idx_pos, i in enumerate(demand_indices):
        radius = max(5, float(poblacion_norm[idx_pos]) * 20)
        folium.CircleMarker(
            location=[dataset.latitudes[i], dataset.longitudes[i]],
            radius=radius,
            color="#5B9BD5",
            fill=True,
            fillColor="#5B9BD5",
            fillOpacity=0.4,
            weight=0.5,
        ).add_to(m)

    return m


def create_distance_heatmap(
    dataset,
    result: LocationResult,
) -> go.Figure:
    """Crea un gráfico de distancia por municipio desde la ubicación óptima.

    Parámetros:
        dataset: Dataset con municipios.
        result: LocationResult con la ubicación óptima.

    Retorna:
        Figura Plotly con gráfico de barras.
    """
    distances = np.sqrt(
        (result.longitude - dataset.longitudes) ** 2
        + (result.latitude - dataset.latitudes) ** 2
    )

    # Haversine más preciso
    R = 6371
    lat1 = np.radians(result.latitude)
    lon1 = np.radians(result.longitude)
    lat2 = np.radians(dataset.latitudes)
    lon2 = np.radians(dataset.longitudes)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    distances_km = R * c

    # Filtrar solo municipios con demanda
    is_demand = dataset.poblacion > 0
    names_demand = [dataset.names[i] for i in range(len(dataset.names)) if is_demand[i]]
    distances_demand = [distances_km[i] for i in range(len(distances_km)) if is_demand[i]]

    # Ordenar por distancia
    sorted_indices = np.argsort(distances_demand)
    sorted_names = [names_demand[i] for i in sorted_indices]
    sorted_distances = [distances_demand[i] for i in sorted_indices]

    fig = go.Figure(
        data=[
            go.Bar(
                y=sorted_names[:30],  # Top 30 municipios más lejanos
                x=sorted_distances[:30],
                orientation="h",
                marker=dict(color=sorted_distances[:30], colorscale="Reds"),
            )
        ]
    )
    fig.update_layout(
        title=f"Distancia desde ubicación óptima ({result.method.value})",
        xaxis_title="Distancia (km)",
        yaxis_title="Municipio",
        height=500,
        showlegend=False,
    )

    return fig


def create_population_coverage_chart(
    dataset,
    result: LocationResult,
    distance_thresholds: Optional[List[float]] = None,
) -> go.Figure:
    """Crea un gráfico de cobertura de población por rangos de distancia.

    Parámetros:
        dataset: Dataset con población.
        result: LocationResult con ubicación óptima.
        distance_thresholds: Lista de distancias (km) para evaluar cobertura.
                            Por defecto: [25, 50, 75, 100, 150, 200].

    Retorna:
        Figura Plotly con gráfico de área.
    """
    if distance_thresholds is None:
        distance_thresholds = [25, 50, 75, 100, 150, 200]

    # Calcular distancias Haversine
    R = 6371
    lat1 = np.radians(result.latitude)
    lon1 = np.radians(result.longitude)
    lat2 = np.radians(dataset.latitudes)
    lon2 = np.radians(dataset.longitudes)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    distances_km = R * c

    # Calcular población dentro de cada radio
    is_demand = dataset.poblacion > 0
    coverage = []
    coverage_pct = []

    total_population = dataset.poblacion[is_demand].sum()

    for dist in distance_thresholds:
        covered = (distances_km[is_demand] <= dist).sum()
        covered_pop = dataset.poblacion[is_demand][distances_km[is_demand] <= dist].sum()
        coverage.append(covered_pop)
        coverage_pct.append(100 * covered_pop / total_population)

    fig = go.Figure(
        data=[
            go.Scatter(
                x=[str(d) for d in distance_thresholds],
                y=coverage_pct,
                fill="tozeroy",
                mode="lines+markers",
                line=dict(color="#5B9BD5", width=2),
                marker=dict(size=8),
            )
        ]
    )
    fig.update_layout(
        title="Cobertura de población por distancia",
        xaxis_title="Distancia máxima (km)",
        yaxis_title="Población cubierta (%)",
        yaxis_range=[0, 105],
        height=400,
        showlegend=False,
    )

    return fig


def render_location_results(dataset, result: LocationResult) -> None:
    """Renderiza un panel completo de resultados de localización en Streamlit.

    Parámetros:
        dataset: Dataset con municipios.
        result: LocationResult con la solución calculada.
    """
    st.markdown("### Resultados de Localización")

    # Métricas clave
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Latitud", f"{result.latitude:.4f}")
    col2.metric("Longitud", f"{result.longitude:.4f}")
    col3.metric("Municipio Más Cercano", result.nearest_municipality)
    col4.metric("Distancia (km)", f"{result.distance_to_nearest_km:.2f}")

    col1b, col2b = st.columns(2)
    col1b.metric("Dist. Total Ponderada", f"{result.weighted_distance:,.0f}")
    col2b.metric("Dist. Máx. Ponderada", f"{result.max_weighted_distance:,.0f}")

    # Mapa principal
    st.markdown("### Visualización Geográfica")
    m = build_location_map(dataset, result, show_distance_rings=True)
    from streamlit_folium import st_folium

    st_folium(m, height=500, use_container_width=True)

    # Gráficos adicionales
    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("### Cobertura de Población")
        fig_coverage = create_population_coverage_chart(dataset, result)
        st.plotly_chart(fig_coverage, use_container_width=True)

    with col_right:
        st.markdown("### Distancias a Municipios")
        fig_distances = create_distance_heatmap(dataset, result)
        st.plotly_chart(fig_distances, use_container_width=True)


def render_comparison_view(dataset, solver: LocationSolver) -> None:
    """Renderiza un panel comparativo de todas las técnicas de localización.

    Parámetros:
        dataset: Dataset con municipios.
        solver: LocationSolver inicializado.
    """
    st.markdown("### Comparación de Técnicas de Localización")

    # Tabla comparativa
    st.markdown("#### Tabla Comparativa")
    comparison_df = solver.compare_solutions()
    st.dataframe(comparison_df, use_container_width=True, hide_index=True)

    # Mapa con todas las soluciones
    st.markdown("#### Ubicaciones Óptimas por Método")
    solutions = solver.get_all_solutions()
    m_comparison = build_comparison_map(dataset, solutions)
    from streamlit_folium import st_folium

    st_folium(m_comparison, height=500, use_container_width=True)

    # Tabla detallada de desempeño
    st.markdown("#### Análisis de Desempeño")
    perf_rows = []
    for method_name, result in solutions.items():
        perf_rows.append(
            {
                "Método": method_name.replace("_", " ").title(),
                "Lat": f"{result.latitude:.4f}",
                "Lon": f"{result.longitude:.4f}",
                "Dist. Total": f"{result.weighted_distance:,.0f}",
                "Dist. Máx": f"{result.max_weighted_distance:,.0f}",
                "Municipio": result.nearest_municipality,
                "Km al municipio": f"{result.distance_to_nearest_km:.2f}",
            }
        )
    st.dataframe(pd.DataFrame(perf_rows), use_container_width=True, hide_index=True)
