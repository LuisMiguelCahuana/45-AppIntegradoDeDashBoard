"""Lectura paginada de Google Sheets con caché compartida entre dashboards."""
import time
import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

BLOCK_SIZE = 2000  # Cambiar a 1500 si se desea.
CACHE_TTL = 1800
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

@st.cache_resource(show_spinner=False)
def _client():
    credentials = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return gspread.authorize(credentials)

@st.cache_data(ttl=CACHE_TTL, show_spinner=False, max_entries=100)
def _block(sheet_id, tab, first_row, last_row):
    ws = _client().open_by_key(sheet_id).worksheet(tab)
    for attempt in range(4):
        try:
            return ws.get(f"A{first_row}:ZZ{last_row}", value_render_option="FORMATTED_VALUE")
        except gspread.exceptions.APIError as exc:
            if attempt == 3 or getattr(exc.response, 'status_code', None) not in (429, 500, 502, 503, 504):
                raise
            time.sleep(2 ** attempt)

@st.cache_data(ttl=CACHE_TTL, show_spinner=False, max_entries=10)
def read_sheet(sheet_id, tab, block_size=BLOCK_SIZE):
    """Devuelve todas las filas; cada petición lee hasta block_size filas."""
    ws = _client().open_by_key(sheet_id).worksheet(tab)
    total = ws.row_count
    result = []
    progress = st.progress(0, text="Descargando registros por bloques...") if False else None
    for first in range(1, total + 1, block_size):
        block = _block(sheet_id, tab, first, min(first + block_size - 1, total))
        result.extend(block)
        # Las filas vacías intermedias no detienen la lectura.
    while result and not any(str(v).strip() for v in result[-1]):
        result.pop()
    return result

def clear_sheet(sheet_id, tab):
    # La caché de bloques se comparte entre ambos módulos; invalidar todo
    # garantiza que el botón manual obtenga los datos más recientes.
    _block.clear()
    read_sheet.clear()
