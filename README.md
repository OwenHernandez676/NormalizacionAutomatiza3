# Normalizaci-nAutomatizada
# Proyecto I - Normalización Automatizada

Este proyecto tiene como objetivo automatizar el proceso de **normalización de bases de datos** a partir de un conjunto de datos proporcionado en un archivo plano (como `.csv` .) o mediante conexión a una base de datos SQL Server.

## 📌 Objetivo General

Desarrollar una aplicación web que permita:
1. Cargar una estructura de base de datos desde archivo o conexión.
2. Analizar si está normalizada (1FN, 2FN, 3FN).
3. Transformarla automáticamente a la forma normal siguiente.
4. Visualizar las nuevas entidades/tablas normalizadas mediante un **script SQL** generado automáticamente.

## 🗂️ Estructura del Proyecto

```
/templates         # Archivos HTML
/static            # Archivos estáticos (CSS, JS)
/uploads           # Archivos subidos por el usuario
/scripts           # Funciones de análisis y transformación
/app.py            # Aplicación principal en Flask
```

## 🚧 Ramas de desarrollo sugeridas

- `read-file-template` → Lectura y validación del archivo de entrada (.csv/.xlsx)
- `analyzer-fn` → Análisis automático de formas normales (1FN, 2FN, 3FN)
- `transform-fn` → Transformación estructural hacia 1FN, 2FN y 3FN
- `visualizer-output` → Esquema visual de las entidades resultantes
- `sql-generator` → Generador de scripts SQL
- `ui-front` → Interfaz web con carga, ejecución y visualización
- `db-connector` → Módulo para conexión con base de datos (opcional)

## 👥 Distribución sugerida (ejemplo)

- Integrante 1: Template y lectura de archivo
- Integrante 2: Análisis de formas normales
- Integrante 3: Transformación de datos
- Integrante 4: Visualización y generación de script
- Integrante 5: Interfaz web y pruebas finales

## ✅ Entregables

| Semana | Avance |
|--------|--------|
| Semana 1 | Template definido, carga de archivo funcional |
| Semana 2 | Análisis y transformación, visualización de resultados |

## 🛠️ Tecnologías sugeridas

- Python 3.x
- Flask
- Pandas
- HTML/CSS/JS
- Mermaid.js o Graphviz (para esquemas)
- SQL Server (con `pyodbc` para conexiones opcionales)

---
 