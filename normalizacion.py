# normalizacion.py
import pandas as pd
import re

def parse_dependencies(df_structure):
    dependencies = {}
    for _, row in df_structure.iterrows():
        dep = row['dependencia_funcional(A→B)']
        if pd.isna(dep) or not dep.strip(): continue
        match = re.match(r'([^→]+)→(.+)', dep.strip())
        if match:
            left = [x.strip() for x in match.group(1).split(',') if x.strip()]
            right = [x.strip() for x in match.group(2).split(',') if x.strip()]
            for attr in left:
                dependencies[attr] = dependencies.get(attr, []) + right
    for k in dependencies: dependencies[k] = list(set(dependencies[k]))
    return dependencies

def is_in_1fn(df):
    for col in df.columns:
        sample = df[col].astype(str).str.contains(r'[;,]\s*', na=False)
        if sample.any() and df[col].nunique() > 1:
            val = df[col][sample].iloc[0]
            return False, f"No atómico en '{col}': {val}"
    return True, "✔️ 1FN: Valores atómicos"

def find_partial_dependencies(df, pk, dependencies):
    partial = []
    for attr in pk:
        if attr in dependencies:
            for dep in dependencies[attr]:
                if dep not in pk:
                    partial.append(f"{attr} → {dep}")
    return partial

def find_transitive_dependencies(pk, dependencies):
    transitive = []
    pk_set = set(pk)
    for x in dependencies:
        if x in pk_set:
            for y in dependencies[x]:
                if y in dependencies and y not in pk_set:
                    for z in dependencies[y]:
                        if z not in pk_set and z not in dependencies.get(x, []):
                            transitive.append(f"{x} → {y} → {z}")
    return transitive

def analyze_table_normalization(df_data, df_structure):
    dependencies = parse_dependencies(df_structure)
    pk = df_structure[df_structure['llave'] == 'PK']['atributo'].tolist()
    if not pk and len(df_data.columns) > 0:
        pk = [df_data.columns[0]]

    in_1fn, msg_1fn = is_in_1fn(df_data)
    partial_deps = find_partial_dependencies(df_data, pk, dependencies)
    in_2fn = len(partial_deps) == 0
    msg_2fn = "✔️ 2FN: No hay dependencias parciales" if in_2fn else f"❌ 2FN: {', '.join(partial_deps)}"
    transitive_deps = find_transitive_dependencies(pk, dependencies)
    in_3fn = len(transitive_deps) == 0
    msg_3fn = "✔️ 3FN: No hay dependencias transitivas" if in_3fn else f"❌ 3FN: {', '.join(transitive_deps)}"

    return {
        '1fn': {'cumple': in_1fn, 'mensaje': msg_1fn},
        '2fn': {'cumple': in_2fn, 'mensaje': msg_2fn},
        '3fn': {'cumple': in_3fn, 'mensaje': msg_3fn},
        'necesita_normalizar': not (in_1fn and in_2fn and in_3fn),
        'pk': pk,
        'dependencies': dependencies
    }