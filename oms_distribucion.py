import streamlit as st
import pandas as pd
import gspread
import plotly.graph_objects as go

from google.oauth2.service_account import Credentials
from datetime import date, datetime
from zoneinfo import ZoneInfo
import calendar
def render_html(html):

    if hasattr(st, "html"):
        st.html(html)
    else:
        st.markdown(
            html,
            unsafe_allow_html=True
        )


# ============================================================
# CONFIGURACIÓN GOOGLE SHEETS
# ============================================================

ID_REGISTRO = "1Q5nFlkZRWxoCPDwxqEIX_llEJglsY7vHSfYPr2YNLMM"
HOJA_REGISTRO = "REGISTROS"

ID_CECO = "1_QWDZC4GSIB3pGasgZqo51s5aOrZLWXbjWx3edb14Cw"
HOJA_CECO = "BD_CECO"


# ============================================================
# METAS
# ============================================================

METAS = {
    "ITEM I": 300299.99,
    "ITEM II": 450000.00,
    "ITEM III": 450000.00,
    "ITEM IV": 450000.00,
    "ITEM IV URBANO": 450000.00
}

def render():
    # ============================================================
    # ESTILOS
    # ============================================================
    
    render_html(
        """
        <style>
    
            .stApp {
                background:
                    radial-gradient(
                        circle at top left,
                        rgba(178, 13, 13, 0.05),
                        transparent 35%
                    ),
                    linear-gradient(
                        135deg,
                        #f7f8fa 0%,
                        #eef1f5 100%
                    );
            }
    
            .block-container {
                max-width: 1450px;
                padding-top: 1.5rem;
                padding-bottom: 3rem;
            }
    
            #MainMenu {
                visibility: hidden;
            }
    
            footer {
                visibility: hidden;
            }
    
            header {
                visibility: hidden;
            }
    
            .dashboard-header {
                text-align: center;
                margin-bottom: 28px;
            }
    
            .dashboard-title {
                font-size: 42px;
                font-weight: 800;
                line-height: 1.1;
                margin-bottom: 8px;
    
                background: linear-gradient(
                    135deg,
                    #333333 0%,
                    #B20D0D 100%
                );
    
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
    
            .dashboard-subtitle {
                color: #6c757d;
                font-size: 16px;
                font-weight: 500;
            }
    
            .filter-box {
                background: rgba(255, 255, 255, 0.90);
                border: 1px solid #dee2e6;
                border-radius: 20px;
                padding: 18px 22px 10px 22px;
                box-shadow: 0 8px 30px rgba(0, 0, 0, 0.06);
                margin-bottom: 22px;
            }
    
            .kpi {
                background: rgba(255, 255, 255, 0.95);
                border: 1px solid #dee2e6;
                border-radius: 20px;
                padding: 20px 18px;
                min-height: 150px;
                box-shadow: 0 8px 28px rgba(0, 0, 0, 0.055);
                position: relative;
                overflow: hidden;
            }
    
            .kpi::before {
                content: "";
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: #B20D0D;
            }
    
            .kpi-title {
                color: #6c757d;
                font-size: 13px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.5px;
                margin-bottom: 12px;
            }
    
            .kpi-value {
                color: #333333;
                font-size: 29px;
                font-weight: 800;
                line-height: 1.15;
                word-break: break-word;
            }
    
            .kpi-icon {
                font-size: 25px;
                margin-bottom: 8px;
            }
    
            .avance-rojo::before {
                background: #B20D0D;
            }
    
            .avance-amarillo::before {
                background: #f59e0b;
            }
    
            .avance-verde::before {
                background: #10b981;
            }
    
            .stat-box {
                background: rgba(255, 255, 255, 0.90);
                border: 1px solid #dee2e6;
                border-radius: 16px;
                padding: 15px;
                text-align: center;
                box-shadow: 0 5px 18px rgba(0, 0, 0, 0.04);
            }
    
            .stat-value {
                font-size: 21px;
                font-weight: 800;
                color: #333333;
            }
    
            .stat-title {
                color: #6c757d;
                font-size: 12px;
                font-weight: 600;
                margin-top: 3px;
            }
    
            .section-title {
                font-size: 20px;
                font-weight: 750;
                color: #333333;
                margin-top: 20px;
                margin-bottom: 4px;
            }
    
            .section-subtitle {
                color: #6c757d;
                font-size: 13px;
                margin-bottom: 8px;
            }
    
            div[data-baseweb="select"] > div {
                border-radius: 12px;
                border: 1px solid #dee2e6;
            }
    
            div[data-baseweb="select"] > div:focus-within {
                border-color: #B20D0D;
                box-shadow: 0 0 0 1px #B20D0D;
            }
    
            @media (max-width: 768px) {
    
                .block-container {
                    padding: 12px 10px 30px 10px;
                }
    
                .dashboard-title {
                    font-size: 29px;
                }
    
                .dashboard-subtitle {
                    font-size: 13px;
                }
    
                .kpi {
                    min-height: 125px;
                    padding: 15px;
                }
    
                .kpi-value {
                    font-size: 22px;
                }
    
                .stat-value {
                    font-size: 18px;
                }
            }
    
        </style>
        """
    )


