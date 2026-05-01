# VRP por tiempo desde SVQ1

App en Streamlit + OR-Tools que asigna nodos de entrega (Sevilla y capitales
cercanas) a una flota heterogenea (diesel + electrica) minimizando los
vehiculos usados, con la jornada maxima del conductor y el rango electrico
como restricciones duras. Incluye mapa interactivo de rutas con folium.

Este proyecto es una version **nueva y limpia** del ejercicio anterior
(`vrp_old`): no se reutiliza la logica volumetrica, solo se han tomado como
referencia los patrones de carga de CSV, modelado OR-Tools y estructura de UI.

---

## Estructura del proyecto

```
vrp_tiempo_svq1/
├── app.py                       # Entrypoint Streamlit (sidebar + metricas + tabla + mapa)
├── requirements.txt
├── setup.bat / run.bat          # Scripts Windows para venv y arranque
├── data/
│   ├── poblacion.csv            # Municipios y poblacion (122 nodos: SVQ1, DQA4, 120 municipios/provincias)
│   └── rutasDistTiempo.csv      # Matriz OD km y minutos (122x122 nodos, sincronizada con poblacion.csv)
├── src/
│   ├── data_loader.py           # Carga y validacion de los 2 CSVs sincronizados
│   ├── demand.py                # Calculo de paquetes y tiempo de servicio
│   ├── split_delivery.py        # Preprocesado de nodos que no caben en jornada
│   ├── fleet.py                 # FleetConfig: cotas y tipos diesel/electrica
│   ├── vrp_solver.py            # OR-Tools con dimension tiempo + dimension distancia (electricas)
│   ├── map_view.py              # Construccion del mapa folium con rutas
│   └── pipeline.py              # Orquestacion: carga -> demanda -> split -> solver
├── tests/
│   └── test_pipeline.py         # Tests rapidos sin OR-Tools
└── docs/
    └── (espacio reservado para diagramas o notas)
```

---

## Instalacion

### Windows (recomendado)

Hay dos scripts listos para usar:

```bat
setup.bat   :: crea .venv con Python 3.11 e instala dependencias
run.bat     :: activa .venv y arranca Streamlit
```

`setup.bat` busca primero `py -3.11`, luego `py -3.10`, y por ultimo cualquier
`python` del PATH. OR-Tools tiene ruedas precompiladas para 3.10 y 3.11; en
versiones mas nuevas puede tardar mas o no instalar.

### Linux / macOS

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Ejecucion

```bat
:: Windows
run.bat
```

```bash
# Linux / macOS
streamlit run app.py
```

Por defecto la app:

1. Carga los CSV/XLSX desde la carpeta `data/`.
2. Construye un dataset unificado de 121 nodos (los 117 originales + Cadiz,
   Malaga, Cordoba y Huelva).
3. Calcula paquetes y tiempo nodal a partir de los parametros del sidebar.
4. Aplica el split-delivery: cualquier nodo cuya entrega completa no quepa en
   la jornada genera tantas rutas dedicadas como haga falta.
5. Optimiza el resto con OR-Tools usando una dimension de tiempo.

---

## Supuestos de calculo

- **Paquetes por nodo**: `paquetes = round(poblacion * penetracion)`. El
  deposito SVQ1 (y DQA4 si aparece) tienen 0 paquetes.
- **Tiempo nodal de servicio**: `paquetes * (servicio_por_paquete + tiempo_entre_paquetes)`.
  Por defecto se asume que el tiempo entre paquetes captura la conduccion
  intra-municipio, asi que el solver no vuelve a sumarlo.
- **Stem time** (de y hacia el deposito): se toma directamente de
  `rutasDistTiempo.csv` para los nodos originales. Para los 4 nodos nuevos se
  estima a partir de la distancia del XLSX y la velocidad mediana observada
  para distancias > 50 km en el CSV (alrededor de 70 km/h).
- **Tiempos de servicio en split**: cada ruta dedicada paga el tiempo de
  servicio proporcional a los paquetes que entrega (es la opcion conservadora;
  si quisieras descontarlo solo una vez basta con cambiar
  `compute_node_service_time`).
- **Flota heterogenea**: por defecto 75 furgonetas diesel + 45 electricas
  (total 120, segun datos DQA4 del enunciado). Las electricas tienen un
  rango maximo por jornada (180 km por defecto) como restriccion dura. El
  solver elige la mezcla optima dentro de las cotas, prefiriendo electricas
  cuando caben (coste fijo ligeramente menor) y minimizando el numero
  total de vehiculos activos.

---

## Interpretacion de resultados

- **Rutas dedicadas**: numero de viajes deposito-nodo-deposito generados por
  el split-delivery, uno por cada chunk de paquetes que no cabe en jornada
  combinada con otros nodos.
- **Rutas VRP**: vehiculos que el solver OR-Tools usa para cubrir la demanda
  residual.
- **Tiempo total**: suma de jornadas (viaje + servicio) sobre todos los
  vehiculos, util para auditar uso global.
- **Tabla de asignacion**: una fila por vehiculo con la lista ordenada de
  nodos visitados, paquetes entregados y desglose de tiempos.

---

## Limites del MVP

- No considera ventanas horarias del cliente ni restricciones de tipo de
  vehiculo (camion vs furgoneta). El campo `Restringe camion` del CSV se carga
  pero todavia no se usa como restriccion en el solver.
- El mapa dibuja **lineas rectas** entre nodos, no rutas reales por carretera.
  Es suficiente para visualizacion a alto nivel.
- El rango electrico se modela como una distancia maxima por jornada, sin
  contemplar recargas intermedias.
- La estimacion de tiempo para los 4 nodos nuevos es heuristica (km / velocidad
  media). Si en el futuro se obtiene una matriz de tiempos real para esas
  capitales, basta con anadirla a `distanciasReales.xlsx` o sustituir el CSV.
- El solver minimiza el numero de vehiculos via fixed-cost; no compara con un
  optimo demostrable. Si la jornada es muy ajustada puede no encontrar
  solucion: en ese caso, sube la jornada o reduce la penetracion.

---

## Tests rapidos

```bat
:: Windows (con .venv activado)
python tests\test_pipeline.py
```

```bash
# Linux / macOS
python3 tests/test_pipeline.py
```

Verifica que:

- El dataset se carga con los 121 nodos esperados.
- Los paquetes y tiempos se calculan correctamente.
- El split-delivery genera rutas dedicadas para Malaga, Cordoba y Huelva con
  parametros de ejemplo, sin exceder nunca la jornada maxima.

Estos tests no requieren OR-Tools (solo pandas/numpy/openpyxl).
