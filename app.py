# app.py
from flask import Flask, render_template, request, make_response
import pandas as pd
import os
import io

# Importar funciones
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
            try:
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
            except Exception as e:
                print(f"❌ Error listando BD: {e}")
                return f"Error: {e}", 500

        # --- Descargar estructura.csv ---
        elif action == 'descargar_estructura':
            try:
                if not db_name or not request.form.get('tabla'):
                    return "Base de datos o tabla no especificada", 400

                table_name = request.form.get('tabla').strip()
                conn = conectar_sql_server(server, db_name)
                if not conn:
                    return "No se pudo conectar a SQL Server", 500

                df_estructura = leer_estructura_desde_tabla(conn, table_name)
                conn.close()

                output = io.StringIO()
                df_estructura.to_csv(output, index=False, encoding='utf-8')
                output.seek(0)

                response = make_response(output.getvalue())
                response.headers["Content-Disposition"] = f"attachment; filename={table_name}_estructura.csv"
                response.headers["Content-Type"] = "text/csv; charset=utf-8"
                return response

            except Exception as e:
                print(f"❌ Error en descargar_estructura: {e}")
                return f"Error interno: {e}", 500

        # --- Descargar datos.csv ---
        elif action == 'descargar_datos':
            try:
                if not db_name or not request.form.get('tabla'):
                    return "Base de datos o tabla no especificada", 400

                table_name = request.form.get('tabla').strip()
                conn = conectar_sql_server(server, db_name)
                if not conn:
                    return "No se pudo conectar a SQL Server", 500

                df_datos = leer_tabla(conn, table_name)
                conn.close()

                output = io.StringIO()
                df_datos.to_csv(output, index=False, encoding='utf-8')
                output.seek(0)

                response = make_response(output.getvalue())
                response.headers["Content-Disposition"] = f"attachment; filename={table_name}_datos.csv"
                response.headers["Content-Type"] = "text/csv; charset=utf-8"
                return response

            except Exception as e:
                print(f"❌ Error en descargar_datos: {e}")
                return f"Error interno: {e}", 500

        # --- Analizar y normalizar ---
        elif action == 'analizar_normalizar':
            try:
                archivo_estructura = request.files['estructura']
                archivo_datos = request.files['datos']

                if not archivo_estructura or not archivo_datos:
                    return "Faltan archivos", 400

                if not archivo_estructura.filename.endswith('.csv') or not archivo_datos.filename.endswith('.csv'):
                    return "Solo se permiten archivos CSV", 400

                df_estructura = pd.read_csv(archivo_estructura)
                df_datos = pd.read_csv(archivo_datos)
                df_datos.name = "DatosAnalizados"

                # --- 1FN ---
                if not esta_en_1fn(df_datos):
                    df_datos = aplicar_1fn(df_datos)
                    analisis['1fn'] = "✅ Aplicada 1FN: valores descompuestos."
                else:
                    analisis['1fn'] = "✅ Ya está en 1FN."

                # Extraer dependencias
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

                # Guardar resultados
                for nombre, tabla in tablas_3fn.items():
                    path = os.path.join(app.config['OUTPUT_FOLDER'], f"{nombre}.csv")
                    tabla.to_csv(path, index=False)

                # Subir a SQL Server
                if db_name:
                    conn = conectar_sql_server(server, db_name)
                    if conn:
                        for nombre, tabla in tablas_3fn.items():
                            crear_tabla_desde_df(conn, nombre, tabla)
                        conn.close()
                        analisis['sql'] = f"✅ Tablas normalizadas subidas a {db_name}"

                datos_html = df_datos.head(50).to_html(classes="table table-striped table-hover", index=False)
                estructura_html = df_estructura.head(10).to_html(classes="table table-sm", index=False)

                return render_template('index.html',
                                       server=server,
                                       db_name=db_name,
                                       tablas=tablas,
                                       datos=datos_html,
                                       estructura=estructura_html,
                                       analisis=analisis)

            except Exception as e:
                print(f"❌ Error en analizar_normalizar: {e}")
                return f"Error interno: {e}", 500

    return render_template('index.html',
                           server=server,
                           bases_datos=bases_datos,
                           db_name=db_name,
                           tablas=tablas)

# === Iniciar servidor y abrir navegador ===
if __name__ == '__main__':
    import webbrowser
    import threading
    def open_browser():
        webbrowser.open("http://127.0.0.1:5000")
    threading.Timer(2.0, open_browser).start()
    app.run(debug=False, host='127.0.0.1', port=5000)