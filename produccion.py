import io
import re
import calendar
import time
from datetime import datetime

import pandas as pd
import streamlit as st
import gspread
import plotly.express as px
import plotly.graph_objects as go

from sheets_cache import read_sheet, clear_sheet, CACHE_TTL


# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================

SPREADSHEET_ID = "1gNq2nuNGfogcgcq7gsIqmQ5BZmMuWiSgAbDLpytJTIY"
HOJA_ORIGEN = "CONSOLIDADO_GENERAL"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

COLUMNAS = [
    "unidad_negocio",
    "periodo",
    "fecha",
    "suministro",
    "cuadrilla",
    "zona",
    "codigo",
    "cantidad",
    "actividad",
    "costo_unitario",
    "costo_total",
    "proceso",
    "hoja_origen",
    "archivo_origen",
]

ESTILO_ETIQUETA_COSTO = dict(
    size=11,
    family="Arial, sans-serif",
)


@st.cache_resource
def estado_cache_sheets():
    """Conserva la última lectura correcta mientras viva el proceso."""
    return {"valores": None, "actualizado": None}


def es_error_cuota_google(error):
    texto = str(error).lower()
    return (
        "429" in texto
        or "quota exceeded" in texto
        or "read requests per minute" in texto
        or "rate limit" in texto
    )


def leer_google_sheets_con_reintentos():
    """
    Lee la hoja con reintentos limitados ante cuotas temporales.
    Si Google mantiene el límite, reutiliza la última lectura correcta.
    """
    estado = estado_cache_sheets()
    ultimo_error = None

    for espera in (0, 5, 12):
        if espera:
            time.sleep(espera)
        try:
            valores = leer_google_sheets_con_reintentos()
            if valores:
                estado["valores"] = valores
                estado["actualizado"] = datetime.now()
            return valores
        except Exception as error:
            ultimo_error = error
            if not es_error_cuota_google(error):
                raise

    # No se interrumpe el dashboard si ya existe una lectura correcta.
    if estado.get("valores"):
        return estado["valores"]

    raise RuntimeError(
        "Google Sheets está limitando temporalmente las lecturas. "
        "No se pudo obtener una primera copia de los datos. "
        "Espera unos minutos y vuelve a intentarlo."
    ) from ultimo_error


# ============================================================
# FUNCIONES GENERALES
# ============================================================

@st.cache_data(ttl=CACHE_TTL, show_spinner="Procesando producción...")
def cargar_datos():
    """Lee y procesa la hoja CONSOLIDADO_GENERAL."""

    if "gcp_service_account" not in st.secrets:
        raise ValueError(
            "Falta configurar gcp_service_account en los Secrets de Streamlit."
        )

    valores = read_sheet(SPREADSHEET_ID, HOJA_ORIGEN)

    if not valores:
        raise ValueError(f"La hoja {HOJA_ORIGEN} está vacía.")

    # Normalizar encabezados de Google Sheets
    encabezados = [
        str(col).replace("\ufeff", "").replace("\xa0", " ")
        .strip().lower().replace(" ", "_")
        for col in valores[0]
    ]
    
    # Admitir otras variantes de UnidadNegocio
    encabezados = [
        "unidad_negocio"
        if col in ("unidadnegocio", "unidad_de_negocio")
        else col
        for col in encabezados
    ]
    
    # Validar encabezados duplicados
    if len(encabezados) != len(set(encabezados)):
        st.error(
            f"Hay encabezados duplicados: {encabezados}"
        )
        st.stop()
    
    # Validar columnas obligatorias
    faltantes = [
        col for col in COLUMNAS
        if col not in encabezados
    ]
    
    if faltantes:
        st.error(
            f"Faltan columnas en Google Sheets: {faltantes}"
        )
        st.info(
            f"Encabezados encontrados: {encabezados}"
        )
        st.stop()
    
    # Construir DataFrame
    df = pd.DataFrame(
        valores[1:],
        columns=encabezados
    )
    
    # Respetar orden de columnas
    df = df[COLUMNAS].copy()


    if "fecha" in df.columns:
        df["fecha"] = df["fecha"].astype(str).str.strip()
        df.loc[
            df["fecha"].isin(["", "nan", "None"]),
            "fecha"
        ] = ""

    def convertir_numero(valor):
        if pd.isna(valor):
            return None

        if isinstance(valor, (int, float)):
            return float(valor)

        texto = str(valor).strip().replace(" ", "")
        texto = texto.replace("S/.", "").replace("S/", "").strip()

        if not texto or texto.upper() in {"NAN", "NONE", "-"}:
            return None

        if "," in texto and "." in texto:
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            texto = texto.replace(",", ".")

        try:
            return float(texto)
        except (ValueError, TypeError):
            return None

    for col in ["cantidad", "costo_unitario", "costo_total"]:
        if col in df.columns:
            df[col] = df[col].apply(convertir_numero)

    if {"cantidad", "costo_unitario", "costo_total"}.issubset(df.columns):
        calculado = df["cantidad"] * df["costo_unitario"]
        df["costo_total"] = calculado.fillna(df["costo_total"]).fillna(0)

    df = df.dropna(how="all").reset_index(drop=True)

    return df


