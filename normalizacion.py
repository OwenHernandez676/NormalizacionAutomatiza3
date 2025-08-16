# normalizacion.py
def esta_en_1fn(df):
    """Verifica si todos los valores son atómicos"""
    if df.empty:
        return True
    for col in df.columns:
        if df[col].astype(str).str.contains(',', na=False).any():
            return False
    return True

def aplicar_1fn(df):
    """Descompone valores múltiples separados por coma"""
    if df.empty:
        return df
    df_copy = df.copy()
    for col in df.columns:
        if df_copy[col].astype(str).str.contains(',', na=False).any():
            df_copy = df_copy.assign(**{col: df_copy[col].astype(str).str.split(',')}).explode(col)
    df_copy = df_copy.reset_index(drop=True)
    df_copy.name = getattr(df, 'name', None)
    return df_copy

def extraer_dependencias(df_estructura):
    """Extrae dependencias funcionales del formato A → B, C"""
    dependencias = {}
    if df_estructura.empty:
        return dependencias
    for _, row in df_estructura.dropna(subset=['dependencia_funcional(A→B)']).iterrows():
        tabla = row['tabla']
        dep = str(row['dependencia_funcional(A→B)']).strip()
        if '→' not in dep:
            continue
        izq, der = dep.split('→')
        izq_attrs = [a.strip() for a in izq.split(',') if a.strip()]
        der_attrs = [a.strip() for a in der.split(',') if a.strip()]
        if tabla not in dependencias:
            dependencias[tabla] = []
        for d in der_attrs:
            dependencias[tabla].append((izq_attrs, d))
    return dependencias

def obtener_pk(df_estructura, tabla):
    """Obtiene las columnas que son PK para una tabla"""
    if df_estructura.empty:
        return []
    return df_estructura[
        (df_estructura['tabla'] == tabla) & 
        (df_estructura['llave'].str.contains('PK'))
    ]['atributo'].tolist()

def tiene_dependencia_parcial(df, pk, dependencias):
    """Verifica dependencias parciales (2FN)"""
    if len(pk) <= 1 or df.empty:
        return False
    for (izq, der) in dependencias:
        if set(izq).issubset(set(pk)) and der not in pk:
            return True
    return False

def aplicar_2fn(df, dependencias, pk):
    """Descompone tablas con dependencias parciales"""
    if not tiene_dependencia_parcial(df, pk, dependencias):
        return {df.name: df.copy()}

    tablas = {}
    cols_remover = []
    for (izq, der) in dependencias:
        if set(izq).issubset(set(pk)) and der not in pk:
            nueva_tabla = f"{df.name}_{der}"
            cols = izq + [der]
            tablas[nueva_tabla] = df[cols].drop_duplicates()
            cols_remover.append(der)

    tabla_principal = df.drop(columns=cols_remover).drop_duplicates()
    tablas[df.name] = tabla_principal
    return tablas

def tiene_dependencia_transitiva(dependencias, pk=None):
    """Verifica dependencias transitivas (3FN)"""
    pk = pk or []
    for izq, der in dependencias:
        if not set(izq).issubset(set(pk)) and der not in pk:
            return True
    return False

def aplicar_3fn(tablas_2fn, dependencias, pk):
    """Aplica 3FN descomponiendo dependencias transitivas"""
    if not tiene_dependencia_transitiva(dependencias, pk):
        return tablas_2fn, "✅ Ya está en 3FN."

    tablas_3fn = {}
    for nombre, df in tablas_2fn.items():
        df_main = df.copy()
        nuevas = {}
        for (izq, der) in dependencias:
            if der in df_main.columns and der not in pk and not set(izq).issubset(set(pk)):
                nueva_tabla = f"{nombre}_{der}"
                cols = izq + [der]
                nuevas[nueva_tabla] = df_main[cols].drop_duplicates()
                if der in df_main.columns:
                    df_main = df_main.drop(columns=[der])
        tablas_3fn[nombre] = df_main.drop_duplicates()
        tablas_3fn.update(nuevas)

    return tablas_3fn, "⚠️ Aplicada 3FN"


def normalizar_tabla(df, pk, dependencias):
    """Aplica 1FN, 2FN y 3FN a un DataFrame"""
    df_1fn = aplicar_1fn(df)
    tablas_2fn = aplicar_2fn(df_1fn, dependencias, pk)
    tablas_3fn, _ = aplicar_3fn(tablas_2fn, dependencias, pk)
    return tablas_3fn


def inferir_tipo_sql(serie):
    import pandas as pd
    if pd.api.types.is_integer_dtype(serie):
        return "INT"
    if pd.api.types.is_float_dtype(serie):
        return "FLOAT"
    if pd.api.types.is_datetime64_any_dtype(serie):
        return "DATETIME"
    return "VARCHAR(255)"


def generar_script_sql(tablas):
    """Genera un script SQL CREATE TABLE para las tablas dadas"""
    lineas = []
    for nombre, df in tablas.items():
        lineas.append(f"CREATE TABLE {nombre} (")
        cols = []
        for col in df.columns:
            cols.append(f"    {col} {inferir_tipo_sql(df[col])}")
        lineas.append(",\n".join(cols))
        lineas.append(");\n")
    return "\n".join(lineas)
