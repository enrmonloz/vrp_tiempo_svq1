"""
Ejemplo de uso del módulo de Localización de Centro de Reparto.

Este script demuestra cómo usar los módulos location_solver.py y location_view.py
de forma independiente a Streamlit, para análisis y generación de reportes.
"""

from pathlib import Path
import sys
import pandas as pd
import numpy as np

# Permitir importar módulos del proyecto
PROJECT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_DIR))

from src.data_loader import load_dataset
from src.location_solver import LocationSolver, LocationMethod


def example_basic_usage():
    """Ejemplo 1: Uso básico - obtener una solución."""
    print("=" * 70)
    print("EJEMPLO 1: Uso Básico - Solución Única")
    print("=" * 70)
    
    # Cargar datos
    data_dir = PROJECT_DIR / "data"
    dataset = load_dataset(
        str(data_dir / "poblacion.csv"),
        str(data_dir / "rutasDistTiempo.csv"),
    )
    
    # Crear solver
    solver = LocationSolver(dataset)
    
    # Resolver con método de minimización de distancia total
    result = solver.solve(LocationMethod.MIN_TOTAL_DISTANCE)
    
    # Mostrar resultados
    print(f"\n✓ Técnica: {result.method.value.replace('_', ' ').title()}")
    print(f"  Ubicación óptima:")
    print(f"    - Latitud:  {result.latitude:.6f}°")
    print(f"    - Longitud: {result.longitude:.6f}°")
    print(f"\n  Municipio más cercano:")
    print(f"    - Nombre: {result.nearest_municipality}")
    print(f"    - Distancia: {result.distance_to_nearest_km:.2f} km")
    print(f"\n  Métricas de desempeño:")
    print(f"    - Distancia total ponderada: {result.weighted_distance:,.1f}")
    print(f"    - Distancia máxima ponderada: {result.max_weighted_distance:,.1f}")
    print(f"    - Valor de función objetivo: {result.objective_value:.2f}")


def example_compare_all_methods():
    """Ejemplo 2: Comparar todas las técnicas de localización."""
    print("\n" + "=" * 70)
    print("EJEMPLO 2: Comparación de Técnicas")
    print("=" * 70)
    
    # Cargar datos
    data_dir = PROJECT_DIR / "data"
    dataset = load_dataset(
        str(data_dir / "poblacion.csv"),
        str(data_dir / "rutasDistTiempo.csv"),
    )
    
    # Crear solver
    solver = LocationSolver(dataset)
    
    # Obtener tabla comparativa
    comparison_df = solver.compare_solutions()
    
    print("\n" + comparison_df.to_string(index=False))
    
    # Guardar en CSV
    output_file = PROJECT_DIR / "location_comparison.csv"
    comparison_df.to_csv(output_file, index=False, encoding="utf-8")
    print(f"\n✓ Tabla guardada en: {output_file}")


