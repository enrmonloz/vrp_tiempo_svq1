"""Streamlit app - VRP por tiempo desde SVQ1.

Interfaz industrial con configuracion arriba (expander + tabs), pantalla
principal centrada en el mapa de rutas y los datos de la resolucion, y
pantallas secundarias accesibles por botones para detalle por vehiculo,
rutas dedicadas, distribucion de turnos y detalle por parada.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

# Permite ejecutar `streamlit run app.py` desde la raiz del proyecto.
import sys
THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from src.data_loader import load_dataset
from src.fleet import FleetConfig, VehicleType
from src.map_view import build_route_map
from src.pipeline import PipelineConfig, run_pipeline
from src.schedule import ScheduleConfig
from src.trailer import DEFAULT_BIG_NODES, TrailerConfig
from src.vrp_solver import SolverStrategy
from src.location_solver import LocationMethod, LocationSolver
from src.location_view import render_location_results, render_comparison_view


st.set_page_config(
    page_title="VRP SVQ1",
    page_icon=":truck:",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# Estilos: aspecto industrial (gris oscuro + naranja Amazon, bordes definidos)
# ---------------------------------------------------------------------------
_INDUSTRIAL_CSS = """
<style>
    :root {
        /* Branding (cabecera) */
        --brand-dark: #1a1d23;
        --brand-darker: #11141a;
        --accent: #ff9900;
        --accent-dim: #c97400;
        --accent-soft: #fff4e0;

        /* Cuerpo claro */
        --bg-app: #f5f6f8;
        --bg-card: #ffffff;
        --bg-soft: #eef0f4;
        --text-main: #1f2329;
        --text-dim: #5b6470;
        --border: #d6d9de;
        --border-strong: #b9bdc4;
    }

    /* Fondo principal claro y ancho razonable */
    .stApp {
        background-color: var(--bg-app);
    }
    section.main > div.block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* Cabecera oscura como branding industrial */
    .industrial-header {
        background: linear-gradient(90deg, var(--brand-darker) 0%, var(--brand-dark) 100%);
        border-left: 6px solid var(--accent);
        padding: 1.1rem 1.3rem;
        margin-bottom: 1.1rem;
        border-radius: 2px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.18);
    }
    .industrial-header h1 {
        margin: 0;
        font-size: 1.7rem;
        font-weight: 700;
        letter-spacing: 0.04em;
        color: #ffffff;
        text-transform: uppercase;
    }
    .industrial-header .subtitle {
        color: #c9ced6;
        font-size: 0.9rem;
        margin-top: 0.25rem;
        letter-spacing: 0.02em;
    }
    .industrial-tag {
        display: inline-block;
        background: var(--accent);
        color: var(--brand-dark);
        font-weight: 700;
        padding: 0.15rem 0.55rem;
        margin-right: 0.5rem;
        font-size: 0.72rem;
        letter-spacing: 0.1em;
        border-radius: 2px;
    }

    /* Cards de metricas: fondo blanco, borde claro, accent naranja */
    div[data-testid="stMetric"] {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-left: 4px solid var(--accent);
        padding: 0.85rem 1rem;
        border-radius: 3px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    div[data-testid="stMetricLabel"] p {
        text-transform: uppercase;
        font-size: 0.74rem !important;
        letter-spacing: 0.08em;
        color: var(--text-dim) !important;
        font-weight: 600 !important;
    }
    div[data-testid="stMetricValue"] {
        font-weight: 700 !important;
        font-size: 1.7rem !important;
        color: var(--text-main) !important;
    }

    /* Boton primario en naranja Amazon */
    div.stButton > button[kind="primary"] {
        background: var(--accent);
        color: var(--brand-dark);
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border: none;
        border-radius: 2px;
        padding: 0.6rem 1.2rem;
        box-shadow: 0 1px 2px rgba(0,0,0,0.15);
    }
    div.stButton > button[kind="primary"]:hover {
        background: var(--accent-dim);
        color: #ffffff;
    }

    /* Botones secundarios (navegacion) */
    div.stButton > button[kind="secondary"] {
        background: var(--bg-card);
        color: var(--text-main);
        border: 1px solid var(--border-strong);
        border-radius: 2px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 0.55rem 0.9rem;
    }
    div.stButton > button[kind="secondary"]:hover {
        border-color: var(--accent);
        color: var(--accent-dim);
        background: var(--accent-soft);
    }

    /* Expander de configuracion */
    div[data-testid="stExpander"] {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 3px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    }
    div[data-testid="stExpander"] summary {
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.85rem;
        color: var(--text-main);
    }
    div[data-testid="stExpander"] summary:hover {
        color: var(--accent-dim);
    }

    /* Tabs internos del expander */
    div[data-baseweb="tab-list"] {
        border-bottom: 1px solid var(--border) !important;
    }
    button[data-baseweb="tab"] {
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        font-size: 0.78rem;
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        color: var(--accent-dim) !important;
        border-bottom-color: var(--accent) !important;
    }

    /* Subtitulos de seccion */
    .section-title {
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 700;
        font-size: 0.95rem;
        color: var(--text-main);
        border-bottom: 2px solid var(--accent);
        padding-bottom: 0.3rem;
        margin: 1.2rem 0 0.7rem 0;
    }

    /* Tablas: borde claro y filas legibles */
    div[data-testid="stDataFrame"] {
        border: 1px solid var(--border);
        border-radius: 3px;
        background: var(--bg-card);
    }

    /* Avisos (warning, info) con buen contraste sobre fondo claro */
    div[data-testid="stAlert"] {
        border-radius: 3px;
    }

    /* Inputs y selects: borde claro, fondo blanco */
    div[data-baseweb="input"] input,
    div[data-baseweb="select"] > div,
    div[data-baseweb="time-input"] input {
        background: var(--bg-card) !important;
    }

    /* Captions */
    div[data-testid="stCaptionContainer"], .stCaption {
        color: var(--text-dim) !important;
    }
</style>
"""


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _format_minutes(minutes: float) -> str:
    if minutes is None:
        return "-"
    h = int(minutes // 60)
    m = int(round(minutes - h * 60))
    if h == 0:
        return f"{m} min"
    return f"{h} h {m} min"


@st.cache_data(show_spinner=False)
def _cached_dataset(poblacion_path: str, rutas_path: str):
    return load_dataset(
        poblacion_path=poblacion_path,
        rutas_path=rutas_path,
    )


def _section_title(text: str) -> None:
    st.markdown(f"<div class='section-title'>{text}</div>", unsafe_allow_html=True)


def _go(view: str) -> None:
    st.session_state["view"] = view


# ---------------------------------------------------------------------------
# Panel de configuracion (arriba, expander con tabs)
# ---------------------------------------------------------------------------
def render_config_panel() -> dict:
    """Renderiza el panel de configuracion y devuelve los valores elegidos."""
    with st.expander("Configuracion del modelo", expanded=False):
        tabs = st.tabs(["Demanda", "Flota", "Trailers", "Horario", "Solver"])

        # --- Tab: Demanda ---
        with tabs[0]:
            c1, c2, c3 = st.columns(3)
            market_pct = c1.number_input(
                "Penetracion de mercado (%)",
                min_value=0.001,
                max_value=100.0,
                value=0.523,
                step=0.001,
                format="%.3f",
                help="Acepta hasta 3 decimales (p.ej. 1.215).",
            )
            service_min = c2.number_input(
                "Servicio por paquete (min)",
                min_value=0.0, max_value=30.0, value=1.5, step=0.5,
            )
            inter_min = c3.number_input(
                "Conduccion entre paquetes (min)",
                min_value=0.0, max_value=30.0, value=1.0, step=0.5,
            )
            new_pops = {}  # Ya no hay nodos nuevos en el XLSX

        # --- Tab: Flota ---
        with tabs[1]:
            c1, c2, c3 = st.columns(3)
            max_diesel = c1.number_input(
                "Cota furgonetas diesel", min_value=0, max_value=500, value=75, step=5,
            )
            max_electric = c2.number_input(
                "Cota furgonetas electricas", min_value=0, max_value=500, value=45, step=5,
            )
            electric_range = c3.number_input(
                "Rango electrico (km/jornada)", min_value=50.0, max_value=1000.0, value=350.0, step=10.0,
            )
            with st.expander("Costes fijos del solver"):
                cc1, cc2 = st.columns(2)
                diesel_cost = int(
                    cc1.number_input(
                        "Coste fijo diesel", min_value=0, max_value=10_000_000,
                        value=1_050_000, step=10_000,
                    )
                )
                electric_cost = int(
                    cc2.number_input(
                        "Coste fijo electrica", min_value=0, max_value=10_000_000,
                        value=1_000_000, step=10_000,
                    )
                )

        # --- Tab: Trailers ---
        with tabs[2]:
            trailer_enabled = st.checkbox(
                "Usar trailers para nodos grandes (Cadiz, Malaga, Cordoba, Huelva, Granada)",
                value=True,
            )
            c1, c2 = st.columns(2)
            trailer_capacity = c1.number_input(
                "Capacidad trailer (paquetes/viaje)",
                min_value=10, max_value=20_000, value=500, step=50,
                disabled=not trailer_enabled,
            )
            trailer_unloading = c2.number_input(
                "Tiempo de descarga (min)",
                min_value=0.0, max_value=240.0, value=30.0, step=5.0,
                disabled=not trailer_enabled,
            )

        # --- Tab: Horario ---
        with tabs[3]:
            c1, c2, c3, c4 = st.columns(4)
            max_workday_hours = c1.number_input(
                "Jornada efectiva (h)",
                min_value=1.0, max_value=14.0, value=7.5, step=0.25,
                help="Tiempo efectivo de trabajo. La pausa NO se cuenta aqui.",
            )
            start_clock = c2.time_input(
                "Hora de inicio", value=_dt.time(8, 0),
            )
            morning_max_min = c3.number_input(
                "Tiempo continuado antes de pausa (min)",
                min_value=60.0, max_value=480.0, value=240.0, step=15.0,
            )
            lunch_break_min = c4.number_input(
                "Duracion pausa para comer (min)",
                min_value=0.0, max_value=240.0, value=90.0, step=5.0,
            )

        # --- Tab: Solver ---
        with tabs[4]:
            c1, c2 = st.columns([2, 1])
            strategy_options = {
                "Vecino mas cercano (Nearest Neighbor)": SolverStrategy.NEAREST_NEIGHBOR,
                "Algoritmo de barrido (Sweep)": SolverStrategy.SWEEP,
                "Clarke-Wright (Savings)": SolverStrategy.SAVINGS,
                "Heuristica de insercion paralela": SolverStrategy.INSERTION,
                "Christofides (3/2-aprox.)": SolverStrategy.CHRISTOFIDES,
            }
            strategy_label = c1.selectbox(
                "Metodo de resolucion",
                options=list(strategy_options.keys()),
                index=3,
                help="La mejora local sobre la primera solucion siempre usa Guided Local Search.",
            )
            time_limit = c2.number_input(
                "Tiempo maximo (s)",
                min_value=5, max_value=600, value=30, step=5,
            )

    return {
        "market_pct": market_pct,
        "service_min": service_min,
        "inter_min": inter_min,
        "new_pops": new_pops,
        "max_diesel": int(max_diesel),
        "max_electric": int(max_electric),
        "electric_range": float(electric_range),
        "diesel_cost": diesel_cost,
        "electric_cost": electric_cost,
        "trailer_enabled": bool(trailer_enabled),
        "trailer_capacity": int(trailer_capacity),
        "trailer_unloading": float(trailer_unloading),
        "max_workday_hours": float(max_workday_hours),
        "start_clock": start_clock,
        "morning_max_min": float(morning_max_min),
        "lunch_break_min": float(lunch_break_min),
        "solver_strategy": strategy_options[strategy_label],
        "time_limit": int(time_limit),
    }


def build_pipeline_config(params: dict) -> PipelineConfig:
    fleet = FleetConfig(
        max_diesel=params["max_diesel"],
        max_electric=params["max_electric"],
        electric_max_range_km=params["electric_range"],
        diesel_fixed_cost=params["diesel_cost"],
        electric_fixed_cost=params["electric_cost"],
    )
    trailer = TrailerConfig(
        enabled=params["trailer_enabled"],
        packages_capacity=params["trailer_capacity"],
        unloading_time_min=params["trailer_unloading"],
        big_nodes=DEFAULT_BIG_NODES,
    )
    schedule_cfg = ScheduleConfig(
        start_hour=int(params["start_clock"].hour),
        start_minute=int(params["start_clock"].minute),
        lunch_break_min=params["lunch_break_min"],
        morning_max_min=params["morning_max_min"],
    )
    return PipelineConfig(
        market_penetration=params["market_pct"] / 100.0,
        max_workday_hours=params["max_workday_hours"],
        service_time_per_package_min=params["service_min"],
        inter_package_time_min=params["inter_min"],
        fleet=fleet,
        trailer=trailer,
        schedule=schedule_cfg,
        solver_strategy=params["solver_strategy"],
        solver_time_limit_seconds=params["time_limit"],
    )


# ---------------------------------------------------------------------------
# Pantallas
# ---------------------------------------------------------------------------
def view_main(result, dataset) -> None:
    """Pantalla principal: resumen + mapa + botones de navegacion."""
    _section_title("Resumen de la resolucion")
    cols = st.columns(4)
    cols[0].metric("Total rutas", result.total_routes)
    cols[1].metric("Rutas VRP", result.vrp_route_count)
    cols[2].metric("Rutas dedicadas", result.dedicated_route_count)
    cols[3].metric("Paquetes totales", f"{int(result.packages.sum()):,}")

    cols2 = st.columns(4)
    cols2[0].metric("Distancia total", f"{result.total_distance_km:,.0f} km")
    cols2[1].metric("Tiempo total", _format_minutes(result.total_time_min))
    cols2[2].metric("Diesel (VRP)", result.vrp.diesel_count)
    cols2[3].metric("Electricas (VRP)", result.vrp.electric_count)

    if result.vrp.unassigned_nodes:
        st.warning(
            "Nodos sin asignar: "
            + ", ".join(dataset.names[i] for i in result.vrp.unassigned_nodes)
        )

    _section_title("Mapa de rutas")
    st.caption(
        "Cada color representa una furgoneta VRP distinta. Las lineas marrones "
        "son rutas con trailer y las grises punteadas son furgonetas dedicadas. "
        "Click en cualquier elemento para ver detalle."
    )
    fmap = build_route_map(dataset, result)
    st_folium(fmap, height=560, use_container_width=True, returned_objects=[])

    _section_title("Detalle adicional")
    nav = st.columns(4)
    if nav[0].button("Detalle por vehiculo (VRP)", use_container_width=True):
        _go("vehicles")
        st.rerun()
    if nav[1].button("Rutas dedicadas y trailers", use_container_width=True):
        _go("dedicated")
        st.rerun()
    if nav[2].button("Distribucion de turnos", use_container_width=True):
        _go("shifts")
        st.rerun()
    if nav[3].button("Detalle parada a parada", use_container_width=True):
        _go("stops")
        st.rerun()


def _back_button() -> None:
    if st.button("Volver al resumen", type="secondary"):
        _go("main")
        st.rerun()


def view_location_selector(dataset) -> None:
    """Pantalla principal de localización con selector de técnica mejorado."""
    st.markdown(
        "Calcula la ubicación óptima para un nuevo centro de distribución "
        "basándose en la población y coordenadas de los municipios."
    )

    # Selector de vista mejorado
    view_mode = st.radio(
        "📊 **Selecciona la vista:**",
        options=["🎯 Solución Única", "📈 Comparar Técnicas"],
        horizontal=True,
    )

    if view_mode == "🎯 Solución Única":
        col1, col2 = st.columns([1, 1])
        with col1:
            technique_options = [
                ("gravity_center", "🌍 Centro de Gravedad"),
                ("min_total_distance", "📏 Minimizar Distancia Total"),
                ("minimax", "⚖️ Minimax (Equilibrar distancias)"),
                ("geographic_center", "🗺️ Centro Geográfico"),
                ("k_median", "🎲 K-Median (Iterativo)"),
            ]
            technique_label = st.selectbox(
                "🔧 **Técnica de localización:**",
                options=technique_options,
                format_func=lambda x: x[1],
                key="technique_select"
            )
            technique = technique_label[0]
    else:
        technique = None

    # Ejecutar solver
    solver = LocationSolver(dataset)

    if view_mode == "🎯 Solución Única":
        result = solver.solve(LocationMethod(technique))
        render_location_results(dataset, result)
    else:
        render_comparison_view(dataset, solver)


def view_vehicles(result) -> None:
    _back_button()
    _section_title("Detalle por vehiculo VRP")
    if not result.vrp.routes:
        st.info("El solver no ha generado rutas residuales.")
        return
    rows = []
    for route, sch in zip(result.vrp.routes, result.vrp_schedules):
        tipo = "Diesel" if route.vehicle_type == VehicleType.DIESEL else "Electrica"
        morning_names = [s.node_name for s in sch.stops if s.period == "manana"]
        afternoon_names = [s.node_name for s in sch.stops if s.period == "tarde"]
        rows.append(
            {
                "Vehiculo": route.vehicle_id,
                "Tipo": tipo,
                "# paradas": len(route.stops),
                "Paquetes": sum(s.packages for s in route.stops),
                "Tiempo total (min)": round(route.total_time_min, 1),
                "Distancia (km)": round(route.travel_distance_km, 1),
                "Inicio": sch.start_clock,
                "Pausa": "-" if not sch.has_lunch_break
                          else f"{sch.morning_end_clock} -> {sch.afternoon_start_clock}",
                "Fin": sch.end_clock,
                "Turno": sch.shift_label,
                "Manana (#)": sch.morning_stops,
                "Tarde (#)": sch.afternoon_stops,
                "Nodos manana": " - ".join(morning_names) if morning_names else "-",
                "Nodos tarde": " - ".join(afternoon_names) if afternoon_names else "-",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def view_dedicated(result) -> None:
    _back_button()
    _section_title("Rutas dedicadas (trailers + furgonetas dedicadas)")
    if not result.split.dedicated_routes:
        st.info("Ningun nodo necesita ruta dedicada con los parametros actuales.")
        return
    rows = []
    for r_idx, (r, sch) in enumerate(
        zip(result.split.dedicated_routes, result.dedicated_schedules), start=1
    ):
        rows.append(
            {
                "Ruta": r_idx,
                "Tipo": r.vehicle_type.capitalize(),
                "Nodo": r.node_name,
                "Paquetes": r.packages,
                "Viaje (min)": round(r.travel_time_min, 1),
                "Servicio (min)": round(r.service_time_min, 1),
                "Total (min)": round(r.total_time_min, 1),
                "Distancia (km)": round(r.travel_distance_km, 1),
                "Inicio": sch.start_clock,
                "Pausa": "-" if not sch.has_lunch_break
                          else f"{sch.morning_end_clock} -> {sch.afternoon_start_clock}",
                "Fin": sch.end_clock,
                "Turno": sch.shift_label,
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


def view_shifts(result) -> None:
    _back_button()
    _section_title("Distribucion de turnos")

    all_schedules = list(result.vrp_schedules) + list(result.dedicated_schedules)
    total = len(all_schedules)
    if total == 0:
        st.info("No hay rutas que mostrar.")
        return

    # Conteo por shift_label completo (los 5 posibles).
    expected_labels = [
        "Solo mañana",
        "Mañana + retorno tarde",
        "Mañana + tarde",
        "Solo tarde",
        "Sin paradas",
    ]
    counts = Counter(s.shift_label for s in all_schedules)

    with_break = sum(1 for s in all_schedules if s.has_lunch_break)
    without_break = total - with_break

    st.caption(
        "Las rutas se clasifican segun en que tramo de la jornada se realizan "
        "las paradas y si el conductor toma pausa para comer (la pausa se "
        "inserta cuando el tiempo efectivo cruza el umbral configurado)."
    )

    # Resumen agregado.
    cols = st.columns(3)
    cols[0].metric("Total rutas", total)
    cols[1].metric("Con pausa para comer", with_break)
    cols[2].metric("Sin pausa", without_break)

    # Tabla detallada con TODAS las categorias (suma cuadra con total).
    rows = [
        {
            "Tipo de turno": label,
            "Rutas": int(counts.get(label, 0)),
            "% del total": f"{(counts.get(label, 0) / total * 100):.1f}%",
        }
        for label in expected_labels
    ]
    rows.append(
        {
            "Tipo de turno": "TOTAL",
            "Rutas": total,
            "% del total": "100.0%",
        }
    )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    # Barra horizontal sencilla para visualizar.
    chart_df = pd.DataFrame(
        {"Rutas": [counts.get(label, 0) for label in expected_labels]},
        index=expected_labels,
    )
    chart_df = chart_df[chart_df["Rutas"] > 0]
    if not chart_df.empty:
        st.bar_chart(chart_df, horizontal=True)

    # Glosario para que el usuario entienda cada categoria.
    with st.expander("Explicacion de cada tipo de turno"):
        st.markdown(
            "- **Solo mañana**: la ruta termina antes del umbral de pausa; el "
            "conductor no necesita parar a comer.\n"
            "- **Mañana + retorno tarde**: las paradas son todas de mañana, "
            "pero la jornada cruza el umbral y el conductor toma la pausa "
            "antes de regresar al deposito.\n"
            "- **Mañana + tarde**: el conductor sirve paradas tanto antes "
            "como despues de la pausa para comer.\n"
            "- **Solo tarde**: todas las paradas son posteriores a la pausa "
            "(no se da habitualmente con inicio matinal).\n"
            "- **Sin paradas**: vehiculo asignado pero sin clientes (no debe "
            "darse en condiciones normales)."
        )


def view_stops(result) -> None:
    _back_button()
    _section_title("Detalle parada a parada (VRP)")
    if not result.vrp.routes:
        st.info("No hay rutas VRP.")
        return
    rows = []
    for route, sch in zip(result.vrp.routes, result.vrp_schedules):
        for stop, stop_sch in zip(route.stops, sch.stops):
            rows.append(
                {
                    "Vehiculo": route.vehicle_id,
                    "Tipo": "Diesel" if route.vehicle_type == VehicleType.DIESEL else "Electrica",
                    "Parada": stop_sch.node_name,
                    "Llegada": stop_sch.arrival_clock,
                    "Salida": stop_sch.leave_clock,
                    "Tramo": stop_sch.period.capitalize(),
                    "Paquetes": stop.packages,
                    "Servicio (min)": round(stop.service_time_min, 1),
                }
            )
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def main() -> None:
    st.markdown(_INDUSTRIAL_CSS, unsafe_allow_html=True)

    st.markdown(
        """
        <div class='industrial-header'>
            <h1>🚀 Proyecto de Amazon</h1>
            <div class='subtitle'>
                Optimización operativa integrada: Localiza el centro de distribución óptimo y asigna rutas inteligentes
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("✓ Dataset cargado: 82 municipios | 2 centros logísticos (SVQ1, DQA4)")

    if "view" not in st.session_state:
        st.session_state["view"] = "main"

    # Cargar dataset (necesario para ambas vistas)
    data_dir = THIS_DIR / "data"
    try:
        dataset = _cached_dataset(
            str(data_dir / "poblacion.csv"),
            str(data_dir / "rutasDistTiempo.csv"),
        )
    except Exception as exc:
        st.error(f"Error cargando datos: {exc}")
        st.stop()
    
    # Selector del problema a resolver mediante pestañas
    st.divider()
    tab_vrp, tab_localizacion = st.tabs(
        ["📦 Asignación de Rutas (VRP)", "📍 Localización de Centro"]
    )

    with tab_localizacion:
        view_location_selector(dataset)

    with tab_vrp:
        # Panel de configuracion arriba.
        params = render_config_panel()

        run_col, status_col = st.columns([1, 4])
        run_button = run_col.button("Resolver VRP", type="primary", use_container_width=True)

        # El dataset ya fue cargado al inicio de main()

        for name, pop in params["new_pops"].items():
            if name in dataset.names:
                idx = dataset.names.index(name)
                dataset.poblacion[idx] = int(pop)

        state_key = "vrp_result"
        if run_button or state_key not in st.session_state:
            config = build_pipeline_config(params)
            with st.spinner("Calculando asignacion..."):
                try:
                    result = run_pipeline(dataset, config)
                except Exception as exc:
                    st.error(f"No se pudo resolver el VRP: {exc}")
                    st.stop()
            st.session_state[state_key] = result
            # Tras ejecutar, regresar a la pantalla principal.
            st.session_state["view"] = "main"
        else:
            result = st.session_state[state_key]

        status_col.caption(
            f"Estrategia: **{params['solver_strategy'].value}** | "
            f"Penetracion: **{params['market_pct']:.3f}%** | "
            f"Jornada: **{params['max_workday_hours']:.2f} h** efectiva | "
            f"Trailers: **{'ON' if params['trailer_enabled'] else 'OFF'}**"
        )

        # Router de pantallas.
        view = st.session_state.get("view", "main")
        if view == "main":
            view_main(result, dataset)
        elif view == "vehicles":
            view_vehicles(result)
        elif view == "dedicated":
            view_dedicated(result)
        elif view == "shifts":
            view_shifts(result)
        elif view == "stops":
            view_stops(result)
        else:
            view_main(result, dataset)
    
    # Footer informativo
    st.divider()
    col1, col2, col3 = st.columns(3)
    col1.caption("🏢 **Centro**: SVQ1, Sevilla")
    col2.caption("📊 **Versión**: 2.1 Integrado (VRP + Localización)")
    col3.caption("⚙️ **Motor**: OR-Tools + SciPy Optimize")


if __name__ == "__main__":
    main()