# ============================================================
# GOOGLE AUTH
# ============================================================

@st.cache_resource
def conectar_google():

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly"
    ]

    credentials = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes
    )

    return gspread.authorize(credentials)


# ============================================================
# CARGAR REGISTROS
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_registros():

    client = conectar_google()

    spreadsheet = client.open_by_key(
        ID_REGISTRO
    )

    hoja = spreadsheet.worksheet(
        HOJA_REGISTRO
    )

    data = hoja.get_all_values()

    if len(data) <= 1:
        return pd.DataFrame()

    encabezados = data[0]
    filas = data[1:]

    return pd.DataFrame(
        filas,
        columns=encabezados
    )


# ============================================================
# CARGAR CECO
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def cargar_ceco():

    client = conectar_google()

    spreadsheet = client.open_by_key(
        ID_CECO
    )

    hoja = spreadsheet.worksheet(
        HOJA_CECO
    )

    data = hoja.get_all_values()

    if len(data) <= 1:
        return pd.DataFrame()

    filas = data[1:]

    df = pd.DataFrame(
        filas,
        columns=[
            "item",
            "unidad",
            "servicio",
            "cuadrilla",
            "ceco",
            "costo"
        ]
    )

    df["costo"] = df["costo"].apply(convertir_importe)

    return df


# ============================================================
# FORMATO SOLES
# ============================================================

