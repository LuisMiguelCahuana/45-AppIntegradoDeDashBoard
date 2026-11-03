import io
import re
import unicodedata
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from sheets_cache import read_sheet, clear_sheet, CACHE_TTL

# ID del Google Sheets proporcionado por el usuario.
SPREADSHEET_ID = "1AJ94Nrvlg7T4994K3qD_gD7dv6JZ563hJSf8hvPhOTA"

HOJAS = {
    "Personal": [
        "CONTRATO", "UUNN", "LOCALIDAD", "PERSONAL", "DNI", "CARGO",
        "TIPO_INCIDENCIA", "FECHA_SALIDA",
        "FECHA_INCORPRACION / NUEVO PERSONAL", "ESTADO",
        "OBSERVACIONES", "FECHA_ACTUALIZACION",
    ],
    "Vehiculo": [
        "CONTRATO", "UUNN", "SSEE", "PLACA", "TIPO_INCIDENCIA",
        "DESCRIPCION", "FECHA_REPORTE", "FECHA_REPOSICION", "ESTADO",
        "OBSERVACIONES", "EVIDENCIA_FOTOGRAFICA", "FECHA_ACTUALIZACION",
    ],
    "Material": [
        "CONTRATO", "UUNN", "LOCALIDAD", "TIPO",
        "MATERIAL/EQUPO Y HERRAMIENTA", "UNIDAD_MEDIDA",
        "CANTIDAD_FALTANTE", "TIPO_INCIDENCIA", "FECHA_INICIO",
        "FECHA_REPOSICION", "ESTADO", "OBSERVACIONES",
        "EVIDENCIA_FOTOGRAFICA", "FECHA_ACTUALIZACION",
    ],
}

DATE_COLUMNS = {
    "Personal": ["FECHA_SALIDA", "FECHA_INCORPRACION / NUEVO PERSONAL", "FECHA_ACTUALIZACION"],
    "Vehiculo": ["FECHA_REPORTE", "FECHA_REPOSICION", "FECHA_ACTUALIZACION"],
    "Material": ["FECHA_INICIO", "FECHA_REPOSICION", "FECHA_ACTUALIZACION"],
}

def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", str(texto or "").strip())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", texto.casefold())