def example_analyze_method(method: LocationMethod):
    """Ejemplo 3: Análisis detallado de un método."""
    print("\n" + "=" * 70)
    print(f"EJEMPLO 3: Análisis Detallado - {method.value.replace('_', ' ').title()}")
    print("=" * 70)
    
    # Cargar datos
    data_dir = PROJECT_DIR / "data"
    dataset = load_dataset(
        str(data_dir / "poblacion.csv"),
        str(data_dir / "rutasDistTiempo.csv"),
    )
    
    # Resolver
    solver = LocationSolver(dataset)
    result = solver.solve(method)
    
    # Calcular distancias desde la ubicación óptima
    R = 6371  # Radio de la Tierra en km
    lat1 = np.radians(result.latitude)
    lon1 = np.radians(result.longitude)
    lat2 = np.radians(dataset.latitudes)
    lon2 = np.radians(dataset.longitudes)
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    distances_km = R * c
    
    # Municipios de demanda (población > 0)
    is_demand = dataset.poblacion > 0
    
    # Crear tabla de análisis
    analysis_data = {
        "Municipio": [dataset.names[i] for i in range(len(dataset.names)) if is_demand[i]],
        "Población": [dataset.poblacion[i] for i in range(len(dataset.names)) if is_demand[i]],
        "Latitud": [dataset.latitudes[i] for i in range(len(dataset.names)) if is_demand[i]],
        "Longitud": [dataset.longitudes[i] for i in range(len(dataset.names)) if is_demand[i]],
        "Distancia (km)": [distances_km[i] for i in range(len(dataset.names)) if is_demand[i]],
    }
    
    analysis_df = pd.DataFrame(analysis_data)
    analysis_df["Ponderado"] = analysis_df["Población"] * analysis_df["Distancia (km)"]
    analysis_df = analysis_df.sort_values("Distancia (km)", ascending=False)
    
    print("\n📊 Municipios más lejanos:")
    print(analysis_df.head(10).to_string(index=False))
    
    print("\n📊 Municipios más cercanos:")
    print(analysis_df.tail(10).to_string(index=False))
    
    # Estadísticas agregadas
    print(f"\n📈 Estadísticas de distancia:")
    print(f"   - Promedio: {analysis_df['Distancia (km)'].mean():.2f} km")
    print(f"   - Mediana: {analysis_df['Distancia (km)'].median():.2f} km")
    print(f"   - Mínima: {analysis_df['Distancia (km)'].min():.2f} km")
    print(f"   - Máxima: {analysis_df['Distancia (km)'].max():.2f} km")
    print(f"   - Desv. Estándar: {analysis_df['Distancia (km)'].std():.2f} km")
    
    print(f"\n📊 Estadísticas de población:")
    print(f"   - Total demanda: {analysis_df['Población'].sum():,} hab")
    
    # Cobertura por radio
    print(f"\n🎯 Cobertura de población por distancia:")
    for radius in [25, 50, 75, 100, 150, 200]:
        covered = (analysis_df["Distancia (km)"] <= radius).sum()
        covered_pop = analysis_df[analysis_df["Distancia (km)"] <= radius]["Población"].sum()
        pct = 100 * covered_pop / analysis_df["Población"].sum()
        print(f"   - Dentro de {radius:3d} km: {covered:3d} municipios, {pct:5.1f}% población")
    
    # Guardar análisis detallado
    output_file = PROJECT_DIR / f"location_analysis_{method.value}.csv"
    analysis_df.to_csv(output_file, index=False, encoding="utf-8")
    print(f"\n✓ Análisis detallado guardado en: {output_file}")


def example_coverage_analysis():
    """Ejemplo 4: Análisis de cobertura de población."""
    print("\n" + "=" * 70)
    print("EJEMPLO 4: Análisis de Cobertura")
    print("=" * 70)
    
    # Cargar datos
    data_dir = PROJECT_DIR / "data"
    dataset = load_dataset(
        str(data_dir / "poblacion.csv"),
        str(data_dir / "rutasDistTiempo.csv"),
    )
    
    # Comparar cobertura de todos los métodos
    solver = LocationSolver(dataset)
    
    print(f"\n{'Método':<30} {'50km':<12} {'100km':<12} {'150km':<12} {'200km':<12}")
    print("-" * 70)
    
    for method in LocationMethod:
        result = solver.solve(method)
        
        # Calcular distancias
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
        
        is_demand = dataset.poblacion > 0
        total_pop = dataset.poblacion[is_demand].sum()
        
        coverage_50 = 100 * dataset.poblacion[is_demand][distances_km[is_demand] <= 50].sum() / total_pop
        coverage_100 = 100 * dataset.poblacion[is_demand][distances_km[is_demand] <= 100].sum() / total_pop
        coverage_150 = 100 * dataset.poblacion[is_demand][distances_km[is_demand] <= 150].sum() / total_pop
        coverage_200 = 100 * dataset.poblacion[is_demand][distances_km[is_demand] <= 200].sum() / total_pop
        
        method_name = method.value.replace("_", " ").title()
        print(f"{method_name:<30} {coverage_50:>10.1f}% {coverage_100:>10.1f}% {coverage_150:>10.1f}% {coverage_200:>10.1f}%")


def main():
    """Ejecuta todos los ejemplos."""
    print("\n" + "🔍 EJEMPLOS DE USO - MÓDULO DE LOCALIZACIÓN " + "🔍".rjust(30))
    print("=" * 70)
    
    try:
        # Ejemplo 1: Uso básico
        example_basic_usage()
        
        # Ejemplo 2: Comparar todas las técnicas
        example_compare_all_methods()
        
        # Ejemplo 3: Análisis detallado
        example_analyze_method(LocationMethod.MIN_TOTAL_DISTANCE)
        
        # Ejemplo 4: Análisis de cobertura
        example_coverage_analysis()
        
        print("\n" + "=" * 70)
        print("✓ Todos los ejemplos completados exitosamente")
        print("=" * 70 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
