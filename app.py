# app.py
from flask import Flask, render_template, request, send_file, make_response
import pandas as pd
import os
import io

# Importar funciones desde otros módulos
try:
    from utils import (
        conectar_sql_server,
        listar_bases_datos,
        listar_tablas,
        leer_tabla_completa,
        leer_estructura_completa
    )
    from normalizacion import (
        esta_en_1fn,
        aplicar_1fn,
        extraer_dependencias,
        obtener_pk,
        tiene_dependencia_parcial,
        aplicar_2fn,
        tiene_dependencia_transitiva
    )
except Exception as e:
    print(f"❌ Error al importar módulos: {e}")

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
    modo = request.form.get('modo', 'conexion')  # 'conexion' o 'archivos'

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
                                       tablas=tablas,
                                       modo=modo)
            except Exception as e:
                print(f"❌ Error en listar_bd: {e}")
                return f"<h3>❌ Error: {e}</h3><p>Verifica la conexión a SQL Server.</p>", 500

        # --- Descargar estructura.csv (todas las tablas) ---
        elif action == 'descargar_estructura':
            try:
                conn = conectar_sql_server(server, db_name)
                if not conn:
                    return "❌ No se pudo conectar a SQL Server", 500

                df_estructura = leer_estructura_completa(conn)
                conn.close()

                if df_estructura.empty:
                    return "❌ No se pudo generar la estructura", 500

                output = io.StringIO()
                df_estructura.to_csv(output, index=False, encoding='utf-8')
                output.seek(0)

                response = make_response(output.getvalue())
                response.headers["Content-Disposition"] = "attachment; filename=estructura_completa.csv"
                response.headers["Content-Type"] = "text/csv; charset=utf-8"
                return response

            except Exception as e:
                print(f"❌ Error en descargar_estructura: {e}")
                return f"❌ Error interno: {e}", 500

        # --- Descargar datos (todos en un solo CSV) ---
        elif action == 'descargar_datos':
            try:
                conn = conectar_sql_server(server, db_name)
                if not conn:
                    return "❌ No se pudo conectar a SQL Server", 500

                tablas = listar_tablas(conn)
                if not tablas:
                    conn.close()
                    return "❌ No se encontraron tablas", 500

                registros = []
                for tabla in tablas:
                    try:
                        df = leer_tabla_completa(conn, tabla)
                        if not df.empty:
                            df['__tabla'] = tabla
                            registros.append(df)
                    except Exception as e:
                        print(f"❌ Error leyendo {tabla}: {e}")

                conn.close()

                if not registros:
                    return "❌ No se pudieron leer los datos", 500

                df_datos = pd.concat(registros, ignore_index=True)
                output = io.StringIO()
                df_datos.to_csv(output, index=False, encoding='utf-8')
                output.seek(0)

                response = make_response(output.getvalue())
                response.headers["Content-Disposition"] = "attachment; filename=datos_completos.csv"
                response.headers["Content-Type"] = "text/csv; charset=utf-8"
                return response

            except Exception as e:
                print(f"❌ Error en descargar_datos: {e}")
                return f"❌ Error interno: {e}", 500

        # --- Analizar base de datos conectada ---
        elif action == 'analizar_bd':
            try:
                conn = conectar_sql_server(server, db_name)
                if not conn:
                    return "❌ No se pudo conectar a SQL Server", 500

                df_estructura = leer_estructura_completa(conn)
                dependencias = extraer_dependencias(df_estructura)

                tablas = listar_tablas(conn)
                resultados = []

                for tabla in tablas:
                    try:
                        df = leer_tabla_completa(conn, tabla)
                        if df.empty:
                            continue
                        df.name = tabla

                        # 1FN
                        if not esta_en_1fn(df):
                            fn1 = "❌ No está en 1FN"
                        else:
                            fn1 = "✅ En 1FN"

                        # 2FN
                        pk = obtener_pk(df_estructura, tabla)
                        deps = dependencias.get(tabla, [])
                        if tiene_dependencia_parcial(df, pk, deps):
                            fn2 = "❌ No está en 2FN"
                        else:
                            fn2 = "✅ En 2FN"

                        # 3FN
                        if tiene_dependencia_transitiva(deps):
                            fn3 = "❌ No está en 3FN"
                        else:
                            fn3 = "✅ En 3FN"

                        resultados.append({
                            'tabla': tabla,
                            '1FN': fn1,
                            '2FN': fn2,
                            '3FN': fn3
                        })
                    except Exception as e:
                        print(f"❌ Error analizando {tabla}: {e}")
                        resultados.append({
                            'tabla': tabla,
                            '1FN': 'Error',
                            '2FN': 'Error',
                            '3FN': 'Error'
                        })

                conn.close()
                analisis = pd.DataFrame(resultados).to_html(classes="table table-striped table-hover", index=False, escape=False)

                return render_template('index.html',
                                       server=server,
                                       db_name=db_name,
                                       tablas=tablas,
                                       analisis=analisis,
                                       modo=modo)

            except Exception as e:
                print(f"❌ Error en analizar_bd: {e}")
                return f"❌ Error interno: {e}", 500

        # --- Analizar archivos CSV subidos ---
        elif action == 'analizar_archivos':
            try:
                archivo_estructura = request.files.get('estructura')
                archivo_datos = request.files.get('datos')

                if not archivo_estructura or not archivo_datos:
                    return "❌ Faltan archivos: estructura.csv y datos.csv", 400

                # ✅ CORRECCIÓN CLAVE: Usa engine='python' para manejar comas en campos entre comillas
                df_estructura = pd.read_csv(archivo_estructura, engine='python', encoding='utf-8')
                df_datos = pd.read_csv(archivo_datos, engine='python', encoding='utf-8')

                # Validación básica
                expected_cols_estructura = ['tabla', 'atributo', 'tipo', 'llave', 'dependencia_funcional(A→B)']
                if not all(col in df_estructura.columns for col in expected_cols_estructura):
                    return f"❌ Estructura CSV inválida. Se esperan: {expected_cols_estructura}", 400

                if df_estructura.empty or df_datos.empty:
                    return "❌ Los archivos están vacíos", 400

                # Procesar análisis por tabla
                if '__tabla' in df_datos.columns:
                    tablas = df_datos['__tabla'].unique()
                else:
                    tablas = ['DatosAnalizados']

                dependencias = extraer_dependencias(df_estructura)
                resultados = []

                for tabla in tablas:
                    try:
                        df = df_datos[df_datos['__tabla'] == tabla] if '__tabla' in df_datos.columns else df_datos
                        df.name = tabla

                        # 1FN
                        if not esta_en_1fn(df):
                            fn1 = "❌ No está en 1FN"
                        else:
                            fn1 = "✅ En 1FN"

                        # 2FN
                        pk = obtener_pk(df_estructura, tabla)
                        deps = dependencias.get(tabla, [])
                        if tiene_dependencia_parcial(df, pk, deps):
                            fn2 = "❌ No está en 2FN"
                        else:
                            fn2 = "✅ En 2FN"

                        # 3FN
                        if tiene_dependencia_transitiva(deps):
                            fn3 = "❌ No está en 3FN"
                        else:
                            fn3 = "✅ En 3FN"

                        resultados.append({
                            'tabla': tabla,
                            '1FN': fn1,
                            '2FN': fn2,
                            '3FN': fn3
                        })
                    except Exception as e:
                        print(f"❌ Error analizando {tabla}: {e}")
                        resultados.append({
                            'tabla': tabla,
                            '1FN': 'Error',
                            '2FN': 'Error',
                            '3FN': 'Error'
                        })

                analisis = pd.DataFrame(resultados).to_html(classes="table table-striped table-hover", index=False, escape=False)

                return render_template('index.html', analisis=analisis, modo=modo)

            except pd.errors.ParserError as e:
                print(f"❌ Error de parsing CSV: {e}")
                return f"❌ Error al leer el archivo CSV. Asegúrate de que las comas dentro de campos estén entre comillas.", 400
            except Exception as e:
                print(f"❌ Error en analizar_archivos: {e}")
                return f"❌ Error interno: {str(e)}", 500

    return render_template('index.html',
                           server=server,
                           bases_datos=bases_datos,
                           db_name=db_name,
                           tablas=tablas,
                           modo=modo)


if __name__ == '__main__':
    import webbrowser
    import threading

    def open_browser():
        webbrowser.open("http://127.0.0.1:5000")

    threading.Timer(2.0, open_browser).start()
    
    app.run(debug=True, host='127.0.0.1', port=5000)