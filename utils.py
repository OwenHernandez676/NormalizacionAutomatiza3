# utils.py
import pyodbc
import pandas as pd
from typing import List, Tuple, Dict

def get_connection():
    """
    Establece conexión a SQL Server con autenticación de Windows
    """
    try:
        conn = pyodbc.connect(
            'DRIVER={ODBC Driver 17 for SQL Server};'
            'SERVER=localhost;'  # Cambia si usas otro servidor
            'Trusted_Connection=yes;',
            autocommit=False
        )
        return conn
    except Exception as e:
        raise Exception(f"Error al conectar a SQL Server: {str(e)}")

def get_databases() -> List[str]:
    """
    Obtiene la lista de bases de datos disponibles
    """
    try:
        conn = get_connection()
        query = "SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name"
        df = pd.read_sql(query, conn)
        conn.close()
        return df['name'].tolist()
    except Exception as e:
        raise Exception(f"Error al obtener bases de datos: {str(e)}")

def get_tables(database: str) -> List[str]:
    """
    Obtiene las tablas de una base de datos específica
    """
    try:
        conn = get_connection()
        conn.execute(f"USE [{database}]")
        query = """
            SELECT TABLE_NAME 
            FROM INFORMATION_SCHEMA.TABLES 
            WHERE TABLE_TYPE = 'BASE TABLE'
            ORDER BY TABLE_NAME
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df['TABLE_NAME'].tolist()
    except Exception as e:
        raise Exception(f"Error al obtener tablas: {str(e)}")

def get_table_structure(database: str, table: str) -> Tuple[List[Dict], List[str]]:
    """
    Obtiene la estructura de una tabla: atributos, tipos, llaves, dependencias
    Retorna: (lista de columnas, lista de PK)
    """
    try:
        conn = get_connection()
        conn.execute(f"USE [{database}]")

        # Información de columnas
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
        ORDER BY c.column_id
        """
        cols_df = pd.read_sql(col_query, conn, params=[table])

        # Clave primaria
        pk_query = """
        SELECT col.name AS atributo
        FROM sys.indexes i
        JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
        JOIN sys.columns col ON ic.object_id = col.object_id AND ic.column_id = col.column_id
        JOIN sys.tables tbl ON i.object_id = tbl.object_id
        WHERE i.is_primary_key = 1 AND tbl.name = ?
        """
        pk_df = pd.read_sql(pk_query, conn, params=[table])
        pk_cols = pk_df['atributo'].tolist()

        # Claves foráneas
        fk_query = """
        SELECT col.name AS atributo
        FROM sys.foreign_key_columns fkc
        JOIN sys.columns col ON fkc.parent_object_id = col.object_id AND fkc.parent_column_id = col.column_id
        JOIN sys.tables tbl ON fkc.parent_object_id = tbl.object_id
        WHERE tbl.name = ?
        """
        fk_df = pd.read_sql(fk_query, conn, params=[table])
        fk_cols = fk_df['atributo'].tolist()

        # Formatear tipo de dato
        def format_type(row):
            t = row['tipo'].upper()
            if t in ['VARCHAR', 'NVARCHAR', 'CHAR', 'NCHAR']:
                size = row['max_length']
                return f"{t}({size})" if size > 0 else f"{t}(MAX)"
            elif t == 'DECIMAL':
                return f"DECIMAL({row['precision']},{row['scale']})"
            elif t in ['INT', 'BIGINT', 'SMALLINT', 'TINYINT']:
                return 'INT'
            elif t == 'DATE':
                return 'DATE'
            elif t == 'DATETIME':
                return 'DATETIME'
            elif t == 'BIT':
                return 'BIT'
            else:
                return t

        cols_df['tipo'] = cols_df.apply(format_type, axis=1)
        cols_df['llave'] = cols_df['atributo'].apply(
            lambda x: 'PK' if x in pk_cols else 'FK' if x in fk_cols else ''
        )

        # Dependencias funcionales (desde PK)
        non_pk_non_fk = [c for c in cols_df['atributo'] if c not in pk_cols and c not in fk_cols]
        if pk_cols and non_pk_non_fk:
            dep = f"{', '.join(pk_cols)} → {', '.join(non_pk_non_fk)}"
        else:
            dep = ""

        # Añadir dependencia a todas las filas
        cols_df['dependencia_funcional(A→B)'] = dep
        cols_df['tabla'] = table

        # Seleccionar columnas requeridas
        structure = cols_df[[
            'tabla', 'atributo', 'tipo', 'llave', 'dependencia_funcional(A→B)'
        ]].to_dict('records')

        conn.close()
        return structure, pk_cols

    except Exception as e:
        conn.close()
        raise Exception(f"Error al obtener estructura: {str(e)}")

def get_table_data(database: str, table: str) -> pd.DataFrame:
    """
    Obtiene los datos de una tabla (hasta 1000 filas)
    """
    try:
        conn = get_connection()
        conn.execute(f"USE [{database}]")
        query = f"SELECT TOP 1000 * FROM [{table}] ORDER BY (SELECT NULL)"
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        raise Exception(f"Error al obtener datos de la tabla: {str(e)}")

def upload_normalized_tables(database: str, tables_dict: Dict[str, pd.DataFrame]):
    """
    Sube múltiples tablas normalizadas a la base de datos
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"USE [{database}]")
        for table_name, df in tables_dict.items():
            # Eliminar tabla si existe
            cursor.execute(f"IF OBJECT_ID('{table_name}', 'U') IS NOT NULL DROP TABLE [{table_name}];")

            # Crear columnas
            create_cols = []
            for col_name, dtype in df.dtypes.items():
                if dtype == 'object':
                    sql_type = 'NVARCHAR(MAX)'
                elif 'int' in str(dtype):
                    sql_type = 'INT'
                elif 'float' in str(dtype) or 'double' in str(dtype):
                    sql_type = 'DECIMAL(18, 4)'
                elif 'datetime' in str(dtype):
                    sql_type = 'DATETIME'
                elif dtype == 'bool':
                    sql_type = 'BIT'
                else:
                    sql_type = 'NVARCHAR(255)'
                create_cols.append(f"[{col_name}] {sql_type}")

            create_query = f"CREATE TABLE [{table_name}] ({', '.join(create_cols)})"
            cursor.execute(create_query)

            # Insertar datos
            for _, row in df.iterrows():
                values = [str(v) if pd.notna(v) else None for v in row]
                placeholders = ', '.join(['?' for _ in values])
                insert_query = f"INSERT INTO [{table_name}] VALUES ({placeholders})"
                cursor.execute(insert_query, values)

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise Exception(f"Error al subir tablas normalizadas: {str(e)}")
    finally:
        conn.close()