def formatear_periodo(valor):
    texto = str(valor).strip()

    if re.fullmatch(r"\d{6}", texto):
        try:
            anio = int(texto[:4])
            mes = int(texto[4:6])
            return f"{calendar.month_name[mes].capitalize()} {anio}"
        except (ValueError, IndexError):
            return texto

    return texto


def etiqueta_costo(valor):
    if pd.isna(valor):
        return ""
    return f"S/ {float(valor):,.2f}"


def descargar_excel(df, nombre):
    salida = io.BytesIO()

    with pd.ExcelWriter(salida, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Reporte")

    st.download_button(
        label="📥 Descargar reporte (Excel)",
        data=salida.getvalue(),
        file_name=nombre,
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        ),
        use_container_width=True,
    )


def estilo_barra_con_costo(valores):
    valores = pd.to_numeric(
        pd.Series(valores), errors="coerce"
    ).fillna(0)

    maximo = valores.max() if not valores.empty else 0

    posiciones = [
        "inside" if maximo > 0 and valor >= maximo * 0.12
        else "outside"
        for valor in valores
    ]

    return dict(
        textposition=posiciones,
        textfont=ESTILO_ETIQUETA_COSTO,
        insidetextanchor="middle",
        cliponaxis=False,
    )

def fijar_visibilidad_texto(fig):
    """
    Ajusta el eje Y para dejar espacio a las etiquetas
    de los costos sin modificar las dimensiones del gráfico.
    """

    maximos = []

    for trace in fig.data:
        if trace.y is not None:
            valores = pd.to_numeric(
                pd.Series(trace.y),
                errors="coerce",
            ).dropna()

            if not valores.empty:
                maximos.extend(valores.tolist())

    maximo = max(maximos) if maximos else 0

    limite_superior = (
        maximo * 1.30 if maximo > 0 else 1
    )

    fig.update_yaxes(
        range=[0, limite_superior],
        automargin=True,
        fixedrange=False,
    )

    return fig

# ============================================================
# CONFIGURACIÓN VISUAL DE LOS GRÁFICOS
# ============================================================

ALTO_GRAFICO = 450

def mostrar_grafico(fig):
    """
    Evita que la selección de columnas altere
    la apariencia de los gráficos.
    """

    fig.update_layout(
        height=450,
        autosize=True,
        dragmode=False,
        clickmode="none",
        uirevision="grafico_estable",
        margin=dict(
            l=60,
            r=40,
            t=65,
            b=100,
        ),
        font=dict(
            family="Arial, sans-serif",
            size=12,
        ),
    )

    fig.update_xaxes(
        automargin=True,
        fixedrange=True,
    )

    fig.update_yaxes(
        automargin=True,
        fixedrange=True,
    )

    st.plotly_chart(
        fig,
        use_container_width=True,
        theme="streamlit",
        config={
            "responsive": True,
            "displaylogo": False,
            "scrollZoom": False,
            "modeBarButtonsToRemove": [
                "select2d",
                "lasso2d",
                "toggleSpikelines",
                "hoverClosestCartesian",
                "hoverCompareCartesian",
            ],
        },
    )
