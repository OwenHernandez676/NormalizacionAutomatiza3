# app.py
from flask import Flask, render_template, request, jsonify, send_file
import pandas as pd
from io import StringIO, BytesIO
import pyodbc
import zipfile
import os

app = Flask(__name__)

# --- Conexión a SQL Server ---
def get_connection():
    try:
        return pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost;'
            'Trusted_Connection=yes;',
            autocommit=False
        )
    except Exception as e:
        raise Exception(f"Error de conexión: {e}")

def get_databases():
    conn = get_connection()
    query = "SELECT name FROM sys.databases WHERE database_id > 4"
    df = pd.read_sql(query, conn)
    conn.close()
    return df['name'].tolist()

def get_tables(database):
    conn = get_connection()
    conn.execute(f"USE [{database}]")
    query = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
    df = pd.read_sql(query, conn)
    conn.close()
    return df['TABLE_NAME'].tolist()

def get_table_structure(database, table):
    conn = get_connection()
    conn.execute(f"USE [{database}]")
    col_query = """
    SELECT 
        c.name AS atributo,
        t.name AS tipo,
        c.max_length,
        c.precision,
        c.scale,
        c.is_nullable
    FROM sys.columns c
    JOIN sys.types t ON c.user_type_id = t.user_type_id
    JOIN sys.tables tbl ON c.object_id = tbl.object_id
    WHERE tbl.name = ?
    """
    cols = pd.read_sql(col_query, conn, params=[table])

    pk_query = """
    SELECT col.name AS atributo
    FROM sys.indexes i
    JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
    JOIN sys.columns col ON ic.object_id = col.object_id AND ic.column_id = col.column_id
    JOIN sys.tables tbl ON i.object_id = tbl.object_id
    WHERE i.is_primary_key = 1 AND tbl.name = ?
    """
    pk_cols = pd.read_sql(pk_query, conn, params=[table])['atributo'].tolist()

    fk_query = """
    SELECT col.name AS atributo
    FROM sys.foreign_key_columns fkc
    JOIN sys.columns col ON fkc.parent_object_id = col.object_id AND fkc.parent_column_id = col.column_id
    JOIN sys.tables tbl ON fkc.parent_object_id = tbl.object_id
    WHERE tbl.name = ?
    """
    fk_cols = pd.read_sql(fk_query, conn, params=[table])['atributo'].tolist()

    def format_type(row):
        t = row['tipo'].upper()
        if t in ['VARCHAR', 'NVARCHAR', 'CHAR', 'NCHAR']:
            size = row['max_length']
            return f"{t}({size})" if size > 0 else f"{t}(MAX)"
        elif t == 'DECIMAL':
            return f"DECIMAL({row['precision']},{row['scale']})"
        elif t == 'INT': return 'INT'
        elif t == 'DATE': return 'DATE'
        else: return t

    cols['tipo'] = cols.apply(format_type, axis=1)
    cols['llave'] = cols['atributo'].apply(
        lambda x: 'PK' if x in pk_cols else 'FK' if x in fk_cols else ''
    )
    pk_str = ', '.join(pk_cols)
    non_key = [c for c in cols['atributo'] if c not in pk_cols and c not in fk_cols]
    dep = f"{pk_str} → {', '.join(non_key)}" if non_key else ""
    cols['dependencia_funcional(A→B)'] = dep
    cols['tabla'] = table

    conn.close()
    return cols[['tabla', 'atributo', 'tipo', 'llave', 'dependencia_funcional(A→B)']].to_dict('records'), pk_cols

def get_table_data(database, table):
    conn = get_connection()
    conn.execute(f"USE [{database}]")
    df = pd.read_sql(f"SELECT TOP 1000 * FROM [{table}]", conn)
    conn.close()
    return df

