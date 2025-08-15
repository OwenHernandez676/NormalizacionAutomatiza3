# app.py
from flask import Flask, render_template, request, make_response
import pandas as pd
import os
import io

# Importamos funciones desde otros módulos
# (asegúrate de tener utils.py y normalizacion.py en la misma carpeta)
from utils import (
    conectar_sql_server,
    listar_bases_datos,
    listar_tablas,
    leer_tabla,
    leer_estructura_desde_tabla,
    crear_tabla_desde_df
)
from normalizacion import (
    esta_en_1fn,
    aplicar_1fn,
    extraer_dependencias,
    obtener_pk,
    tiene_dependencia_parcial,
    aplicar_2fn,
    tiene_dependencia_transitiva,
    aplicar_3fn
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'data/input'
app.config['OUTPUT_FOLDER'] = 'data/output'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    bases_datos = []
    tablas = []
    analisis = {}
    server = request.form.get('server', 'localhost')
    db_name = request.form.get('database')

    if request.method == 'POST':
        action = request.form.get('action')

        # --- Listar bases de datos ---
        if action == 'listar_bd':
            bases_datos = listar_bases_datos(server)
            if db_name:
                conn = conectar_sql_server(server, db_name)
                if conn:
                    tablas = listar_tablas(conn)
                    conn.close()
                return render_template('index.html',
                                       server=server,
                                       bases_datos=bases_datos,
                                       db_name=db_name,
                                       tablas=tablas)

        # --- Descargar estructura.csv ---
        elif action == 'descargar_estructura':
            conn = conectar_sql_server(server, db_name)
            if conn:
                table_name = request.form.get('tabla')
                df_estructura = leer_estructura_desde_tabla(conn, table_name)
                conn.close()

                # Generar CSV en memoria
                output = io.StringIO()
                df_estructura.to_csv(output, index=False, encoding='utf-8')
                output.seek(0)

                response = make_response(output.getvalue())
                response.headers["Content-Disposition"] = f"attachment; filename={table_name}_estructura.csv"
                response.headers["Content-Type"] = "text/csv; charset=utf-8"
                return response

        # --- Descargar datos.csv ---
        elif action == 'descargar_datos':
            conn = conectar_sql_server(server, db_name)
            if conn:
                table_name = request.form.get('tabla')
                df_datos = leer_tabla(conn, table_name)
                conn.close()

                # Generar CSV en memoria
                output = io.StringIO()
                df_datos.to_csv(output, index=False, encoding='utf-8')
                output.seek(0)

                response = make_response(output.getvalue())
                response.headers["Content-Disposition"] = f"attachment; filename={table_name}_datos.csv"
                response.headers["Content-Type"] = "text/csv; charset=utf-8"
                return response

        # --- Analizar y normalizar ---
        elif action == 'analizar_normalizar':
            # Recibir archivos CSV
            archivo_estructura = request.files['estructura']
            archivo_datos = request.files['datos']

            if not archivo_estructura or not archivo_datos:
                return "Faltan archivos", 400

            if not archivo_estructura.filename.endswith('.csv') or not archivo_datos.filename.endswith('.csv'):
                return "Solo se permiten archivos CSV", 400

            # Leer CSVs
            df_estructura = pd.read_csv(archivo_estructura)
            df_datos = pd.read_csv(archivo_datos)
            df_datos.name = "DatosAnalizados"

            # --- 1FN ---
            if not esta_en_1fn(df_datos):
                df_datos = aplicar_1fn(df_datos)
                analisis['1fn'] = "✅ Aplicada 1FN: valores descompuestos."
            else:
                analisis['1fn'] = "✅ Ya está en 1FN."

            # Extraer dependencias y PK
            dependencias = extraer_dependencias(df_estructura)
            pk = obtener_pk(df_estructura) or ['Id']

            # --- 2FN ---
            if tiene_dependencia_parcial(df_datos, pk, dependencias):
                tablas_2fn = aplicar_2fn(df_datos, dependencias, pk)
                analisis['2fn'] = "✅ Aplicada 2FN: tablas descompuestas."
            else:
                tablas_2fn = {df_datos.name: df_datos}
                analisis['2fn'] = "✅ Ya está en 2FN."

            # --- 3FN ---
            tablas_3fn, msg_3fn = aplicar_3fn(tablas_2fn, dependencias)
            analisis['3fn'] = msg_3fn

            # Guardar resultados normalizados
            for nombre, tabla in tablas_3fn.items():
                path = os.path.join(app.config['OUTPUT_FOLDER'], f"{nombre}.csv")
                tabla.to_csv(path, index=False)

            # Subir a SQL Server si se especifica
            if db_name:
                conn = conectar_sql_server(server, db_name)
                if conn:
                    for nombre, tabla in tablas_3fn.items():
                        crear_tabla_desde_df(conn, nombre, tabla)
                    conn.close()
                    analisis['sql'] = f"✅ Tablas normalizadas subidas a {db_name}"

            # Preparar vista previa
            datos_html = df_datos.head(50).to_html(classes="table table-striped table-hover", index=False)
            estructura_html = df_estructura.head(10).to_html(classes="table table-sm", index=False)

            return render_template('index.html',
                                   server=server,
                                   db_name=db_name,
                                   tablas=tablas,
                                   datos=datos_html,
                                   estructura=estructura_html,
                                   analisis=analisis)

    return render_template('index.html',
                           server=server,
                           bases_datos=bases_datos,
                           db_name=db_name,
                           tablas=tablas)

# === Ejecución automática con apertura de navegador ===
if __name__ == '__main__':
    import webbrowser
    import threading

    def open_browser():
        webbrowser.open("http://127.0.0.1:5000")

    # Abre el navegador 2 segundos después de que el servidor inicie
    threading.Timer(2.0, open_browser).start()

    # Inicia Flask sin modo debug (para evitar doble ejecución)
    app.run(debug=False, host='127.0.0.1', port=5000)