def render():
    # ============================================================
    # CARGA DE DATOS
    # ============================================================

    try:
        df = cargar_datos()
    except Exception as e:
        mensaje = str(e)
        if es_error_cuota_google(e) or "limitando temporalmente" in mensaje.lower():
            st.warning(
                "Los datos de Google Sheets no están disponibles temporalmente "
                "por límite de solicitudes. El dashboard reutilizará la última "
                "lectura correcta cuando exista. Espera unos minutos antes de "
                "volver a actualizar."
            )
        else:
            st.error(f"No se pudo cargar el reporte de producción: {mensaje}")
        st.stop()

    if df.empty:
        st.warning("No hay registros en el consolidado todavía.")
        st.stop()

    # La fecha original se conserva para los filtros.
    df["_fecha_dt"] = pd.to_datetime(
        df["fecha"],
        format="mixed",
        dayfirst=True,
        errors="coerce",
    )


    # ============================================================
    # BARRA LATERAL: FILTROS
    # ============================================================

    st.sidebar.title("🔎 Filtros")
    # ------------------------------------------------------------
    # FILTRO POR UNIDAD DE NEGOCIO
    # ------------------------------------------------------------

    unidades_disponibles = sorted(
        df["unidad_negocio"]
        .dropna()
        .astype(str)
        .str.strip()
        .loc[lambda x: x != ""]
        .unique()
        .tolist()
    )

    unidades_filtro = st.sidebar.multiselect(
        "🏢 UnidadNegocio",
        options=unidades_disponibles,
        default=unidades_disponibles,
        key="filtro_unidad_negocio",
    )

    # Filtrar los datos según las unidades seleccionadas
    df = df[
        df["unidad_negocio"]
        .astype(str)
        .str.strip()
        .isin(unidades_filtro)
    ].copy()

    # ------------------------------------------------------------
    # 1. FILTRO POR PERIODO
    # ------------------------------------------------------------

    periodos_disponibles = (
        df["periodo"]
        .astype(str)
        .str.strip()
        .replace("", pd.NA)
        .dropna()
        .unique()
    )

    periodos_ordenados = sorted(
        periodos_disponibles,
        key=lambda p: (formatear_periodo(p), p),
    )

    todos_los_periodos = ["TODOS"] + periodos_ordenados

    periodo_filtro = st.sidebar.selectbox(
        "📅 Periodo (Año y mes)",
        options=todos_los_periodos,
        index=0,
    )

    # ------------------------------------------------------------
    # 2. FILTRO POR FECHA: VALORES ÚNICOS SEGÚN EL PERIODO
    # ------------------------------------------------------------

    df_periodo = df.copy()

    if periodo_filtro != "TODOS":
        df_periodo = df_periodo[
            df_periodo["periodo"].astype(str).str.strip()
            == str(periodo_filtro).strip()
        ]

    fechas_disponibles = (
        df_periodo["fecha"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    fechas_disponibles = fechas_disponibles[
        fechas_disponibles != ""
    ].drop_duplicates().tolist()

    opciones_fecha = ["TODOS"] + sorted(fechas_disponibles)

    fecha_opcion = st.sidebar.selectbox(
        "📆 Fecha",
        options=opciones_fecha,
        index=0,
    )

    fecha_filtro = None if fecha_opcion == "TODOS" else fecha_opcion

    # ------------------------------------------------------------
    # 3. FILTROS ADICIONALES
    # ------------------------------------------------------------

    procesos_disponibles = sorted(
        df_periodo["proceso"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    procesos_filtro = st.sidebar.multiselect(
        "⚙️ Proceso",
        options=procesos_disponibles,
        default=procesos_disponibles,
    )

    zonas_disponibles = sorted(
        df_periodo["zona"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    zonas_filtro = st.sidebar.multiselect(
        "🗺️ Zona",
        options=zonas_disponibles,
        default=zonas_disponibles,
    )

    cuadrillas_disponibles = sorted(
        df_periodo["cuadrilla"]
        .dropna()
        .astype(str)
        .str.strip()
        .unique()
    )

    cuadrillas_filtro = st.sidebar.multiselect(
        "👷 Cuadrilla / Técnico",
        options=cuadrillas_disponibles,
        default=cuadrillas_disponibles,
    )

    # ------------------------------------------------------------
    # APLICAR FILTROS
    # ------------------------------------------------------------

    df_filtrado = df_periodo.copy()

    if fecha_filtro is not None:
        df_filtrado = df_filtrado[
            df_filtrado["fecha"].astype(str).str.strip()
            == fecha_filtro
        ]

    df_filtrado = df_filtrado[
        df_filtrado["proceso"].astype(str).str.strip().isin(procesos_filtro)
        & df_filtrado["zona"].astype(str).str.strip().isin(zonas_filtro)
        & df_filtrado["cuadrilla"].astype(str).str.strip().isin(cuadrillas_filtro)
    ]

    if df_filtrado.empty:
        st.info("Seleccione una o mas unidades de negocio")
        st.stop()


    # ============================================================
    # ENCABEZADO E INDICADORES
    # ============================================================

    titulo_periodo = (
        "Todos los periodos"
        if periodo_filtro == "TODOS"
        else formatear_periodo(periodo_filtro)
    )

    titulo_fecha = (
        " - " + str(fecha_filtro)
        if fecha_filtro is not None
        else ""
    )

    st.title("📈 REPORTES DE PRODUCCIÓN")

    if len(unidades_filtro) == len(unidades_disponibles):
        titulo_unidad = "Todas las unidades de negocio"
    elif unidades_filtro:
        titulo_unidad = ", ".join(unidades_filtro)
    else:
        titulo_unidad = "Sin unidad seleccionada"

    st.caption(
        f"🏢 {titulo_unidad} | "
        f"📅 {titulo_periodo}{titulo_fecha}"
    )


    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Registros", f"{len(df_filtrado):,}")

    c2.metric(
        "Cantidad total producida",
        f"{df_filtrado['cantidad'].sum(skipna=True):,.0f}",
    )

    c3.metric(
        "Costo total",
        f"S/ {df_filtrado['costo_total'].sum(skipna=True):,.2f}",
    )

    cuadrillas_activas = df_filtrado["cuadrilla"].nunique()
    c4.metric("Cuadrillas activas", f"{cuadrillas_activas:,}")


    # ============================================================
    # TODOS LOS REPORTES SE MUESTRAN EN LA MISMA PÁGINA
    # (El selector "Reporte que desea visualizar" fue eliminado)
    # ============================================================

    # REPORTE 2: PRODUCCIÓN POR CUADRILLA
    # ============================================================

    st.divider()
    st.subheader("📊 Producción por cuadrilla")

    por_cuadrilla = (
        df_filtrado.groupby("cuadrilla")
        .agg(
            registros=("cantidad", "size"),
            cantidad=("cantidad", "sum"),
            costo_total=("costo_total", "sum"),
            dias_trabajados=(
                "_fecha_dt",
                lambda x: x.dropna().dt.normalize().nunique(),
            ),
        )
        .reset_index()
        .sort_values("cantidad", ascending=False)
    )

    pesta_grafico, pesta_tabla = st.tabs(["📊 Gráfico", "📋 Tabla"])

    with pesta_grafico:
        fig_cuadrilla = px.bar(
            por_cuadrilla,
            x="cuadrilla",
            y="cantidad",
            color_discrete_sequence=["#2ca02c"],
            text=por_cuadrilla["costo_total"].apply(etiqueta_costo),
            custom_data=["costo_total", "dias_trabajados"],
            title="Cantidad producida por cuadrilla (etiqueta = costo total S/)",
        )

        fig_cuadrilla.update_traces(
            hovertemplate=(
                "Cuadrilla: %{x}<br>"
                "Cantidad: %{y:,.0f}<br>"
                "Costo total: S/ %{customdata[0]:,.2f}<br>"
                "Días trabajados: %{customdata[1]}"
                "<extra></extra>"
            ),
            **estilo_barra_con_costo(por_cuadrilla["cantidad"]),
        )

        fig_cuadrilla.update_layout(
            xaxis_title="Cuadrilla / Técnico",
            yaxis_title="Cantidad",
            showlegend=False,
        )

        fijar_visibilidad_texto(fig_cuadrilla)
        mostrar_grafico(fig_cuadrilla)

    with pesta_tabla:
        por_cuadrilla_mostrar = por_cuadrilla.copy()
        por_cuadrilla_mostrar["costo_total"] = (
            por_cuadrilla_mostrar["costo_total"].round(2)
        )

        st.dataframe(
            por_cuadrilla_mostrar,
            use_container_width=True,
            hide_index=True,
        )

        descargar_excel(
            por_cuadrilla_mostrar,
            f"produccion_por_cuadrilla_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )


    # ============================================================
    # REPORTE 3: MONTO POR CUADRILLA
    # ============================================================

    st.divider()
    st.subheader("📊 Monto por cuadrilla")

    monto_cuadrilla = (
        df_filtrado.groupby("cuadrilla")
        .agg(
            monto=("costo_total", "sum"),
            registros=("cantidad", "size"),
            cantidad=("cantidad", "sum"),
        )
        .reset_index()
        .sort_values("monto", ascending=False)
    )

    pesta_grafico, pesta_tabla = st.tabs(["📊 Gráfico", "📋 Tabla"])

    with pesta_grafico:
        fig_monto = px.bar(
            monto_cuadrilla,
            x="cuadrilla",
            y="monto",
            color_discrete_sequence=["#d62728"],
            text=monto_cuadrilla["monto"].apply(etiqueta_costo),
            custom_data=["monto", "cantidad", "registros"],
            title="Monto (S/) por cuadrilla",
        )

        fig_monto.update_traces(
            hovertemplate=(
                "Cuadrilla: %{x}<br>"
                "Monto: S/ %{customdata[0]:,.2f}<br>"
                "Cantidad producida: %{customdata[1]:,.0f}<br>"
                "Registros: %{customdata[2]}"
                "<extra></extra>"
            ),
            **estilo_barra_con_costo(monto_cuadrilla["monto"]),
        )

        fig_monto.update_layout(
            xaxis_title="Cuadrilla / Técnico",
            yaxis=dict(title="Monto (S/)"),
            showlegend=False,
        )

        fijar_visibilidad_texto(fig_monto)
        mostrar_grafico(fig_monto)

    with pesta_tabla:
        monto_cuadrilla_mostrar = monto_cuadrilla.copy()
        monto_cuadrilla_mostrar["monto"] = (
            monto_cuadrilla_mostrar["monto"].round(2)
        )

        st.dataframe(
            monto_cuadrilla_mostrar,
            use_container_width=True,
            hide_index=True,
        )

        descargar_excel(
            monto_cuadrilla_mostrar,
            f"monto_por_cuadrilla_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )


    # ============================================================
    # REPORTE 4: PRODUCCIÓN POR ZONA
    # ============================================================

    st.divider()
    st.subheader("📊 Producción por zona")

    por_zona = (
        df_filtrado.groupby("zona")
        .agg(
            registros=("cantidad", "size"),
            cantidad=("cantidad", "sum"),
            costo_total=("costo_total", "sum"),
        )
        .reset_index()
        .sort_values("cantidad", ascending=False)
    )

    c1, c2 = st.columns([2, 1])

    with c1:
        fig_zona = px.bar(
            por_zona,
            x="zona",
            y="cantidad",
            color="zona",
            color_discrete_map={
                "UB": "#1f77b4",
                "UR": "#ff7f0e",
                "R": "#2ca02c",
            },
            text=por_zona["costo_total"].apply(etiqueta_costo),
            custom_data=["costo_total", "registros"],
            title="Producción por zona (etiqueta = costo total S/)",
        )

        fig_zona.update_traces(
            hovertemplate=(
                "Zona: %{x}<br>"
                "Cantidad: %{y:,.0f}<br>"
                "Costo total: S/ %{customdata[0]:,.2f}<br>"
                "Registros: %{customdata[1]}"
                "<extra></extra>"
            ),
            **estilo_barra_con_costo(por_zona["cantidad"]),
        )

        fig_zona.update_layout(
            showlegend=False,
            xaxis_title="Zona",
            yaxis_title="Cantidad",
        
            margin=dict(l=10, r=10, t=50, b=10),
        )

        fijar_visibilidad_texto(fig_zona)
        mostrar_grafico(fig_zona)

    with c2:
        por_zona_mostrar = por_zona.copy()
        por_zona_mostrar["costo_total"] = (
            por_zona_mostrar["costo_total"].round(2)
        )

        st.dataframe(
            por_zona_mostrar,
            use_container_width=True,
            hide_index=True,
        )

        descargar_excel(
            por_zona_mostrar,
            f"produccion_por_zona_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )


    # ============================================================
    # REPORTE 5: PRODUCCIÓN POR PROCESO
    # ============================================================

    st.divider()
    st.subheader("📊 Producción por proceso")

    por_proceso = (
        df_filtrado.groupby("proceso")
        .agg(
            registros=("cantidad", "size"),
            cantidad=("cantidad", "sum"),
            costo_total=("costo_total", "sum"),
            cuadrillas=("cuadrilla", "nunique"),
        )
        .reset_index()
        .sort_values("cantidad", ascending=False)
    )

    pesta_grafico, pesta_tabla = st.tabs(["📊 Gráfico", "📋 Tabla"])

    with pesta_grafico:
        fig_proceso = px.bar(
            por_proceso,
            x="proceso",
            y="cantidad",
            color="proceso",
            text=por_proceso["costo_total"].apply(etiqueta_costo),
            custom_data=["costo_total", "registros", "cuadrillas"],
            title="Cantidad producida por proceso (etiqueta = costo total S/)",
        )

        fig_proceso.update_traces(
            hovertemplate=(
                "Proceso: %{x}<br>"
                "Cantidad: %{y:,.0f}<br>"
                "Costo total: S/ %{customdata[0]:,.2f}<br>"
                "Registros: %{customdata[1]}<br>"
                "Cuadrillas: %{customdata[2]}"
                "<extra></extra>"
            ),
            # Los montos deben mostrarse completos también en barras pequeñas.
            textposition="outside",
            textfont=dict(size=13),
            cliponaxis=False,
        )

        fig_proceso.update_layout(
            showlegend=False,
            xaxis_title="Proceso",
            yaxis_title="Cantidad",
        
            margin=dict(l=10, r=10, t=50, b=10),
        )

        fijar_visibilidad_texto(fig_proceso)
        fig_proceso.update_layout(uniformtext_mode="show", uniformtext_minsize=12)
        mostrar_grafico(fig_proceso)

    with pesta_tabla:
        por_proceso_mostrar = por_proceso.copy()
        por_proceso_mostrar["costo_total"] = (
            por_proceso_mostrar["costo_total"].round(2)
        )

        st.dataframe(
            por_proceso_mostrar,
            use_container_width=True,
            hide_index=True,
        )

        descargar_excel(
            por_proceso_mostrar,
            f"produccion_por_proceso_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )


    # ============================================================
    # REPORTE 6: TODOS LOS CÓDIGOS DE ACTIVIDAD
    # ============================================================

    st.divider()
    st.subheader("📊 Códigos y actividades")

    top_codigos = (
        df_filtrado.groupby(["codigo", "actividad"])
        .agg(
            cantidad=("cantidad", "sum"),
            costo_total=("costo_total", "sum"),
        )
        .reset_index()
        .sort_values("cantidad", ascending=False)
    )

    pesta_grafico, pesta_tabla = st.tabs(["📊 Gráfico", "📋 Tabla"])

    with pesta_grafico:
        # La navegación de este fragmento no reejecuta el dashboard completo.
        @st.fragment
        def render_codigos_paginados():
            # Navegación por grupos de cinco columnas para evitar etiquetas comprimidas.
            columnas_por_pagina = 5
            total_paginas = max(1, (len(top_codigos) + columnas_por_pagina - 1) // columnas_por_pagina)
            clave_pagina = "pagina_top_codigos_actividad"
            if clave_pagina not in st.session_state:
                st.session_state[clave_pagina] = 0
            st.session_state[clave_pagina] = min(
                max(0, st.session_state[clave_pagina]), total_paginas - 1
            )

            pagina_actual = st.session_state[clave_pagina]
            inicio = pagina_actual * columnas_por_pagina
            top_pagina = top_codigos.iloc[inicio:inicio + columnas_por_pagina].copy()
            # Las categorías incorporan el nombre de actividad además del código.
            # Identificador posicional: evita unir columnas con códigos repetidos.
            top_pagina["_posicion"] = [str(i) for i in range(inicio, inicio + len(top_pagina))]

            fig_top = px.bar(
                top_pagina,
                x="_posicion",
                y="cantidad",
                color_discrete_sequence=["#9467bd"],
                text=top_pagina["costo_total"].apply(etiqueta_costo),
                custom_data=["codigo", "actividad", "costo_total"],
                title="Códigos y actividades (etiqueta = costo total S/)",
            )
            fig_top.update_traces(
                hovertemplate=(
                    "Código: %{customdata[0]}<br>"
                    "Actividad: %{customdata[1]}<br>"
                    "Cantidad: %{y:,.0f}<br>"
                    "Costo total: S/ %{customdata[2]:,.2f}"
                    "<extra></extra>"
                ),
                textposition="outside",
                textfont=dict(size=12),
                cliponaxis=False,
            )
            etiquetas = [
                str(codigo) + "<br>" + (
                    "<br>".join(
                        str(actividad or "Sin actividad")[i:i+24]
                        for i in range(0, len(str(actividad or "Sin actividad")), 24)
                    )
                )
                for codigo, actividad in zip(top_pagina["codigo"], top_pagina["actividad"])
            ]
            fig_top.update_xaxes(
                title="Código y actividad",
                tickmode="array",
                tickvals=top_pagina["_posicion"].tolist(),
                ticktext=etiquetas,
                tickangle=0,
                tickfont=dict(size=10),
                automargin=True,
            )
            fig_top.update_layout(
                yaxis_title="Cantidad",
                height=570,
                margin=dict(l=60, r=35, t=65, b=190),
                uniformtext_mode="show",
                uniformtext_minsize=10,
            )
            fijar_visibilidad_texto(fig_top)
            # Mantener la escala desde cero incluso después de hacer clic o arrastrar.
            # No afecta a los demás gráficos ni a la paginación.
            max_cantidad = pd.to_numeric(top_pagina["cantidad"], errors="coerce").fillna(0).max()
            max_cantidad = max(float(max_cantidad), 0.0)
            fig_top.update_yaxes(
                range=[0, max_cantidad * 1.28 if max_cantidad > 0 else 1],
                autorange=False,
                fixedrange=True,
                automargin=True,
            )
            fig_top.update_xaxes(fixedrange=True)
            fig_top.update_layout(
                dragmode=False,
                clickmode="none",
                uirevision=f"codigos_pagina_{pagina_actual}",
                selectionrevision=f"codigos_pagina_{pagina_actual}",
            )
            # Sin herramientas de zoom ni selección; conserva el tooltip al pasar el ratón.
            st.plotly_chart(
                fig_top,
                use_container_width=True,
                theme="streamlit",
                config={
                    "responsive": True,
                    "displaylogo": False,
                    "displayModeBar": False,
                    "scrollZoom": False,
                    "doubleClick": False,
                    "editable": False,
                },
                key="grafico_top_codigos_paginado",
            )

            anterior, indicador, siguiente = st.columns([1, 3, 1])
            with anterior:
                if st.button("◀ Anterior", key="top_codigos_anterior",
                             disabled=pagina_actual == 0, use_container_width=True):
                    st.session_state[clave_pagina] -= 1
                    st.rerun(scope="fragment")
            with indicador:
                st.markdown(
                    f"<p style='text-align:center'>Mostrando {inicio + 1}–"
                    f"{inicio + len(top_pagina)} de {len(top_codigos)} "
                    f"(página {pagina_actual + 1} de {total_paginas})</p>",
                    unsafe_allow_html=True,
                )
            with siguiente:
                if st.button("Siguiente ▶", key="top_codigos_siguiente",
                             disabled=pagina_actual >= total_paginas - 1,
                             use_container_width=True):
                    st.session_state[clave_pagina] += 1
                    st.rerun(scope="fragment")

        render_codigos_paginados()

    with pesta_tabla:
        top_codigos_mostrar = top_codigos.copy()
        top_codigos_mostrar["costo_total"] = (
            top_codigos_mostrar["costo_total"].round(2)
        )

        st.dataframe(
            top_codigos_mostrar,
            use_container_width=True,
            hide_index=True,
        )

        descargar_excel(
            top_codigos_mostrar,
            f"codigos_actividades_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )


    # ============================================================
    # REPORTE 7: RESUMEN CUADRILLA POR DÍA
    # ============================================================

    st.divider()
    st.subheader("📊 Resumen cuadrilla por día")

    df_pivote = df_filtrado.dropna(subset=["_fecha_dt"]).copy()

    if df_pivote.empty:
        st.warning("No hay fechas válidas para generar el resumen.")
    else:
        df_pivote["dia"] = df_pivote["_fecha_dt"].dt.strftime("%d/%m/%Y")

        pivote_cantidad = df_pivote.pivot_table(
            index="cuadrilla",
            columns="dia",
            values="cantidad",
            aggfunc="sum",
            fill_value=0,
        )

        st.dataframe(
            pivote_cantidad,
            use_container_width=True,
            height=350,
        )

        descargar_excel(
            pivote_cantidad.reset_index(),
            f"resumen_cuadrilla_dia_{datetime.now().strftime('%Y%m%d')}.xlsx",
        )


    # ============================================================
    # REPORTE 8: DETALLE COMPLETO
    # ============================================================

    st.divider()
    st.subheader("📊 Detalle de registros")

    st.dataframe(
        df_filtrado,
        use_container_width=True,
        hide_index=True,
    )

    descargar_excel(
        df_filtrado,
        f"detalle_produccion_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
    )


    # ============================================================
    # ACTUALIZAR DATOS
    # ============================================================

    st.sidebar.divider()

    if st.sidebar.button("🔄 Refrescar datos", use_container_width=True):
        clear_sheet(SPREADSHEET_ID, HOJA_ORIGEN)
        cargar_datos.clear()
        st.rerun()

    st.sidebar.caption(
        "Los datos se mantienen en caché durante 30 minutos "
        "o puedes recargarlos con el botón 'Refrescar datos'."
    )