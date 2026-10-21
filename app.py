import streamlit as st

st.set_page_config(page_title="Sistema Integrado de Reportes", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.sidebar.title("📊 Sistema de reportes")
seleccion = st.sidebar.radio(
    "Seleccionar dashboard",
    ["📈 Reportes de Producción", "🚙 Reportes de Kilometraje"],
    key="dashboard_seleccionado",
)
st.sidebar.divider()

if seleccion == "📈 Reportes de Producción":
    import produccion
else:
    import kilometraje
