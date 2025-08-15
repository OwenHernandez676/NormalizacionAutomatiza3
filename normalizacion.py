# normalizacion.py
def esta_en_1fn(df):
    for col in df.columns:
        if df[col].astype(str).str.contains(',', na=False).any():
            return False
    return True

def aplicar_1fn(df):
    df_copy = df.copy()
    for col in df.columns:
        if df_copy[col].astype(str).str.contains(',', na=False).any():
            df_copy = df_copy.assign(**{col: df_copy[col].astype(str).str.split(',')}).explode(col)
    return df_copy.reset_index(drop=True)

def extraer_dependencias(df_estructura):
    dependencias = []
    for _, row in df_estructura.dropna(subset=['dependencia_funcional(A→B)']).iterrows():
        dep = str(row['dependencia_funcional(A→B)']).strip()
        if '→' not in dep:
            continue
        izq, der = dep.split('→')
        izq_attrs = [a.strip() for a in izq.split(',') if a.strip()]
        der_attrs = [a.strip() for a in der.split(',') if a.strip()]
        for d in der_attrs:
            dependencias.append((izq_attrs, d))
    return dependencias

def obtener_pk(df_estructura):
    return df_estructura[df_estructura['llave'].str.contains('PK')]['atributo'].tolist()

def tiene_dependencia_parcial(df, pk, dependencias):
    if len(pk) <= 1:
        return False
    for (izq, der) in dependencias:
        if set(izq).issubset(set(pk)) and der not in pk:
            return True
    return False

def aplicar_2fn(df, dependencias, pk):
    if not tiene_dependencia_parcial(df, pk, dependencias):
        return {df.name: df}

    tablas = {}
    grupo_principal = pk.copy()
    for (izq, der) in dependencias:
        if set(izq).issubset(set(pk)) and der not in pk:
            nueva_tabla = f"{df.name}_{der}"
            cols = list(set(izq + [der]))
            tablas[nueva_tabla] = df[cols].drop_duplicates()
            grupo_principal.append(der)
    tablas[df.name] = df[list(set(grupo_principal))].drop_duplicates()
    return tablas

def tiene_dependencia_transitiva(dependencias):
    for (a, b) in [(x, y) for (x, _), y in dependencias]:
        for (b2, c) in [(x, y) for (x, _), y in dependencias]:
            if b == b2 and a != c:
                return True
    return False

def aplicar_3fn(tablas_2fn, dependencias):
    if not tiene_dependencia_transitiva(dependencias):
        return tablas_2fn, "✅ Ya está en 3FN. No hay dependencias transitivas."
    return tablas_2fn, "⚠️ 3FN aplicado (simulado)."