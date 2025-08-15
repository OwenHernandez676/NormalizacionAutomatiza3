# utils.py
import pyodbc
import pandas as pd
from sqlalchemy import create_engine
import urllib

def conectar_sql_server(server="localhost", database=None):
    try:
        conn_str = (
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER={server};"
            f"{'DATABASE=' + database + ';' if database else ''}"
            f"Trusted_Connection=yes;"
        )
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return None

def listar_bases_datos(server):
    conn = conectar_sql_server(server)
    if not conn:
        return []
    query = "SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name"
    try:
        df = pd.read_sql(query, conn)
        conn.close()
        return df['name'].tolist()
    except Exception as e:
        print(f"❌ Error listando bases de datos: {e}")
        conn.close()
        return []

def listar_tablas(conn):
    query = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
    try:
        df = pd.read_sql(query, conn)
        return df['TABLE_NAME'].tolist()
    except Exception as e:
        print(f"❌ Error listando tablas: {e}")
        return []

def leer_tabla(conn, table_name):
    query = f"SELECT * FROM [{table_name}]"
    try:
        df = pd.read_sql(query, conn)
        df.name = table_name
        return df
    except Exception as e:
        print(f"❌ Error al leer tabla [{table_name}]: {e}")
        raise e

def leer_estructura_desde_tabla(conn, table_name):
    query_cols = f"""
    SELECT 
        c.name AS atributo,
        t.name AS tipo,
        c.max_length,
        c.precision,
        c.scale
    FROM sys.columns c
    JOIN sys.types t ON c.user_type_id = t.user_type_id
    JOIN sys.tables tbl ON c.object_id = tbl.object_id
    WHERE tbl.name = '{table_name}'
    ORDER BY c.column_id
    """
    try:
        df_cols = pd.read_sql(query_cols, conn)
    except Exception as e:
        print(f"❌ Error al obtener columnas de {table_name}: {e}")
        raise e

    # Detectar PK
    query_pk = f"""
    SELECT ic.column_id
    FROM sys.indexes i
    JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
    JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
    WHERE i.is_primary_key = 1 AND OBJECT_NAME(i.object_id) = '{table_name}'
    """
    try:
        pk_cols = pd.read_sql(query_pk, conn)['column_id'].tolist()
    except Exception:
        pk_cols = []

    # Detectar FK
    query_fk = f"""
    SELECT fkc.constraint_column_id
    FROM sys.foreign_key_columns fkc
    JOIN sys.tables t1 ON fkc.parent_object_id = t1.object_id
    WHERE t1.name = '{table_name}'
    """
    try:
        fk_cols = pd.read_sql(query_fk, conn)['constraint_column_id'].tolist()
    except Exception:
        fk_cols = []

    estructura = []
    for idx, row in df_cols.iterrows():
        col_name = row['atributo']
        col_id = idx + 1

        tipo = row['tipo']
        if tipo in ['varchar', 'char', 'nvarchar', 'nchar']:
            tamaño = row['max_length']
            if tamaño == -1:
                tamaño = 'MAX'
            tipo = f"VARCHAR({tamaño})"
        elif tipo in ['decimal', 'numeric']:
            tipo = f"DECIMAL({row['precision']},{row['scale']})"
        elif tipo == 'int':
            tipo = 'INT'
        elif tipo == 'date':
            tipo = 'DATE'
        elif tipo == 'datetime':
            tipo = 'DATETIME'
        else:
            tipo = tipo.upper()

        llave = ""
        if col_id in pk_cols:
            llave = "PK"
        if col_id in fk_cols:
            llave = "FK" if not llave else "PK,FK"

        dependencia = ""
        if col_name == "IdCliente":
            dependencia = "IdCliente → Nombre, Email"
        elif col_name == "IdOrden":
            dependencia = "IdOrden → Fecha, IdCliente"
        elif col_name == "IdArticulo":
            dependencia = "IdArticulo → NombreArt, Precio"
        elif col_name == "Cantidad":
            dependencia = "IdOrden, IdArticulo → Cantidad"

        estructura.append({
            'tabla': table_name,
            'atributo': col_name,
            'tipo': tipo,
            'llave': llave,
            'dependencia_funcional(A→B)': dependencia
        })

    return pd.DataFrame(estructura)

def crear_tabla_desde_df(conn, nombre_tabla, df):
    try:
        params = urllib.parse.quote_plus(
            f"DRIVER={{ODBC Driver 17 for SQL Server}};"
            f"SERVER=localhost;"
            f"DATABASE={conn.getinfo(pyodbc.SQL_DATABASE_NAME)};"
            f"Trusted_Connection=yes;"
        )
        engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}")
        df.to_sql(nombre_tabla, engine, if_exists='replace', index=False)
        return True
    except Exception as e:
        print(f"❌ Error al crear tabla {nombre_tabla}: {e}")
        return False