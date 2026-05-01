# Refactorización: Localización vs Asignación de Rutas

## Overview

El proyecto ha sido refactorizado para separar en dos módulos principales:

1. **Localización de Centro de Reparto**: Calcula la ubicación óptima para un nuevo centro de distribución
2. **Asignación de Rutas (VRP)**: Resuelve el problema de ruteo de vehículos (funcionalidad existente)

## Archivos Nuevos

### `src/location_solver.py`
Motor de cálculo de localización con múltiples técnicas de optimización.

**Clases principales:**
- `LocationMethod`: Enum con las técnicas disponibles
- `LocationResult`: Dataclass con los resultados de una localización
- `LocationSolver`: Clase principal que ejecuta los algoritmos

**Técnicas de localización disponibles:**

1. **Centro de Gravedad Ponderado** (`GRAVITY_CENTER`)
   - Cálculo simple: media ponderada por población
   - Rápido, ideal para análisis iniciales
   - Fórmula: $\text{ubicación} = \frac{\sum \text{población}_i \times \text{coordenada}_i}{\sum \text{población}_i}$

2. **Minimización de Distancia Total** (`MIN_TOTAL_DISTANCE`)
   - Minimiza la suma ponderada de distancias: $\min \sum \text{población}_i \times d_i$
   - Usa optimización numérica (scipy.optimize.minimize)
   - Equivalente a `fminunc` en MATLAB
   - Óptimo desde la perspectiva de servicio promedio

3. **Minimax** (`MINIMAX`)
   - Minimiza la distancia máxima ponderada
   - Fórmula: $\min_{x,y} \max_i (\text{población}_i \times d_i)$
   - Enfoque de equidad: minimiza el servicio al peor cliente
   - Equivalente a `fminimax` en MATLAB

4. **Centro Geográfico Simple** (`GEOGRAPHIC_CENTER`)
   - Media simple sin ponderación por población
   - Útil para comparación
   - Fórmula: $\text{ubicación} = \frac{\sum \text{coordenada}_i}{n}$

5. **k-Mediana** (`K_MEDIAN`)
   - Agrupa municipios por proximidad y selecciona medianas ponderadas
   - Para k=1, equivalente a minimización de distancia total
   - Extensible a múltiples centros

**Uso básico:**
```python
from src.data_loader import load_dataset
from src.location_solver import LocationSolver, LocationMethod

# Cargar datos
dataset = load_dataset("data/poblacion.csv", "data/rutasDistTiempo.csv")

# Crear solver
solver = LocationSolver(dataset)

# Resolver con un método específico
result = solver.solve(LocationMethod.MIN_TOTAL_DISTANCE)

# O comparar todos los métodos
comparison = solver.compare_solutions()  # Retorna DataFrame
```

### `src/location_view.py`
Módulo de visualización interactiva para resultados de localización.

**Funciones principales:**

- `build_location_map(dataset, result, show_distance_rings, include_hubs)`
  - Crea mapa Folium con la ubicación óptima y municipios de demanda
  - Opcional: anillos de distancia concéntricos (50, 100, 150 km)
  - Marca centros logísticos (SVQ1, DQA4)

- `build_comparison_map(dataset, solutions)`
  - Superpone todas las soluciones en un solo mapa
  - Cada método con color distinto
  - Útil para comparar técnicas

- `create_distance_heatmap(dataset, result)`
  - Gráfico de barras: distancia desde ubicación óptima a cada municipio
  - Ordenado de mayor a menor distancia

- `create_population_coverage_chart(dataset, result, distance_thresholds)`
  - Gráfico de cobertura: % de población dentro de cada radio
  - Por defecto: 25, 50, 75, 100, 150, 200 km

- `render_location_results(dataset, result)`
  - Panel completo en Streamlit con métricas, mapas y gráficos

- `render_comparison_view(dataset, solver)`
  - Comparativa de todas las técnicas
  - Tabla, mapa unificado, y análisis de desempeño

## Cambios en `app.py`

### Nueva Estructura

Al iniciar la aplicación, aparece un **selector principal**:

```
---
**SELECCIONA EL PROBLEMA A RESOLVER:**
○ Asignación de Rutas (VRP)      ○ Localización de Centro
---
```

### Si se selecciona "Localización de Centro"

Se muestra una interfaz con:

1. **Radio buttons de vista:**
   - "Solución Única": Muestra una técnica elegida
   - "Comparar Técnicas": Compara todas las técnicas lado a lado

2. **Si "Solución Única":**
   - Desplegable para elegir la técnica
   - Métricas de la solución (lat/lon/municipio más cercano/distancias)
   - Mapa interactivo con municipios y ubicación óptima
   - Gráficos de cobertura y distancias

3. **Si "Comparar Técnicas":**
   - Tabla comparativa con todos los métodos
   - Mapa unificado con todas las ubicaciones
   - Análisis detallado de desempeño

