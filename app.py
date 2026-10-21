import importlib
import sys

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
    ["📈 Reportes de Producción", "🚙 Reportes de Kilometraje"],
    key="dashboard_seleccionado",
)
st.sidebar.divider()

# Streamlit vuelve a ejecutar app.py al cambiar el radio button, pero Python
# conserva los módulos importados en caché. Recargar el módulo seleccionado
# hace que se vuelvan a dibujar todos sus widgets y gráficos en cada cambio.
if seleccion == "📈 Reportes de Producción":
    modulo = "produccion"
else:
    modulo = "kilometraje"

if modulo in sys.modules:
    importlib.reload(sys.modules[modulo])
else:
    importlib.import_module(modulo)
