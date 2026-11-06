import streamlit as st

st.set_page_config(
    page_title="Sistema Integrado de Reportes",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.title("📊 Sistema de reportes")
seleccion = st.sidebar.radio(
    "Seleccionar dashboard",
    [
        "🚙 Reportes de km_perdidas",
        "🚚 Reportes de km_distribucion",
        "📦 OMs Distribución",
        "📈 Reportes de Producción",
        "🧩 Incidencia y Recurso",
    ],
    key="dashboard_seleccionado",
)
st.sidebar.divider()
if seleccion == "🚙 Reportes de km_perdidas":
    import kilometraje
    kilometraje.render()
elif seleccion == "🚚 Reportes de km_distribucion":
    import distribucion
    distribucion.render()
elif seleccion == "📦 OMs Distribución":
    import oms_distribucion
    oms_distribucion.render()
elif seleccion == "📈 Reportes de Producción":
    import produccion
    produccion.render()
else:
    import incidencia_recurso
    incidencia_recurso.render()
