import io
import re
from datetime import date, timedelta

import gspread
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sheets_cache import read_sheet, clear_sheet, CACHE_TTL
from google.oauth2.service_account import Credentials

# El tema claro/oscuro se configura en .streamlit/config.toml.
# No colocar la sección TOML [theme] dentro de este archivo Python.

SHEET_ID = "1IVNFi2DIUIRNW7jPMZ5zHA6anUtHkGeCJzN2UmooZTQ"
SHEET_TAB = "sheet1"  # Si no existe, se utiliza la primera pestaña

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stMetric"] {
    border: 1px solid var(--secondary-background-color);
    padding: 14px;
    border-radius: 12px;
}
h1, h2, h3 {letter-spacing: -0.02em;}
</style>
""", unsafe_allow_html=True)

def estabilizar_grafico(fig, altura=460, margen_inferior=90):
    """Mantiene dimensiones estables y etiquetas legibles al interactuar con el gráfico."""
    fig.update_layout(
        autosize=True,
        height=altura,
        margin=dict(t=75, r=100, b=margen_inferior, l=55),
        uniformtext_minsize=9,
        uniformtext_mode="hide",
        transition_duration=0,
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    return fig


st.title("🚚 KM_DISTRIBUCION")
st.caption("Reporte de kilometraje de Distribución · Solo lectura")

# Optional access gate: define REPORT_PASSWORD in Streamlit Secrets to protect the dashboard.
report_password = st.secrets.get("REPORT_PASSWORD", "")
if report_password:
    entered_password = st.text_input("Contraseña de acceso", type="password")
    if entered_password != report_password:
        st.info("Ingresa la contraseña para acceder a los reportes.")
        st.stop()

@st.cache_data(ttl=CACHE_TTL, show_spinner=False)
def obtener_pestana_distribucion():
    """Respeta el comportamiento original: usar la primera hoja si 'sheet1' no existe."""
    credenciales = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    libro = gspread.authorize(credenciales).open_by_key(SHEET_ID)
    try:
        return libro.worksheet(SHEET_TAB).title
    except gspread.exceptions.WorksheetNotFound:
        return libro.sheet1.title


@st.cache_data(ttl=CACHE_TTL, show_spinner="Procesando kilometraje...")
def load_records():
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError(
            "Falta configurar [gcp_service_account] en Streamlit Cloud → Settings → Secrets."
        )
    values = read_sheet(SHEET_ID, obtener_pestana_distribucion())

    if not values:
        return pd.DataFrame()

    headers = [str(x).strip() for x in values[0]]
    rows = values[1:]
    width = len(headers)
    normalized_rows = [(row[:width] + [""] * max(0, width - len(row))) for row in rows]
    df = pd.DataFrame(normalized_rows, columns=headers)

    # Use the known column order from KM_PERDIDAS as a fallback if headers are absent/misaligned.
    # Columnas A:Y de KM_DISTRIBUCION. No eliminar horarios, Nº OM ni actividad.
    expected = [
        "Fecha", "Placa", "Hora Inicio", "Km Inicial", "Hora Fin", "Km Final",
        "Tot Recorrido", "Nom Personal", "Celular", "Cuadrilla", "Item",
        "Unidad Negocio", "Servicio Electrico", "Nº OM | Cod. Recibo",
        "Descripcion Actividad", "CECO", "Foto KM Inicial", "Foto KM Final",
        "Ubicacion Inicial", "Ubicacion Final", "Observacion",
        "Marcador interno de sincronización", "COMB. GLN", "LUBR. GLNS", "Contrato",
    ]
    # Permitir encabezados escritos con variantes, sin cambiar el orden de la hoja.
    def normalizar(texto):
        import unicodedata
        texto = unicodedata.normalize("NFKD", str(texto).strip())
        texto = "".join(c for c in texto if not unicodedata.combining(c))
        return re.sub(r"[^a-z0-9]", "", texto.casefold())

    variantes = {
        "Km Inicial": ["Km Incial", "KM_INICIAL"],
        "Nº OM | Cod. Recibo": ["N° OM | Cod. Recibo", "Nro OM | Cod. Recibo"],
        "Descripcion Actividad": ["Descripción Actividad"],
        "Servicio Electrico": ["Servicio Eléctrico"],
        "Observacion": ["Observación"],
        "Unidad Negocio": ["Unidad de Negocio", "UUNN"],
    }
    nombres = {normalizar(c): c for c in df.columns if str(c).strip()}
    rename = {}
    for canonico in expected:
        if canonico in df.columns:
            continue
        for variante in [canonico] + variantes.get(canonico, []):
            original = nombres.get(normalizar(variante))
            if original and original not in rename:
                rename[original] = canonico
                break
    if rename:
        df = df.rename(columns=rename)
    # El formato del usuario fija columnas A:Y. Si el encabezado está vacío,
    # recuperar únicamente esas columnas por su posición real.
    for i, nombre in enumerate(expected):
        if nombre not in df.columns:
            if i < len(df.columns) and not str(df.columns[i]).strip():
                df[nombre] = df.iloc[:, i]
            else:
                df[nombre] = ""
    df = df[expected].copy()

    # La columna Fecha puede contener formatos mezclados en Google Sheets
    # (por ejemplo, 2026-10-06 y 13/10/2026). Parsear la columna de una sola vez
    # puede descartar fechas posteriores cuando pandas infiere un formato único.
    def parsear_fecha(valor):
        texto = str(valor).strip()
        if not texto:
            return pd.NaT
        fecha_parseada = pd.to_datetime(texto, format="%Y-%m-%d", errors="coerce")
        if pd.notna(fecha_parseada):
            return fecha_parseada
        try:
            return pd.to_datetime(texto, format="mixed", dayfirst=True, errors="coerce")
        except (TypeError, ValueError):
            return pd.to_datetime(texto, dayfirst=True, errors="coerce")

    df["Fecha"] = df["Fecha"].apply(parsear_fecha)
    for col in ["Km Inicial", "Km Final", "Tot Recorrido"]:
        df[col] = pd.to_numeric(
            df[col].astype(str).str.replace(",", "", regex=False).str.strip(),
            errors="coerce",
        )
    for col in ["Placa", "Nom Personal", "Unidad Negocio", "Servicio Electrico", "CECO", "Cuadrilla", "Item", "Contrato", "Descripcion Actividad", "Nº OM | Cod. Recibo"]:
        df[col] = df[col].fillna("").astype(str).str.strip()
    df["Placa"] = df["Placa"].str.upper().str.replace(" ", "", regex=False)
    df["Recorrido válido"] = (
        df["Km Inicial"].notna()
        & df["Km Final"].notna()
        & df["Tot Recorrido"].notna()
        & (df["Km Final"] >= df["Km Inicial"])
        & (df["Tot Recorrido"] >= 0)
    )
    # If total is missing but odometer values are valid, calculate a safe fallback.
    missing_total = df["Tot Recorrido"].isna() & df["Km Inicial"].notna() & df["Km Final"].notna()
    df.loc[missing_total, "Tot Recorrido"] = df.loc[missing_total, "Km Final"] - df.loc[missing_total, "Km Inicial"]
    df["Recorrido válido"] = (
        df["Km Inicial"].notna() & df["Km Final"].notna()
        & (df["Km Final"] >= df["Km Inicial"])
        & df["Tot Recorrido"].notna() & (df["Tot Recorrido"] >= 0)
    )
    df["Pendiente"] = df["Km Inicial"].notna() & df["Km Final"].isna()
    return df

def render():
    try:
        raw = load_records()
    except Exception as exc:
        st.error(f"No se pudo cargar Google Sheets: {exc}")
        st.markdown("""
        **Verifica estos puntos:**
        1. Que el secreto `gcp_service_account` esté cargado en Streamlit Cloud.
        2. Que el correo de la cuenta de servicio tenga permiso de lectura en el Google Sheets.
        3. Que el archivo de Google Sheets sea el correcto.
        """)
        st.stop()

    if raw.empty:
        st.warning("La hoja no contiene registros para analizar.")
        st.stop()

    valid_dates = raw["Fecha"].dropna()
    if valid_dates.empty:
        st.error("No se encontraron fechas válidas en la columna Fecha. Revisa el formato de la hoja.")
        st.stop()

    # El filtro de periodo debe ofrecer exclusivamente fechas existentes en la columna Fecha de Sheets.
    # Se usan fechas únicas y ordenadas; no se generan fechas intermedias que no estén registradas.
    fechas_disponibles = sorted(valid_dates.dt.date.unique())
    fecha_hasta_por_defecto = fechas_disponibles[-1]
    fecha_desde_por_defecto = fechas_disponibles[0]

    with st.sidebar:
        st.header("Filtros")
        st.caption(
            f"Fechas disponibles en Sheets: {len(fechas_disponibles)} · "
            f"Desde {fechas_disponibles[0].strftime('%d/%m/%Y')} "
            f"hasta {fechas_disponibles[-1].strftime('%d/%m/%Y')}."
        )
        col_fecha_desde, col_fecha_hasta = st.columns(2)
        with col_fecha_desde:
            start_date = st.selectbox(
                "Fecha desde",
                options=fechas_disponibles,
                index=0,
                format_func=lambda d: d.strftime("%d/%m/%Y"),
                key="dist_fecha_desde_filtro",
            )
        with col_fecha_hasta:
            end_date = st.selectbox(
                "Fecha hasta",
                options=fechas_disponibles,
                index=len(fechas_disponibles) - 1,
                format_func=lambda d: d.strftime("%d/%m/%Y"),
                key="dist_fecha_hasta_filtro",
            )

        if start_date > end_date:
            st.warning("La fecha inicial es posterior a la fecha final. Se intercambiarán para filtrar.")
            start_date, end_date = end_date, start_date

        # Filtros dependientes: Contrato -> Unidad de negocio -> Servicio eléctrico.
        # Al cambiar un filtro padre, se reinician automáticamente los filtros hijos.
        def _reset_dist_uunn_y_servicio():
            st.session_state["dist_filtro_uunn"] = "Todas"
            st.session_state["dist_filtro_servicio"] = "Todos"

        def _reset_dist_servicio():
            st.session_state["dist_filtro_servicio"] = "Todos"

        contrato_values = ["Todos"] + sorted(
            x for x in raw["Contrato"].dropna().astype(str).str.strip().unique() if x
        )
        selected_contrato = st.selectbox(
            "Contrato", contrato_values,
            key="dist_filtro_contrato_km",
            on_change=_reset_dist_uunn_y_servicio,
        )

        datos_contrato = raw if selected_contrato == "Todos" else raw[raw["Contrato"] == selected_contrato]
        uunn_values = ["Todas"] + sorted(
            x for x in datos_contrato["Unidad Negocio"].dropna().astype(str).str.strip().unique() if x
        )
        selected_uunn = st.selectbox(
            "Unidad de negocio", uunn_values,
            key="dist_filtro_uunn",
            on_change=_reset_dist_servicio,
        )

        datos_uunn = datos_contrato if selected_uunn == "Todas" else datos_contrato[datos_contrato["Unidad Negocio"] == selected_uunn]
        service_values = ["Todos"] + sorted(
            x for x in datos_uunn["Servicio Electrico"].dropna().astype(str).str.strip().unique() if x
        )
        selected_service = st.selectbox(
            "Servicio eléctrico", service_values,
            key="dist_filtro_servicio",
        )

        st.divider()
        st.caption("Los datos se mantienen en caché durante 30 minutos. Puedes usar «Actualizar datos» para forzar una nueva lectura.")
        if st.button("🔄 Actualizar datos", use_container_width=True, key="dist_refrescar"):
            clear_sheet(SHEET_ID, obtener_pestana_distribucion())
            obtener_pestana_distribucion.clear()
            load_records.clear()
            st.rerun()

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    df = raw[(raw["Fecha"] >= start_ts) & (raw["Fecha"] <= end_ts)].copy()
    if selected_contrato != "Todos":
        df = df[df["Contrato"] == selected_contrato]
    if selected_uunn != "Todas":
        df = df[df["Unidad Negocio"] == selected_uunn]
    if selected_service != "Todos":
        df = df[df["Servicio Electrico"] == selected_service]

    completed = df[df["Recorrido válido"]].copy()
    pending = df[df["Pendiente"]].copy()
    km_total = completed["Tot Recorrido"].sum()
    # Contar días distintos por placa y sumar el resultado como número entero.
    # Evita que pandas intente sumar fechas si una agrupación queda con dtype datetime.
    # Días trabajados del periodo: contar fechas calendario distintas, no sumar
    # los días de cada placa. Por ejemplo, del 06/10 al 07/10 son 2 días.
    days_worked = int(
        completed["Fecha"].dropna().dt.normalize().nunique()
    ) if not completed.empty else 0

    plates_active = int(completed.loc[completed["Placa"].ne(""), "Placa"].nunique())

    # Promedio por placa/día: kilómetros acumulados divididos entre los pares
    # únicos de placa y fecha. Así no se presenta el kilometraje de toda la flota
    # como si fuera el promedio diario de un solo vehículo.
    registros_placa_dia = completed.loc[
        completed["Placa"].ne("") & completed["Fecha"].notna(),
        ["Placa", "Fecha"],
    ].copy()
    placa_dias = (
        registros_placa_dia.assign(Fecha=registros_placa_dia["Fecha"].dt.normalize())
        .drop_duplicates(["Placa", "Fecha"])
        .shape[0]
    )
    daily_average = float(km_total / placa_dias) if placa_dias > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    km_total_entero = int(round(km_total))
    m1.metric("Kilómetros recorridos", f"{km_total_entero:,} km")
    m2.metric("Días trabajados", f"{int(days_worked):,}")
    m3.metric("Placas con actividad", f"{int(plates_active):,}")
    m4.metric("Promedio por placa/día", f"{daily_average:,.1f} km")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Resumen", "🏆 Ranking de placas", "📅 Días trabajados",
        "⚠️ Pendientes", "📋 Detalle y exportación"
    ])

    with tab1:
        st.subheader("Evolución del kilometraje")
        if not completed.empty:
            daily = completed.groupby(completed["Fecha"].dt.date, as_index=False)["Tot Recorrido"].sum()
            daily.columns = ["Fecha", "Kilómetros"]
            by_uunn = completed.groupby("Unidad Negocio", as_index=False)["Tot Recorrido"].sum().sort_values("Tot Recorrido", ascending=False)
            by_uunn.columns = ["Unidad de negocio", "Kilómetros"]
            fig_uunn = px.bar(
                by_uunn, x="Unidad de negocio", y="Kilómetros",
                title="Kilómetros por unidad de negocio", text="Kilómetros"
            )
            fig_uunn.update_traces(
                texttemplate="%{text:,.0f} km", textposition="outside",
                cliponaxis=False,
            )
            estabilizar_grafico(fig_uunn, altura=460, margen_inferior=100)
            fig_uunn.update_xaxes(tickangle=-25)
            st.plotly_chart(
                fig_uunn, use_container_width=True, key="dist_grafico_km_unidad",
                config={"responsive": True, "scrollZoom": False, "displayModeBar": False},
            )

            by_service = completed.groupby("Servicio Electrico", as_index=False)["Tot Recorrido"].sum().sort_values("Tot Recorrido", ascending=False)
            by_service.columns = ["Servicio eléctrico", "Kilómetros"]
            fig_service = px.bar(
                by_service, x="Servicio eléctrico", y="Kilómetros",
                title="Kilómetros por servicio eléctrico", text="Kilómetros"
            )
            fig_service.update_traces(
                texttemplate="%{text:,.0f} km", textposition="outside",
                cliponaxis=False,
            )
            estabilizar_grafico(fig_service, altura=460, margen_inferior=115)
            fig_service.update_xaxes(tickangle=-25)
            st.plotly_chart(
                fig_service, use_container_width=True, key="dist_grafico_km_servicio",
                config={"responsive": True, "scrollZoom": False, "displayModeBar": False},
            )
        else:
            st.info("No hay recorridos completados en el periodo seleccionado.")

    with tab2:
        st.subheader("Placas con más kilómetros")
        if not completed.empty:
            ranking = completed.groupby("Placa", as_index=False).agg(
                Kilometros=("Tot Recorrido", "sum"),
                Registros=("Tot Recorrido", "count"),
                Dias_trabajados=("Fecha", lambda s: s.dt.date.nunique()),
            ).sort_values("Kilometros", ascending=False)
            ranking = ranking.rename(columns={"Dias_trabajados": "Días trabajados"})
            # Gráfico horizontal: las placas quedan en el eje vertical y los KM en horizontal.
            # Se fija una altura estable y se desactiva el redimensionamiento por selección,
            # para que el gráfico no se deforme al hacer clic en una barra.
            top_n = st.selectbox(
                "Cantidad de placas en el gráfico",
                options=[10, 15, 20, 30, 50],
                index=2,
                key="dist_top_placas_km",
            )
            grafico_ranking = ranking.head(top_n).sort_values("Kilometros", ascending=True)
            max_km_grafico = float(grafico_ranking["Kilometros"].max()) if not grafico_ranking.empty else 0.0
            # Una única traza y eje explícito impiden recortes o zoom heredado.
            fig_ranking = go.Figure(go.Bar(
                x=grafico_ranking["Kilometros"].tolist(),
                y=grafico_ranking["Placa"].tolist(),
                orientation="h",
                text=[f"{v:,.0f} km" for v in grafico_ranking["Kilometros"]],
                textposition="outside",
                cliponaxis=False,
                customdata=grafico_ranking[["Registros", "Días trabajados"]].to_numpy(),
                hovertemplate="Placa: %{y}<br>Kilómetros: %{x:,.0f}<br>Registros: %{customdata[0]}<br>Días trabajados: %{customdata[1]}<extra></extra>",
                marker_color="#79bef0",
                width=0.75,
            ))
            fig_ranking.update_layout(
                title=f"Top {top_n} placas con más kilómetros recorridos",
                height=max(420, 26 * len(grafico_ranking) + 130),
                margin=dict(l=95, r=110, t=65, b=55),
                autosize=True,
                showlegend=False,
                dragmode=False,
                uirevision="ranking-km-v3",
                bargap=0.20,
                uniformtext_mode="show",
            )
            fig_ranking.update_xaxes(
                title="Kilómetros recorridos", range=[0, max_km_grafico * 1.22 if max_km_grafico > 0 else 1],
                autorange=False, fixedrange=True, automargin=True, rangemode="tozero",
            )
            fig_ranking.update_yaxes(title=None, fixedrange=True, automargin=True, type="category")
            st.plotly_chart(
                fig_ranking, use_container_width=True, key="dist_grafico_ranking_placas_km_v3",
                config={"displayModeBar": False, "scrollZoom": False, "responsive": True},
            )
            st.dataframe(ranking, use_container_width=True, hide_index=True)
        else:
            st.info("No hay recorridos completados para elaborar el ranking.")

    with tab3:
        st.subheader("Placas con más días trabajados")
        if not completed.empty:
            days = completed.dropna(subset=["Fecha"]).groupby("Placa").agg(
                **{"Días trabajados": ("Fecha", lambda s: s.dt.date.nunique()),
                   "Kilómetros": ("Tot Recorrido", "sum"),
                   "Registros completados": ("Recorrido válido", "sum")}
            ).reset_index().sort_values(["Días trabajados", "Kilómetros"], ascending=False)
            days_chart_data = days.head(20).sort_values("Días trabajados", ascending=True)
            max_dias = int(days_chart_data["Días trabajados"].max()) if not days_chart_data.empty else 1
            fig_days = go.Figure(go.Bar(
                x=days_chart_data["Días trabajados"].tolist(),
                y=days_chart_data["Placa"].tolist(),
                orientation="h",
                text=[f"{int(v)} días" for v in days_chart_data["Días trabajados"]],
                textposition="outside",
                cliponaxis=False,
                customdata=days_chart_data[["Kilómetros", "Registros completados"]].to_numpy(),
                hovertemplate="Placa: %{y}<br>Días trabajados: %{x}<br>Kilómetros: %{customdata[0]:,.0f}<br>Registros: %{customdata[1]}<extra></extra>",
                marker_color="#79bef0",
                width=0.75,
            ))
            fig_days.update_layout(
                title="Top 20 placas por días trabajados",
                height=max(420, 26 * len(days_chart_data) + 130),
                margin=dict(l=95, r=110, t=65, b=55),
                autosize=True,
                dragmode=False,
                showlegend=False,
                uirevision="dias-placa-v3",
                bargap=0.20,
                uniformtext_mode="show",
            )
            fig_days.update_xaxes(
                title="Días trabajados", range=[0, max_dias * 1.23 if max_dias > 0 else 1],
                autorange=False, fixedrange=True, automargin=True, dtick=2,
            )
            fig_days.update_yaxes(title=None, fixedrange=True, automargin=True, type="category")
            st.plotly_chart(
                fig_days, use_container_width=True, key="dist_grafico_placas_dias_v3",
                config={"displayModeBar": False, "scrollZoom": False, "responsive": True},
            )
            st.dataframe(days, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos suficientes para contar días trabajados.")

    with tab4:
        st.subheader("Registros con kilometraje pendiente")
        st.caption("Se consideran pendientes las filas con KM inicial registrado y KM final vacío.")
        if pending.empty:
            st.success("No hay registros pendientes en los filtros seleccionados.")
        else:
            cols = ["Fecha", "Placa", "Km Inicial", "Nom Personal", "Unidad Negocio", "Servicio Electrico", "CECO", "Observacion"]
            st.dataframe(pending[cols].sort_values("Fecha", ascending=False), use_container_width=True, hide_index=True)

    with tab5:
        st.subheader("Detalle de registros")
        show = df.copy()
        show["Fecha"] = show["Fecha"].dt.strftime("%Y-%m-%d")
        st.dataframe(show, use_container_width=True, hide_index=True)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            show.to_excel(writer, sheet_name="Detalle", index=False)
            if not completed.empty:
                completed_export = completed.copy()
                completed_export["Fecha"] = completed_export["Fecha"].dt.strftime("%Y-%m-%d")
                completed_export.to_excel(writer, sheet_name="Recorridos", index=False)
            if not pending.empty:
                pending_export = pending.copy()
                pending_export["Fecha"] = pending_export["Fecha"].dt.strftime("%Y-%m-%d")
                pending_export.to_excel(writer, sheet_name="Pendientes", index=False)
        st.download_button(
            "⬇️ Descargar reporte Excel",
            data=output.getvalue(),
            file_name=f"KM_DISTRIBUCION_{start_date}_{end_date}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.caption("KM_DISTRIBUCION · Fuente: Google Sheets · Aplicación de consulta; no escribe ni modifica datos.")