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
    ["📈 Reportes de Producción", "🚙 Reportes de km_perdidas"],
    key="dashboard_seleccionado",
)
st.sidebar.divider()

# El código visual se ejecuta al seleccionar cada dashboard, pero los datos
# ya descargados permanecen en st.cache_data y no se vuelven a solicitar.
if seleccion == "📈 Reportes de Producción":
    import produccion
    produccion.render()
else:
    import kilometraje
    kilometraje.render()