def formato_soles(valor):

    return (
        f"S/ {valor:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


# ============================================================
# FORMATO ENTERO
# ============================================================

def formato_entero(valor):

    return (
        f"{valor:,.0f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


# ============================================================
# CONVERTIR FECHA
# ============================================================

def convertir_fecha(serie):
    # FECHA_FIN puede venir como dd/mm/yyyy, dd-mm-yyyy o yyyy-mm-dd.
    return pd.to_datetime(
        serie.astype(str).str.strip(),
        errors="coerce",
        dayfirst=True
    )


def convertir_importe(valor):
    """Convierte importes de Sheets en formato peruano o internacional."""
    if pd.isna(valor):
        return 0.0
    texto = str(valor).strip().replace("S/", "").replace("s/", "")
    texto = texto.replace(" ", "")
    if not texto:
        return 0.0

    coma = texto.rfind(",")
    punto = texto.rfind(".")

    if coma >= 0 and punto >= 0:
        # El separador más a la derecha es el decimal.
        if coma > punto:
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif coma >= 0:
        decimales = len(texto) - coma - 1
        texto = texto.replace(".", "")
        texto = texto.replace(",", ".") if decimales in (1, 2) else texto.replace(",", "")
    elif punto >= 0 and texto.count(".") > 1:
        partes = texto.split(".")
        decimal = partes.pop()
        texto = "".join(partes) + ("." + decimal if len(decimal) in (1, 2) else decimal)

    try:
        return float(texto)
    except (TypeError, ValueError):
        return 0.0


# ============================================================
# DÍAS DEL MES
# ============================================================

def dias_del_mes(anio, mes):

    return calendar.monthrange(
        anio,
        mes
    )[1]


def dias_transcurridos(anio, mes):

    # Obtener fecha actual según horario de Perú
    hoy = datetime.now(
        ZoneInfo("America/Lima")
    ).date()

    if (
        hoy.year == anio
        and hoy.month == mes
    ):
        return hoy.day

    return dias_del_mes(
        anio,
        mes
    )


# ============================================================
# CLASE AVANCE
# ============================================================

def clase_avance(porcentaje):

    if porcentaje < 70:
        return "avance-rojo"

    if porcentaje < 90:
        return "avance-amarillo"

    return "avance-verde"


# ============================================================
# GRÁFICO VACÍO
# ============================================================

def grafico_vacio(mensaje):

    fig = go.Figure()

    fig.add_annotation(
        text=mensaje,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(
            size=18,
            color="#6c757d"
        )
    )

    fig.update_layout(
        height=380,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False)
    )

    return fig


# ============================================================
# CARGA DE DATOS
# ============================================================

try:

    with st.spinner("Cargando información..."):

        registros = cargar_registros()
        registros.columns = registros.columns.astype(str).str.strip()
        ceco = cargar_ceco()

except Exception as e:

    st.error(
        "No fue posible conectar con Google Sheets."
    )

    st.code(
        str(e)
    )

    st.stop()


# ============================================================
# VALIDAR REGISTROS
# ============================================================

if registros.empty:

    st.warning(
        "La hoja REGISTROS no contiene información."
    )

    st.stop()


# ============================================================
# VALIDAR COLUMNAS MÍNIMAS
# ============================================================

columnas_requeridas = [
    "ITEM",
    "FECHA_FIN",
    "MONTO_PRE_VALORIZADO",
    "UNIDAD_DE_NEGOCIO",
    "SERVICIO_ELECTRICO",
]

columnas_faltantes = [
    columna for columna in columnas_requeridas
    if columna not in registros.columns
]

if columnas_faltantes:
    st.error(
        "Faltan columnas requeridas en la hoja REGISTROS: "
        + ", ".join(columnas_faltantes)
    )
    st.stop()


# ============================================================
# PREPARAR REGISTROS
# ============================================================

# FECHA_FIN (columna I) y MONTO_PRE_VALORIZADO (columna P).
registros["_fecha"] = convertir_fecha(
    registros["FECHA_FIN"]
)

registros["_pre"] = registros["MONTO_PRE_VALORIZADO"].apply(
    convertir_importe
)


# ============================================================
# HEADER
# ============================================================

render_html(
    """
    <div class="dashboard-header">
        <div class="dashboard-title">
            📊 Dashboard Control OMs
        </div>

        <div class="dashboard-subtitle">
            Monitoreo de producción, capacidad y avance
        </div>
    </div>
    """
)


# ============================================================
# FILTROS
# ============================================================

render_html(
    """
    <div class="filter-box">
    """
)

col1, col2 = st.columns(2)


# ============================================================
# PERIODOS
# ============================================================

periodos_df = registros[
    registros["_fecha"].notna()
].copy()

periodos = (
    periodos_df["_fecha"]
    .dt.to_period("M")
    .dropna()
    .unique()
)

periodos = sorted(
    periodos,
    reverse=True
)

opciones_periodo = {
    "Seleccione periodo...": None
}

for periodo in periodos:

    fecha_periodo = periodo.to_timestamp()

    texto = (
        fecha_periodo
        .strftime("%B %Y")
        .capitalize()
    )

    clave = (
        f"{fecha_periodo.year}-"
        f"{fecha_periodo.month}"
    )

    opciones_periodo[texto] = clave


with col1:

    periodo_nombre = st.selectbox(
        "📅 Periodo",
        list(opciones_periodo.keys()),
        index=0,
        key="select_periodo"
    )

    periodo_seleccionado = (
        opciones_periodo[
            periodo_nombre
        ]
    )


# ============================================================
# ITEMS
# ============================================================

items = sorted(
    registros["ITEM"]
    .dropna()
    .astype(str)
    .str.strip()
    .unique()
)

opciones_item = [
    "Seleccione item..."
] + items


with col2:

    item_seleccionado = st.selectbox(
        "📋 Item",
        opciones_item,
        index=0,
        key="select_item"
    )


render_html(
    """
    </div>
    """
)


# ============================================================
# FILTRAR
# ============================================================

data = registros.copy()


if periodo_seleccionado:

    anio, mes = map(
        int,
        periodo_seleccionado.split("-")
    )

    data = data[
        (data["_fecha"].dt.year == anio)
        &
        (data["_fecha"].dt.month == mes)
    ]


if item_seleccionado != "Seleccione item...":

    data = data[
        data["ITEM"].astype(str).str.strip()
        == item_seleccionado
    ]


# ============================================================
# STATS
# ============================================================

if (
    periodo_seleccionado
    and item_seleccionado != "Seleccione item..."
):

    anio, mes = map(
        int,
        periodo_seleccionado.split("-")
    )

    dias_mes = dias_del_mes(
        anio,
        mes
    )

    dias_trans = dias_transcurridos(
        anio,
        mes
    )

    ceco_item = ceco[
        ceco["item"]
        .astype(str)
        .str.strip()
        ==
        item_seleccionado
    ]

    costo_cuadrilla_total = (
        ceco_item["costo"].sum()
    )

    costo_diario = (
        costo_cuadrilla_total / dias_mes
        if dias_mes
        else 0
    )

    # Capacidad = (suma COSTO_CUADRILLA del ITEM / días del mes)
    #             * días transcurridos del periodo.
    cuadrilla = costo_diario * dias_trans

    pre = data["_pre"].sum()

    meta = METAS.get(
        item_seleccionado,
        0
    )

    avance = pre + cuadrilla

    porcentaje = (
        (avance / meta) * 100
        if meta
        else 0
    )

    color_clase = clase_avance(
        porcentaje
    )

else:

    pre = 0
    cuadrilla = 0
    meta = 0
    avance = 0
    porcentaje = 0
    dias_mes = 0
    dias_trans = 0
    costo_diario = 0

    color_clase = "avance-rojo"


# ============================================================
# KPIs
# ============================================================

k1, k2, k3, k4 = st.columns(4)


with k1:

    render_html(
        f"""
        <div class="kpi">

            <div class="kpi-icon">
                💰
            </div>

            <div class="kpi-title">
                Pre Valorizado
            </div>

            <div class="kpi-value">
                {
                    formato_soles(pre)
                    if item_seleccionado != "Seleccione item..."
                    else "Seleccione ITEM"
                }
            </div>

        </div>
        """
    )


with k2:

    render_html(
        f"""
        <div class="kpi">

            <div class="kpi-icon">
                👥
            </div>

            <div class="kpi-title">
                Costo Cuadrilla
            </div>

            <div class="kpi-value">
                {
                    formato_soles(cuadrilla)
                    if item_seleccionado != "Seleccione item..."
                    else "-"
                }
            </div>

        </div>
        """
    )


with k3:

    render_html(
        f"""
        <div class="kpi">

            <div class="kpi-icon">
                🎯
            </div>

            <div class="kpi-title">
                Meta
            </div>

            <div class="kpi-value">
                {
                    formato_soles(meta)
                    if item_seleccionado != "Seleccione item..."
                    else "-"
                }
            </div>

        </div>
        """
    )


with k4:

    render_html(
        f"""
        <div class="kpi {color_clase}">

            <div class="kpi-icon">
                📈
            </div>

            <div class="kpi-title">
                % Avance
            </div>

            <div class="kpi-value">
                {
                    f"{porcentaje:.1f}%"
                    if item_seleccionado != "Seleccione item..."
                    else "-"
                }
            </div>

        </div>
        """
    )


# ============================================================
# STATS
# ============================================================

if (
    periodo_seleccionado
    and item_seleccionado != "Seleccione item..."
):

    st.markdown("<br>", unsafe_allow_html=True)

    s1, s2, s3, s4 = st.columns(4)

    with s1:

        render_html(
            f"""
            <div class="stat-box">

                <div class="stat-value">
                    {formato_entero(len(data))}
                </div>

                <div class="stat-title">
                    Total Registros
                </div>

            </div>
            """
        )

    with s2:

        render_html(
            f"""
            <div class="stat-box">

                <div class="stat-value">
                    {dias_trans}
                </div>

                <div class="stat-title">
                    Días Transcurridos
                </div>

            </div>
            """
        )

    with s3:

        render_html(
            f"""
            <div class="stat-box">

                <div class="stat-value">
                    {dias_mes}
                </div>

                <div class="stat-title">
                    Días del Mes
                </div>

            </div>
            """
        )

    with s4:

        render_html(
            f"""
            <div class="stat-box">

                <div class="stat-value">
                    {formato_soles(costo_diario)}
                </div>

                <div class="stat-title">
                    Costo Diario
                </div>

            </div>
            """
        )


# ============================================================
# SI NO HAY ITEM
# ============================================================

if item_seleccionado == "Seleccione item...":

    st.info(
        "📌 Selecciona un periodo y un item para visualizar "
        "los indicadores y gráficos."
    )

    st.stop()


# ============================================================
# PRODUCCIÓN VS CAPACIDAD
# ============================================================

render_html(
    """
    <div class="section-title">
        ⚖️ Producción vs Capacidad
    </div>

    <div class="section-subtitle">
        Comparación entre la producción valorizada y la
        costo de cuadrilla prorrateado según los días transcurridos.
    </div>
    """
)


fig_comparativo = go.Figure()


fig_comparativo.add_trace(
    go.Bar(

        x=[
            "💰 Producción",
            "👥 Capacidad"
        ],

        y=[
            pre,
            cuadrilla
        ],

        text=[
            formato_soles(pre),
            formato_soles(cuadrilla)
        ],

        textposition="outside",

        textfont=dict(
            color="#111827",
            size=14
        ),

        marker=dict(
            color=[
                "#2563eb",
                "#f59e0b"
            ],

            line=dict(
            width=0
            )
        ),

        hovertemplate=(
            "<b>%{x}</b><br>"
            "Monto: S/ %{y:,.2f}"
            "<extra></extra>"
        )
    )
)


fig_comparativo.update_layout(

    height=410,

    # ========================================================
    # FONDO FIJO CLARO
    # No depende del modo oscuro del navegador
    # ========================================================

    paper_bgcolor="#ffffff",
    plot_bgcolor="#ffffff",

    margin=dict(
        l=25,
        r=25,
        t=35,
        b=55
    ),

    showlegend=False,

    hovermode="closest",

    # ========================================================
    # BLOQUEAR SELECCIÓN / ZOOM / MOVIMIENTO
    # ========================================================

    clickmode="none",

    dragmode=False,

    uirevision="dashboard",

    # ========================================================
    # EJE Y
    # ========================================================

    yaxis=dict(

        title=dict(
            text="Monto (S/)",
            font=dict(
                color="#374151",
                size=13
            )
        ),

        tickfont=dict(
            color="#374151",
            size=11
        ),

        gridcolor="#e5e7eb",

        zeroline=False,

        fixedrange=True
    ),

    # ========================================================
    # EJE X
    # ========================================================

    xaxis=dict(

        showgrid=False,

        tickfont=dict(
            color="#111827",
            size=12
        ),

        fixedrange=True
    ),

    # ========================================================
    # FUENTE GENERAL DEL GRÁFICO
    # ========================================================

    font=dict(
        family="Arial, sans-serif",
        color="#111827"
    )
)


st.plotly_chart(
    fig_comparativo,

    use_container_width=True,

    key="grafico_produccion_capacidad",

    config={
        "displayModeBar": False,
        "responsive": True,
        "scrollZoom": False,
        "doubleClick": False,
        "editable": False
    }
)
# ============================================================
# DISTRIBUCIÓN POR UNIDAD
# ============================================================

render_html(
    """
    <div class="section-title">
        🏢 Distribución por Unidad
    </div>

    <div class="section-subtitle">
        Producción valorizada agrupada por unidad.
    </div>
    """
)


if not data.empty:

    # --------------------------------------------------------
    # AGRUPACIÓN UNIDAD
    # --------------------------------------------------------

    unidad_data = (
        data.assign(
            _unidad=data["UNIDAD_DE_NEGOCIO"]
            .fillna("")
            .astype(str)
            .str.strip()
            .replace("", "(Sin unidad)")
        )
        .groupby("_unidad")["_pre"]
        .sum()
        .sort_values(ascending=False)
    )

    # --------------------------------------------------------
    # COLORES DIFERENTES
    # --------------------------------------------------------

    colores_unidad_base = [
        "#2563eb",
        "#10b981",
        "#f59e0b",
        "#ef4444",
        "#8b5cf6",
        "#06b6d4",
        "#ec4899",
        "#84cc16",
        "#f97316",
        "#6366f1",
        "#14b8a6",
        "#e11d48"
    ]

    colores_unidad = [
        colores_unidad_base[
            i % len(colores_unidad_base)
        ]
        for i in range(
            len(unidad_data)
        )
    ]

    # --------------------------------------------------------
    # TEXTO VISIBLE
    # --------------------------------------------------------

    textos_unidad = [
        formato_soles(valor)
        for valor in unidad_data.values
    ]

    # --------------------------------------------------------
    # GRÁFICO
    # --------------------------------------------------------

    fig_unidad = go.Figure()

    fig_unidad.add_trace(
        go.Bar(

            x=unidad_data.index,

            y=unidad_data.values,

            text=textos_unidad,

            textposition="outside",

            textfont=dict(
                color="#111827",
                size=13
            ),

            marker=dict(
                color=colores_unidad,

                line=dict(
                    width=0
                )
            ),

            hovertemplate=(
                "<b>Unidad: %{x}</b><br>"
                "Producción: S/ %{y:,.2f}"
                "<extra></extra>"
            )
        )
    )

    fig_unidad.update_layout(

        # ----------------------------------------------------
        # TAMAÑO
        # ----------------------------------------------------

        height=460,

        # ----------------------------------------------------
        # FONDO FIJO BLANCO
        # No depende del modo oscuro del navegador
        # ----------------------------------------------------

        paper_bgcolor="#ffffff",

        plot_bgcolor="#ffffff",

        # ----------------------------------------------------
        # MÁRGENES
        # ----------------------------------------------------

        margin=dict(
            l=25,
            r=25,
            t=45,
            b=100
        ),

        showlegend=False,

        # ----------------------------------------------------
        # HOVER
        # ----------------------------------------------------

        hovermode="closest",

        # ----------------------------------------------------
        # BLOQUEAR SELECCIÓN
        # ----------------------------------------------------

        clickmode="none",

        # ----------------------------------------------------
        # BLOQUEAR MOVIMIENTO / ZOOM
        # ----------------------------------------------------

        dragmode=False,

        # ----------------------------------------------------
        # MANTENER ESTADO
        # ----------------------------------------------------

        uirevision="dashboard",

        # ----------------------------------------------------
        # EJE X
        # ----------------------------------------------------

        xaxis=dict(

            showgrid=False,

            tickangle=-25,

            tickfont=dict(
                size=12,
                color="#111827"
            ),

            title=dict(
                text="UNIDAD",

                font=dict(
                    size=13,
                    color="#374151"
                )
            ),

            fixedrange=True
        ),

        # ----------------------------------------------------
        # EJE Y
        # ----------------------------------------------------

        yaxis=dict(

            title=dict(
                text="Monto (S/)",

                font=dict(
                    size=13,
                    color="#374151"
                )
            ),

            tickfont=dict(
                size=11,
                color="#374151"
            ),

            gridcolor="#e5e7eb",

            zeroline=False,

            fixedrange=True
        ),

        # ----------------------------------------------------
        # FUENTE
        # ----------------------------------------------------

        font=dict(
            family="Arial, sans-serif",
            color="#111827"
        )
    )

    # --------------------------------------------------------
    # MOSTRAR GRÁFICO
    # --------------------------------------------------------

    st.plotly_chart(
        fig_unidad,

        use_container_width=True,

        key="grafico_distribucion_unidad",

        config={
            "displayModeBar": False,
            "responsive": True,
            "scrollZoom": False,
            "doubleClick": False,
            "editable": False
        }
    )

else:

    st.plotly_chart(
        grafico_vacio(
            "No existen registros"
        ),
        use_container_width=True,
        key="grafico_vacio_unidad"
    )


# ============================================================
# DISTRIBUCIÓN POR SERVICIO
# ============================================================

render_html(
    """
    <div class="section-title">
        🛠️ Distribución por Servicio
    </div>

    <div class="section-subtitle">
        Producción valorizada agrupada por servicio.
    </div>
    """
)


if not data.empty:

    # --------------------------------------------------------
    # AGRUPACIÓN SERVICIO
    # --------------------------------------------------------

    servicio_agrupado = data.assign(
        _unidad=data["UNIDAD_DE_NEGOCIO"].fillna("").astype(str).str.strip()
            .replace("", "(Sin unidad)"),
        _servicio=data["SERVICIO_ELECTRICO"].fillna("").astype(str).str.strip()
            .replace("", "(Sin servicio)"),
    )

    servicio_data = (
        servicio_agrupado
        .groupby(["_unidad", "_servicio"], dropna=False)["_pre"]
        .sum()
        .sort_values(ascending=False)
    )

    # Etiqueta única para identificar la unidad y el servicio en el gráfico.
    servicio_data.index = [
        f"{unidad} - {servicio}"
        for unidad, servicio in servicio_data.index
    ]

    # --------------------------------------------------------
    # COLORES DIFERENTES
    # --------------------------------------------------------

    colores_servicio_base = [
        "#10b981",
        "#3b82f6",
        "#f59e0b",
        "#ef4444",
        "#8b5cf6",
        "#06b6d4",
        "#ec4899",
        "#84cc16",
        "#f97316",
        "#6366f1",
        "#14b8a6",
        "#e11d48",
        "#0ea5e9",
        "#a855f7"
    ]

    colores_servicio = [
        colores_servicio_base[
            i % len(colores_servicio_base)
        ]
        for i in range(
            len(servicio_data)
        )
    ]

    # --------------------------------------------------------
    # TEXTO VISIBLE
    # --------------------------------------------------------

    textos_servicio = [
        formato_soles(valor)
        for valor in servicio_data.values
    ]

    # --------------------------------------------------------
    # GRÁFICO
    # --------------------------------------------------------

    fig_servicio = go.Figure()

    fig_servicio.add_trace(
        go.Bar(

            x=servicio_data.index,

            y=servicio_data.values,

            text=textos_servicio,

            textposition="outside",

            textfont=dict(
                color="#111827",
                size=13
            ),

            marker=dict(
                color=colores_servicio,

                line=dict(
                    width=0
                )
            ),

            hovertemplate=(
                "<b>Servicio: %{x}</b><br>"
                "Producción: S/ %{y:,.2f}"
                "<extra></extra>"
            )
        )
    )

    fig_servicio.update_layout(

        # ----------------------------------------------------
        # TAMAÑO
        # ----------------------------------------------------

        height=480,

        # ----------------------------------------------------
        # FONDO FIJO BLANCO
        # ----------------------------------------------------

        paper_bgcolor="#ffffff",

        plot_bgcolor="#ffffff",

        # ----------------------------------------------------
        # MÁRGENES
        # ----------------------------------------------------

        margin=dict(
            l=25,
            r=25,
            t=45,
            b=120
        ),

        showlegend=False,

        # ----------------------------------------------------
        # HOVER
        # ----------------------------------------------------

        hovermode="closest",

        # ----------------------------------------------------
        # BLOQUEAR SELECCIÓN
        # ----------------------------------------------------

        clickmode="none",

        # ----------------------------------------------------
        # BLOQUEAR MOVIMIENTO / ZOOM
        # ----------------------------------------------------

        dragmode=False,

        # ----------------------------------------------------
        # MANTENER ESTADO
        # ----------------------------------------------------

        uirevision="dashboard",

        # ----------------------------------------------------
        # EJE X
        # ----------------------------------------------------

        xaxis=dict(

            showgrid=False,

            tickangle=-35,

            tickfont=dict(
                size=11,
                color="#111827"
            ),

            title=dict(
                text="SERVICIO",

                font=dict(
                    size=13,
                    color="#374151"
                )
            ),

            fixedrange=True
        ),

        # ----------------------------------------------------
        # EJE Y
        # ----------------------------------------------------

        yaxis=dict(

            title=dict(
                text="Monto (S/)",

                font=dict(
                    size=13,
                    color="#374151"
                )
            ),

            tickfont=dict(
                size=11,
                color="#374151"
            ),

            gridcolor="#e5e7eb",

            zeroline=False,

            fixedrange=True
        ),

        # ----------------------------------------------------
        # FUENTE
        # ----------------------------------------------------

        font=dict(
            family="Arial, sans-serif",
            color="#111827"
        )
    )

    # --------------------------------------------------------
    # MOSTRAR GRÁFICO
    # --------------------------------------------------------

    st.plotly_chart(
        fig_servicio,

        use_container_width=True,

        key="grafico_distribucion_servicio",

        config={
            "displayModeBar": False,
            "responsive": True,
            "scrollZoom": False,
            "doubleClick": False,
            "editable": False
        }
    )

else:

    st.plotly_chart(
        grafico_vacio(
            "No existen registros"
        ),
        use_container_width=True,
        key="grafico_vacio_servicio"
    )
# ============================================================
# FOOTER
# ============================================================

render_html(
    """
    <div
        style="
            text-align:center;
            margin-top:35px;
            color:#9ca3af;
            font-size:12px;
        "
    >
        Dashboard Control OMs · Streamlit
    </div>
    """
)
