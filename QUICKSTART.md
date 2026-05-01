# GUÍA DE INICIO RÁPIDO - Módulo de Localización

## 🚀 ¡Comenzar en 3 pasos!

### Paso 1: Instalar dependencias
```bash
pip install scipy plotly
```

### Paso 2: Ejecutar la interfaz Streamlit
```bash
streamlit run app.py
```

### Paso 3: Seleccionar problema
En la aplicación web que se abre:
1. Selecciona el radio button: **"Localización de Centro"**
2. Elige entre:
   - **"Solución Única"** → Muestra una técnica específica
   - **"Comparar Técnicas"** → Compara todas las 5 técnicas

---

## 📊 Ejemplos de Uso

### Ejemplo 1: Ver una solución única
```bash
# Desde Streamlit
# 1. Elige "Solución Única"
# 2. Selecciona "Minimización de Distancia Total" en el desplegable
# 3. Observa:
#    - Ubicación óptima (lat/lon)
#    - Municipio más cercano
#    - Mapa interactivo
#    - Gráficos de cobertura
```

### Ejemplo 2: Comparar todas las técnicas
```bash
# Desde Streamlit
# 1. Elige "Comparar Técnicas"
# 2. Observa:
#    - Tabla comparativa de todas las 5 técnicas
#    - Mapa con todas las ubicaciones superpuestas
#    - Análisis de desempeño
```

### Ejemplo 3: Usar desde Python
```bash
python example_location_usage.py
```
Esto ejecuta 4 ejemplos completos y genera archivos CSV con los análisis.

---

## 📁 Estructura de Archivos

```
vrp_tiempo_svq1/
├── app.py                          ← Aplicación Streamlit (MODIFICADA)
├── example_location_usage.py       ← Ejemplos ejecutables (NUEVO)
├── REFACTORING_SUMMARY.md          ← Este resumen (NUEVO)
├── LOCATION_MODULE_README.md       ← Documentación completa (NUEVO)
├── src/
│   ├── location_solver.py          ← Motor de cálculo (NUEVO)
│   ├── location_view.py            ← Visualización (NUEVO)
│   ├── vrp_solver.py               ← VRP (ORIGINAL)
│   ├── data_loader.py              ← Carga de datos
│   └── ...
├── data/
│   ├── poblacion.csv               ← Datos de municipios
│   └── rutasDistTiempo.csv         ← Matriz de distancias
└── ...
```

---

## 🎯 Las 5 Técnicas de Localización

| # | Técnica | Cuándo Usar | Velocidad | Precisión |
|---|---------|------------|-----------|-----------|
| 1️⃣ | Centro de Gravedad | Análisis rápido | ⚡ Muy rápido | ⭐ Básica |
| 2️⃣ | Min Total Distance | **Recomendado** | ⚡⚡ Rápido | ⭐⭐⭐ Óptimo |
| 3️⃣ | Minimax | Equidad/Fairness | ⚡⚡ Rápido | ⭐⭐⭐ Óptimo |
| 4️⃣ | Geographic Center | Referencia | ⚡ Muy rápido | ⭐⭐ Media |
| 5️⃣ | k-Mediana | Multi-depósito | ⚡⚡⚡ Lento | ⭐⭐⭐ Óptimo |

**Recomendación:** Comienza con "Min Total Distance" para la mayoría de casos.

---

## 📊 Qué Esperar

### Entrada
- 120 municipios de Sevilla
- Población total: 3.6 millones de habitantes
- Distancias Haversine entre municipios

### Salida
- **Ubicación óptima** (latitud, longitud WGS84)
- **Municipio más cercano** y distancia
- **Métricas de cobertura** por radio (25, 50, 75, 100, 150, 200 km)
- **Análisis de desempeño** (distancia total/máxima ponderada)
- **Gráficos interactivos** (mapa, cobertura, distancias)

---

## 💡 Preguntas Frecuentes

### P: ¿Cuál es la diferencia entre Min Total Distance y Minimax?
**R:** 
- **Min Total Distance:** Minimiza el promedio ponderado. Buena para minimizar costos generales.
- **Minimax:** Minimiza la distancia máxima. Buena para equidad (nadie está muy lejos).

### P: ¿Por qué algunos municipios están a 200 km?
**R:** El dataset incluye Granada, Málaga, Córdoba que están en el sur/este de Andalucía. Son ciudades grandes con alta demanda, por eso se incluyen.

### P: ¿Puedo usar solo Localización sin VRP?
**R:** Sí. Selecciona "Localización de Centro" en el radio button principal.

### P: ¿Cómo integro la ubicación óptima con VRP?
**R:** La ubicación óptima encontrada puede usarse como nuevo depósito en VRP. Ver `LOCATION_MODULE_README.md` para detalles.

### P: ¿Puedo agregar más municipios?
**R:** Sí. Edita `data/poblacion.csv` y `data/rutasDistTiempo.csv`.

---

## 🔧 Troubleshooting

### Error: "No module named 'scipy'"
```bash
pip install scipy
```

### Error: "No module named 'plotly'"
```bash
pip install plotly
```

### Streamlit no abre navegador
```bash
streamlit run app.py --logger.level=debug
# La URL estará en la terminal, cópiala al navegador
```

### Cálculos muy lentos
- Usa "Solución Única" en lugar de "Comparar Técnicas"
- Min Total Distance es más rápido que Minimax

---

## 📖 Documentación Completa

Para información detallada sobre:
- **API de módulos** → `LOCATION_MODULE_README.md`
- **Ejemplos avanzados** → `example_location_usage.py`
- **Resumen ejecutivo** → `REFACTORING_SUMMARY.md`

---

## ✅ Validación

El código ha sido validado con:
- ✅ 120 municipios reales (Sevilla)
- ✅ 3.6 millones de habitantes
- ✅ 5 técnicas de localización funcionando
- ✅ Gráficos y mapas generados correctamente
- ✅ Ejemplo ejecutable completado

---

## 🎓 Próximo Paso

Ejecuta ahora:
```bash
python example_location_usage.py
```

Verás en la consola:
1. ✓ Ubicación óptima calculada
2. ✓ Tabla comparativa de técnicas
3. ✓ Análisis detallado de municipios
4. ✓ Cobertura de población por distancia
5. ✓ CSV guardados para análisis posterior

---

**¡Listo para usar!** 🚀

Si tienes dudas, consulta:
- `LOCATION_MODULE_README.md` - Documentación técnica
- `REFACTORING_SUMMARY.md` - Resumen ejecutivo
- `example_location_usage.py` - Ejemplos de código