def upload_normalized_tables(database, tables_dict):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"USE [{database}]")
        for name, df in tables_dict.items():
            drop = f"IF OBJECT_ID('{name}', 'U') IS NOT NULL DROP TABLE [{name}];"
            create_cols = []
            for col, dtype in df.dtypes.items():
                if dtype == 'object': sql_type = 'NVARCHAR(MAX)'
                elif 'int' in str(dtype): sql_type = 'INT'
                elif 'float' in str(dtype): sql_type = 'DECIMAL(18,2)'
                elif 'datetime' in str(dtype): sql_type = 'DATETIME'
                else: sql_type = 'NVARCHAR(255)'
                create_cols.append(f"[{col}] {sql_type}")
            create = f"CREATE TABLE [{name}] ({', '.join(create_cols)})"
            cursor.execute(drop + create)
            for _, row in df.iterrows():
                vals = [str(v) if pd.notna(v) else None for v in row]
                placeholders = ', '.join(['?' for _ in vals])
                cursor.execute(f"INSERT INTO [{name}] VALUES ({placeholders})", vals)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise Exception(f"Error al subir: {e}")
    finally:
        conn.close()

@app.route('/')
def index():
    databases = get_databases()
    return render_template('index.html', databases=databases)

@app.route('/get_tables/<database>')
def get_tables_route(database):
    try:
        return jsonify(get_tables(database))
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_structure/<database>/<table>')
def download_structure(database, table):
    try:
        structure, _ = get_table_structure(database, table)
        df = pd.DataFrame(structure)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        return send_file(
            StringIO(csv_buffer.getvalue()),
            mimetype='text/csv',
            as_attachment=True,
            download_name='estructura.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_data/<database>/<table>')
def download_data(database, table):
    try:
        df = get_table_data(database, table)
        csv_buffer = StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        return send_file(
            StringIO(csv_buffer.getvalue()),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{table}.csv'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download_all/<database>')
def download_all(database):
    try:
        tables = get_tables(database)
        memory = BytesIO()
        with zipfile.ZipFile(memory, 'w', zipfile.ZIP_DEFLATED) as zf:
            for table in tables:
                df = get_table_data(database, table)
                csv_buffer = StringIO()
                df.to_csv(csv_buffer, index=False)
                zf.writestr(f'{table}.csv', csv_buffer.getvalue())
        memory.seek(0)
        return send_file(
            memory,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{database}_completa.zip'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

from normalizacion import analyze_table_normalization

@app.route('/analyze_db/<database>')
def analyze_db(database):
    try:
        tables = get_tables(database)
        results = {}
        for table in tables:
            try:
                structure, _ = get_table_structure(database, table)
                df_structure = pd.DataFrame(structure)
                df_data = get_table_data(database, table)
                results[table] = analyze_table_normalization(df_data, df_structure)
            except Exception as e:
                results[table] = {'error': str(e)}
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analyze_csv', methods=['POST'])
def analyze_csv():
    if 'estructura' not in request.files or 'datos' not in request.files:
        return jsonify({'error': 'Faltan archivos'}), 400
    try:
        df_estructura = pd.read_csv(request.files['estructura'].stream)
        df_datos = pd.read_csv(request.files['datos'].stream)
        result = analyze_table_normalization(df_datos, df_estructura)
        return jsonify({'tabla': 'Desde CSV', 'resultado': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/normalize_db_table', methods=['POST'])
def normalize_db_table():
    data = request.get_json()
    database = data['database']
    table = data['table']
    try:
        structure, _ = get_table_structure(database, table)
        df_structure = pd.DataFrame(structure)
        df_data = get_table_data(database, table)
        analysis = analyze_table_normalization(df_data, df_structure)
        if analysis['necesita_normalizar']:
            tables = {f"{table}_normalizada": df_data.drop_duplicates().reset_index(drop=True)}
            upload_normalized_tables(database, tables)
            return jsonify({
                'success': True,
                'message': f"Tabla normalizada y guardada como '{table}_normalizada'."
            })
        else:
            return jsonify({'success': True, 'message': 'Ya está normalizada.'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


if __name__ == '__main__':
    import webbrowser
    import threading
    def open_browser():
        webbrowser.open("http://127.0.0.1:5000")
    threading.Timer(1.0, open_browser).start()
    app.run(debug=False, host='127.0.0.1', port=5000)