# utils.py
import pyodbc
import pandas as pd
from sqlalchemy import create_engine
import urllib

def conectar_sql_server(server="localhost", database=None):
    """Conecta a SQL Server con autenticación de Windows"""
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
    """Lista todas las bases de datos disponibles"""
    conn = conectar_sql_server(server)
    if not conn:
        return []
    try:
        query = "SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name"
        df = pd.read_sql(query, conn)
        conn.close()
        return df['name'].tolist()
    except Exception as e:
        print(f"❌ Error listando BD: {e}")
        conn.close()
        return []

def listar_tablas(conn):
    """Lista todas las tablas con esquema (ej: Sales.Clientes)"""
    try:
        query = """
        SELECT CONCAT(TABLE_SCHEMA, '.', TABLE_NAME) AS full_table_name
        FROM INFORMATION_SCHEMA.TABLES 
        WHERE TABLE_TYPE = 'BASE TABLE'
        ORDER BY TABLE_SCHEMA, TABLE_NAME
        """
        df = pd.read_sql(query, conn)
        return df['full_table_name'].tolist()
    except Exception as e:
        print(f"❌ Error listando tablas: {e}")
        return []

def leer_tabla_completa(conn, table_name):
    """Lee TODOS los datos de una tabla"""
    try:
        query = f"SELECT * FROM [{table_name}]"
        df = pd.read_sql(query, conn)
        df.name = table_name
        return df
    except Exception as e:
        print(f"❌ Error al leer {table_name}: {e}")
        return pd.DataFrame()

def leer_estructura_completa(conn):
    """Genera estructura completa de todas las tablas"""
    try:
        query_cols = """
        SELECT 
            s.name + '.' + t.name AS tabla,
            c.name AS atributo,
            ty.name AS tipo,
            c.max_length,
            c.precision,
            c.scale
        FROM sys.columns c
        JOIN sys.tables t ON c.object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        JOIN sys.types ty ON c.user_type_id = ty.user_type_id
        ORDER BY s.name, t.name, c.column_id
        """
        df_cols = pd.read_sql(query_cols, conn)

        # PK
        query_pk = """
        SELECT 
            s.name + '.' + t.name AS tabla,
            c.name AS atributo
        FROM sys.indexes i
        JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
        JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
        JOIN sys.tables t ON i.object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        WHERE i.is_primary_key = 1
        """
        df_pk = pd.read_sql(query_pk, conn)
        pk_dict = df_pk.set_index(['tabla', 'atributo']).index.tolist()

        # FK
        query_fk = """
        SELECT 
            s.name + '.' + t.name AS tabla,
            c.name AS atributo
        FROM sys.foreign_key_columns fkc
        JOIN sys.tables t ON fkc.parent_object_id = t.object_id
        JOIN sys.schemas s ON t.schema_id = s.schema_id
        JOIN sys.columns c ON fkc.parent_object_id = c.object_id AND fkc.parent_column_id = c.column_id
        """
        df_fk = pd.read_sql(query_fk, conn)
        fk_dict = df_fk.set_index(['tabla', 'atributo']).index.tolist()

        estructura = []
        for _, row in df_cols.iterrows():
            tabla = row['tabla']
            atributo = row['atributo']

            tipo = row['tipo']
            if tipo in ['varchar', 'char', 'nvarchar', 'nchar']:
                tamaño = row['max_length']
                tipo = f"VARCHAR({tamaño})" if tamaño != -1 else "VARCHAR(MAX)"
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
            if (tabla, atributo) in pk_dict:
                llave = "PK"
            if (tabla, atributo) in fk_dict:
                llave = "FK" if not llave else "PK,FK"

            dependencia = ""

            estructura.append({
                'tabla': tabla,
                'atributo': atributo,
                'tipo': tipo,
                'llave': llave,
                'dependencia_funcional(A→B)': dependencia
            })

        return pd.DataFrame(estructura)
    except Exception as e:
        print(f"❌ Error generando estructura: {e}")
        return pd.DataFrame()

def crear_tabla_desde_df(conn, nombre_tabla, df):
    """Crea o reemplaza una tabla desde un DataFrame"""
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