### Si se selecciona "Asignación de Rutas (VRP)"

Aparece la interfaz original sin cambios:
- Panel de configuración
- Botón "Resolver VRP"
- Pantalla principal + navegación entre vistas

## Datos de Entrada

### `data/poblacion.csv`

Formato (CSV con semicolon separator):
```
Municipio;Población;Latitud (Y);Longitud (X);Restringe camion
SVQ1;0;37.27286595;-5.989369203;0
DQA4;0;37.34766449;-5.99895956;0
Aguadulce;2109;37.253;-4.993;0
...
```

**Notas:**
- SVQ1 y DQA4 son centros logísticos (población=0)
- Se incluyen como referencias pero no se cuentan en demanda
- Todas las coordenadas en WGS84 (lat/lon)

### `data/rutasDistTiempo.csv`

Matriz OD con distancias (km) y tiempos (min):
```
origen_id;destino_id;distancia_km;tiempo_min
0;1;125.34;85
...
```

## Métricas de Salida

Para cada solución de localización se calcula:

- **Latitud/Longitud**: Coordenadas WGS84 de la ubicación óptima
- **Municipio Más Cercano**: Nombre del municipio más próximo
- **Distancia al Municipio (km)**: Distancia Haversine al municipio más cercano
- **Distancia Total Ponderada**: $\sum \text{población}_i \times d_i$ (métrica global)
- **Distancia Máxima Ponderada**: $\max_i (\text{población}_i \times d_i)$ (peor cliente)

## Ejemplo de Uso

### Desde la interfaz Streamlit

```bash
streamlit run app.py
```

1. Selecciona "Localización de Centro"
2. Elige "Comparar Técnicas"
3. Observa la tabla y mapa comparativo
4. Selecciona "Solución Única"
5. Elige "Minimización de Distancia Total"
6. Explora los resultados detallados

### Desde Python

```python
from src.data_loader import load_dataset
from src.location_solver import LocationSolver, LocationMethod
import pandas as pd

# Cargar datos
dataset = load_dataset("data/poblacion.csv", "data/rutasDistTiempo.csv")

# Crear solver
solver = LocationSolver(dataset)

# Obtener todas las soluciones
solutions = solver.get_all_solutions()

# Comparar en tabla
comparison_df = solver.compare_solutions()
print(comparison_df)

# Acceder a resultado específico
result_min_dist = solutions[LocationMethod.MIN_TOTAL_DISTANCE.value]
print(f"Ubicación óptima: ({result_min_dist.latitude}, {result_min_dist.longitude})")
print(f"Municipio más cercano: {result_min_dist.nearest_municipality}")
```

## Notas Técnicas

### Cálculo de Distancias

Se usa la fórmula **Haversine** para distancias geodésicas precisas:

$$d = 2R \arcsin\left(\sqrt{\sin^2\left(\frac{\Delta\text{lat}}{2}\right) + \cos(\text{lat}_1)\cos(\text{lat}_2)\sin^2\left(\frac{\Delta\text{lon}}{2}\right)}\right)$$

donde $R = 6371$ km (radio de la Tierra).

### Optimización Numérica

- **Método:** `scipy.optimize.minimize` con algoritmo Nelder-Mead
- **Punto inicial:** Centro de gravedad ponderado
- **Máximo de iteraciones:** 10,000
- **Precisión:** Convergencia automática

### Alternativas Futuras

Posibles extensiones:
1. **Multi-depósito:** Encontrar ubicaciones de N centros simultáneamente
2. **Restricciones territoriales:** Excluir zonas o municipios
3. **Demanda temporal:** Incorporar variaciones de demanda por hora/día
4. **Análisis de accesibilidad:** Integrar datos de red vial real

## Dependencias

Nuevas dependencias requeridas:
- `scipy`: Optimización numérica
- `plotly`: Gráficos interactivos
- `folium`: Mapas
- `streamlit-folium`: Integración Folium-Streamlit

Instalar con:
```bash
pip install scipy plotly folium streamlit-folium
```

## Troubleshooting

### Error: "No module named 'scipy'"
```bash
pip install scipy
```

### Error: "No module named 'plotly'"
```bash
pip install plotly
```

### Mapa no se muestra
- Verificar conexión a internet (necesaria para tiles de OpenStreetMap)
- En entorno offline, usar `tiles='OpenStreetMap'` con caché local

### Cálculos lentos
- Los cálculos de localización son rápidos (<1s en típico)
- Si tarda mucho, verificar tamaño del dataset y recursos disponibles
- Usar "Solución Única" en lugar de "Comparar Técnicas" si es crítico

## Compatibilidad

- ✅ Python 3.8+
- ✅ Windows, Linux, macOS
- ✅ Streamlit 1.20+
- ✅ NumPy 1.20+
- ✅ Pandas 1.3+
