"""Construccion del mapa de rutas con folium.

Visualizacion a alto nivel: cada ruta VRP se dibuja como una polilinea entre
nodos (lineas rectas, no rutas reales por carretera) con un color distinto.
Las rutas dedicadas (split-delivery) se dibujan como lineas punteadas
diferentes para distinguirlas visualmente. El deposito SVQ1 se marca con un
icono especial.
"""

from __future__ import annotations

from typing import List

import folium

from .data_loader import Dataset
from .fleet import VehicleType
from .pipeline import PipelineResult


# Paleta cualitativa para distinguir vehiculos. Reutilizada ciclicamente si
# hay mas rutas que colores (es comun cuando la jornada es ajustada).
_VRP_COLORS: List[str] = [
    "#1f77b4", "#2ca02c", "#9467bd", "#ff7f0e", "#8c564b",
    "#e377c2", "#17becf", "#bcbd22", "#7f7f7f", "#d62728",
    "#393b79", "#637939", "#8c6d31", "#843c39", "#7b4173",
    "#3182bd", "#31a354", "#756bb1", "#e6550d", "#636363",
]


def _vehicle_color(vehicle_index: int) -> str:
    return _VRP_COLORS[vehicle_index % len(_VRP_COLORS)]


def _vehicle_label(vehicle_type: VehicleType) -> str:
    return "Diesel" if vehicle_type == VehicleType.DIESEL else "Electrica"


def build_route_map(dataset: Dataset, result: PipelineResult) -> folium.Map:
    """Devuelve un objeto ``folium.Map`` con todas las rutas dibujadas."""
    depot_lat = float(dataset.latitudes[dataset.depot_index])
    depot_lon = float(dataset.longitudes[dataset.depot_index])

    fmap = folium.Map(
        location=[depot_lat, depot_lon],
        zoom_start=8,
        tiles="cartodbpositron",
        control_scale=True,
    )

    # Capas para poder activar/desactivar grupos de rutas.
    layer_vrp = folium.FeatureGroup(name="Rutas VRP", show=True)
    layer_dedicated = folium.FeatureGroup(name="Rutas dedicadas (split)", show=True)
    layer_unvisited = folium.FeatureGroup(name="Nodos sin demanda", show=False)

    # Marker del deposito.
    folium.Marker(
        location=[depot_lat, depot_lon],
        popup=folium.Popup(
            f"<b>{dataset.names[dataset.depot_index]}</b><br>Deposito",
            max_width=240,
        ),
        tooltip="Deposito SVQ1",
        icon=folium.Icon(color="red", icon="home", prefix="fa"),
    ).add_to(fmap)

    # Rutas VRP.
    for i, route in enumerate(result.vrp.routes):
        color = _vehicle_color(i)
        coords = [(depot_lat, depot_lon)]
        for stop in route.stops:
            lat = float(dataset.latitudes[stop.node_index])
            lon = float(dataset.longitudes[stop.node_index])
            coords.append((lat, lon))
            popup_html = (
                f"<b>{stop.node_name}</b><br>"
                f"Vehiculo {route.vehicle_id} ({_vehicle_label(route.vehicle_type)})<br>"
                f"Paquetes: {stop.packages}<br>"
                f"Llegada: {stop.arrival_time_min:.0f} min"
            )
            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color=color,
                fill=True,
                fill_color=color,
                fill_opacity=0.85,
                popup=folium.Popup(popup_html, max_width=260),
                tooltip=stop.node_name,
            ).add_to(layer_vrp)
        coords.append((depot_lat, depot_lon))

        line_popup = (
            f"<b>Vehiculo {route.vehicle_id}</b> ({_vehicle_label(route.vehicle_type)})<br>"
            f"Paradas: {len(route.stops)}<br>"
            f"Paquetes: {sum(s.packages for s in route.stops)}<br>"
            f"Tiempo total: {route.total_time_min:.0f} min<br>"
            f"Distancia: {route.travel_distance_km:.1f} km"
        )
        folium.PolyLine(
            locations=coords,
            color=color,
            weight=3,
            opacity=0.8,
            popup=folium.Popup(line_popup, max_width=280),
            tooltip=f"V{route.vehicle_id} - {_vehicle_label(route.vehicle_type)}",
        ).add_to(layer_vrp)

    # Rutas dedicadas (split-delivery): trailer en marron solido, furgoneta
    # dedicada en gris punteado.
    for r_idx, r in enumerate(result.split.dedicated_routes, start=1):
        lat = float(dataset.latitudes[r.node_index])
        lon = float(dataset.longitudes[r.node_index])
        coords = [(depot_lat, depot_lon), (lat, lon), (depot_lat, depot_lon)]
        is_trailer = r.vehicle_type == "trailer"
        line_color = "#8B4513" if is_trailer else "#444444"
        dash = None if is_trailer else "6,8"
        marker_color = "#5a2a0a" if is_trailer else "#222222"
        marker_fill = "#c97b4d" if is_trailer else "#888888"
        kind = "Trailer" if is_trailer else "Furgoneta dedicada"
        popup_html = (
            f"<b>{kind} #{r_idx}</b><br>"
            f"Nodo: {r.node_name}<br>"
            f"Paquetes: {r.packages}<br>"
            f"Tiempo total: {r.total_time_min:.0f} min<br>"
            f"Distancia: {r.travel_distance_km:.1f} km"
        )
        polyline_kwargs = dict(
            locations=coords,
            color=line_color,
            weight=3 if is_trailer else 2,
            opacity=0.8 if is_trailer else 0.7,
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=f"{kind} {r_idx}: {r.node_name}",
        )
        if dash is not None:
            polyline_kwargs["dash_array"] = dash
        folium.PolyLine(**polyline_kwargs).add_to(layer_dedicated)
        folium.CircleMarker(
            location=[lat, lon],
            radius=7 if is_trailer else 6,
            color=marker_color,
            fill=True,
            fill_color=marker_fill,
            fill_opacity=0.9,
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=f"{r.node_name} ({kind.lower()})",
        ).add_to(layer_dedicated)

    # Nodos sin demanda asignada (referencia visual).
    visited_in_vrp = {s.node_index for route in result.vrp.routes for s in route.stops}
    visited_in_dedicated = {r.node_index for r in result.split.dedicated_routes}
    visited = visited_in_vrp | visited_in_dedicated
    for node_idx in range(dataset.n_nodes):
        if node_idx == dataset.depot_index or node_idx in visited:
            continue
        if int(result.packages[node_idx]) == 0:
            continue
        lat = float(dataset.latitudes[node_idx])
        lon = float(dataset.longitudes[node_idx])
        folium.CircleMarker(
            location=[lat, lon],
            radius=3,
            color="#aaaaaa",
            fill=True,
            fill_color="#cccccc",
            fill_opacity=0.6,
            tooltip=f"{dataset.names[node_idx]} (no asignado)",
        ).add_to(layer_unvisited)

    layer_vrp.add_to(fmap)
    layer_dedicated.add_to(fmap)
    layer_unvisited.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    return fmap