def _leer_hoja(nombre):
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError(
            "Falta configurar gcp_service_account en Streamlit Secrets. "
            "La cuenta de servicio debe tener permiso de lector en el Google Sheets."
        )
    valores = read_sheet(SPREADSHEET_ID, nombre)
    if not valores:
        return pd.DataFrame(columns=HOJAS[nombre])

    encabezados = [str(x).strip() for x in valores[0]]
    filas = valores[1:]
    ancho = len(encabezados)
    filas = [(fila[:ancho] + [""] * max(0, ancho - len(fila))) for fila in filas]
    df = pd.DataFrame(filas, columns=encabezados)

    # Emparejar encabezados ignorando tildes, espacios, guiones y mayúsculas.
    mapa = {_normalizar(c): c for c in df.columns if str(c).strip()}
    renombrar = {}
    for canonico in HOJAS[nombre]:
        if canonico in df.columns:
            continue
        original = mapa.get(_normalizar(canonico))
        if original is None and canonico == "FECHA_INCORPRACION / NUEVO PERSONAL":
            original = mapa.get(_normalizar("FECHA_INCORPORACION / NUEVO PERSONAL"))
        if original is None and canonico == "MATERIAL/EQUPO Y HERRAMIENTA":
            original = mapa.get(_normalizar("MATERIAL/EQUIPO Y HERRAMIENTA"))
        if original is not None:
            renombrar[original] = canonico
    if renombrar:
        df = df.rename(columns=renombrar)

    for col in HOJAS[nombre]:
        if col not in df.columns:
            df[col] = ""
    df = df[HOJAS[nombre]].copy()

    for col in df.columns:
        if col not in DATE_COLUMNS[nombre]:
            df[col] = df[col].fillna("").astype(str).str.strip()

    for col in DATE_COLUMNS[nombre]:
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True, format="mixed")

    if nombre == "Material":
        df["CANTIDAD_FALTANTE"] = pd.to_numeric(
            df["CANTIDAD_FALTANTE"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce"
        ).fillna(0)
    return df

@st.cache_data(ttl=CACHE_TTL, show_spinner="Leyendo hojas de Incidencia y Recurso...")
def cargar_todo():
    return {nombre: _leer_hoja(nombre) for nombre in HOJAS}

def _limpiar(valor):
    return str(valor).strip() if pd.notna(valor) else ""

def _filtrar_base(df, contrato, uunn):
    out = df.copy()
    if contrato != "Todos":
        out = out[out["CONTRATO"] == contrato]
    if uunn != "Todas":
        out = out[out["UUNN"] == uunn]
    return out

def _estado_abierto(df):
    # Se interpreta como abierto todo estado distinto de cerrado/resuelto/repuesto.
    # Se conserva el texto original en los gráficos y tablas.
    cerrados = {"CERRADO", "CERRADA", "RESUELTO", "RESUELTA", "REPUESTO", "REPUESTA", "ATENDIDO", "ATENDIDA"}
    estado = df["ESTADO"].fillna("").astype(str).str.strip().str.upper()
    return ~estado.isin(cerrados) & estado.ne("")

def _metricas_generales(personal, vehiculo, material):
    total = len(personal) + len(vehiculo) + len(material)
    abiertos = int(_estado_abierto(personal).sum()) + int(_estado_abierto(vehiculo).sum()) + int(_estado_abierto(material).sum())
    cantidad_faltante = float(material["CANTIDAD_FALTANTE"].sum()) if not material.empty else 0
    return total, abiertos, cantidad_faltante

def _grafico_barras(df, categoria, titulo, key, valor=None):
    if df.empty or categoria not in df.columns:
        st.info("No hay datos disponibles para este gráfico.")
        return
    if valor:
        resumen = df.groupby(categoria, dropna=False)[valor].sum().reset_index()
        resumen = resumen.sort_values(valor, ascending=False)
        fig = px.bar(resumen, x=categoria, y=valor, text=valor, title=titulo)
        fig.update_traces(texttemplate="%{text:,.2f}", textposition="outside", cliponaxis=False)
        fig.update_layout(yaxis_title=valor, xaxis_title="")
    else:
        resumen = df[categoria].replace("", "Sin dato").value_counts().rename_axis(categoria).reset_index(name="Registros")
        fig = px.bar(resumen, x=categoria, y="Registros", text="Registros", title=titulo)
        fig.update_traces(textposition="outside", cliponaxis=False)
        fig.update_layout(yaxis_title="Registros", xaxis_title="")
    fig.update_layout(height=390, margin=dict(l=35, r=25, t=65, b=100))
    fig.update_xaxes(tickangle=-25, automargin=True)
    st.plotly_chart(fig, use_container_width=True, key=key, config={"displayModeBar": False, "responsive": True})

def _descargar_excel(datos):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nombre, df in datos.items():
            exportar = df.copy()
            for col in exportar.columns:
                if pd.api.types.is_datetime64_any_dtype(exportar[col]):
                    exportar[col] = exportar[col].dt.strftime("%d/%m/%Y")
            exportar.to_excel(writer, index=False, sheet_name=nombre[:31])
    st.download_button(
        "📥 Descargar datos filtrados (Excel)",
        data=buffer.getvalue(),
        file_name=f"incidencia_recurso_{date.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

def render():
    st.title("🧩 INCIDENCIA Y RECURSO")
    st.caption("Panel de control gerencial · Personal, vehículos, materiales, equipos y herramientas")

    try:
        datos = cargar_todo()
    except Exception as exc:
        st.error(f"No se pudieron cargar las hojas de Google Sheets: {exc}")
        st.info(
            "Verifica que las pestañas se llamen exactamente Personal, Vehiculo y Material, "
            "y que el correo de gcp_service_account tenga acceso de lector al documento."
        )
        st.stop()

    if all(df.empty for df in datos.values()):
        st.warning("Las hojas Personal, Vehiculo y Material no contienen registros.")
        st.stop()

    # Filtros comunes para comparar los tres recursos.
    combinado = pd.concat(
        [df[["CONTRATO", "UUNN"]] for df in datos.values()],
        ignore_index=True
    )
    contratos = sorted(x for x in combinado["CONTRATO"].dropna().astype(str).str.strip().unique() if x)
    unidades = sorted(x for x in combinado["UUNN"].dropna().astype(str).str.strip().unique() if x)

    with st.sidebar:
        st.subheader("🔎 Filtros gerenciales")
        contrato = st.selectbox("Contrato", ["Todos"] + contratos, key="ir_contrato")
        uunn = st.selectbox("Unidad de negocio", ["Todas"] + unidades, key="ir_uunn")
        st.divider()
        st.caption("Los datos se almacenan temporalmente en caché durante 30 minutos.")
        if st.button("🔄 Actualizar datos", use_container_width=True, key="ir_actualizar"):
            clear_sheet(SPREADSHEET_ID, "Personal")
            cargar_todo.clear()
            st.rerun()

    personal = _filtrar_base(datos["Personal"], contrato, uunn)
    vehiculo = _filtrar_base(datos["Vehiculo"], contrato, uunn)
    material = _filtrar_base(datos["Material"], contrato, uunn)

    total, _, _ = _metricas_generales(personal, vehiculo, material)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Registros de incidencias", f"{total:,}")
    c2.metric("Registros de Personal", f"{len(personal):,}")
    c3.metric("Registros de Vehículos", f"{len(vehiculo):,}")
    c4.metric("Registros de Materiales, equipos y herramientas", f"{len(material):,}")

    tab_resumen, tab_personal, tab_vehiculo, tab_material = st.tabs([
        "📊 Resumen gerencial", "👥 Personal", "🚙 Vehículos", "🧰 Materiales y equipos"
    ])

    with tab_resumen:
        st.subheader("Distribución de incidencias por recurso")
        resumen = pd.DataFrame({
            "Recurso": ["Personal", "Vehículos", "Materiales / equipos"],
            "Registros": [len(personal), len(vehiculo), len(material)],
        })
        fig = px.pie(resumen, names="Recurso", values="Registros", hole=0.55,
                     title="Participación de registros por tipo de recurso")
        fig.update_layout(height=390, margin=dict(t=65, b=25))
        st.plotly_chart(fig, use_container_width=True, key="ir_pie_recursos",
                        config={"displayModeBar": False, "responsive": True})

        a, b = st.columns(2)
        with a:
            _grafico_barras(personal, "TIPO_INCIDENCIA", "Incidencias de personal por tipo", "ir_res_personal")
            _grafico_barras(vehiculo, "TIPO_INCIDENCIA", "Incidencias de vehículos por tipo", "ir_res_vehiculo")
        with b:
            _grafico_barras(material, "TIPO_INCIDENCIA", "Incidencias de materiales por tipo", "ir_res_material")
            _grafico_barras(
                pd.concat([personal.assign(RECURSO="Personal"),
                           vehiculo.assign(RECURSO="Vehículo"),
                           material.assign(RECURSO="Material")], ignore_index=True, sort=False),
                "ESTADO", "Registros por estado", "ir_res_estado"
            )

        st.subheader("Resumen por contrato y unidad de negocio")
        combinado_resumen = pd.concat([
            personal.assign(RECURSO="Personal"),
            vehiculo.assign(RECURSO="Vehículo"),
            material.assign(RECURSO="Material"),
        ], ignore_index=True, sort=False)
        if not combinado_resumen.empty:
            tabla = combinado_resumen.groupby(["CONTRATO", "UUNN", "RECURSO"], dropna=False).size().reset_index(name="REGISTROS")
            st.dataframe(tabla, use_container_width=True, hide_index=True)

    with tab_personal:
        st.subheader("Control de incidencias de personal")
        p1, p2, p3 = st.columns(3)
        p1.metric("Registros", len(personal))
        p2.metric("Con fecha de salida", int(personal["FECHA_SALIDA"].notna().sum()))
        p3.metric("Con fecha de incorporación", int(personal["FECHA_INCORPRACION / NUEVO PERSONAL"].notna().sum()))
        a, b = st.columns(2)
        with a:
            _grafico_barras(personal, "TIPO_INCIDENCIA", "Personal por tipo de incidencia", "ir_p_tipo")
        with b:
            _grafico_barras(personal, "ESTADO", "Personal por estado", "ir_p_estado")
        st.dataframe(personal, use_container_width=True, hide_index=True)

    with tab_vehiculo:
        st.subheader("Control de incidencias vehiculares")
        v1, v2, v3 = st.columns(3)
        v1.metric("Vehículos reportados", len(vehiculo))
        v2.metric("Con fecha de reposición", int(vehiculo["FECHA_REPOSICION"].notna().sum()))
        v3.metric("Sin fecha de reposición", int(vehiculo["FECHA_REPOSICION"].isna().sum()))
        a, b = st.columns(2)
        with a:
            _grafico_barras(vehiculo, "TIPO_INCIDENCIA", "Vehículos por tipo de incidencia", "ir_v_tipo")
        with b:
            _grafico_barras(vehiculo, "ESTADO", "Vehículos por estado", "ir_v_estado")
        _grafico_barras(vehiculo, "PLACA", "Incidencias por placa", "ir_v_placa")
        st.dataframe(vehiculo, use_container_width=True, hide_index=True)

    with tab_material:
        st.subheader("Control de materiales, equipos y herramientas")
        m1, m2, m3 = st.columns(3)
        m1.metric("Registros", len(material))
        m2.metric("Cantidad faltante", f"{material['CANTIDAD_FALTANTE'].sum():,.2f}")
        m3.metric("Materiales / equipos distintos", material["MATERIAL/EQUPO Y HERRAMIENTA"].replace("", pd.NA).nunique())
        a, b = st.columns(2)
        with a:
            _grafico_barras(material, "TIPO_INCIDENCIA", "Materiales por tipo de incidencia", "ir_m_tipo")
        with b:
            _grafico_barras(material, "ESTADO", "Materiales por estado", "ir_m_estado")
        _grafico_barras(material, "MATERIAL/EQUPO Y HERRAMIENTA",
                        "Cantidad faltante por material / equipo", "ir_m_cantidad",
                        valor="CANTIDAD_FALTANTE")
        st.dataframe(material, use_container_width=True, hide_index=True)

    st.divider()
    _descargar_excel({"Personal": personal, "Vehiculo": vehiculo, "Material": material})
