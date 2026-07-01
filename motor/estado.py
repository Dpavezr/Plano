"""Estado compartido de la aplicación."""
import streamlit as st
import pandas as pd
from motor_planificacion import PlanMaestro, SemanaConfig, ParametrosCosto, ESPECIES
from modulo_dotacion import TarifasManoObra

# Temporada cubre sem 36-53 (año 1) + sem 1-35 (año 2) = 53 semanas
SEMANAS_DEFAULT = (
    [SemanaConfig(f"sem {n}", n, None, 4 if n in [38,43,48] else 6)
     for n in range(36, 54)] +
    [SemanaConfig(f"sem {n}", n, None, 4 if n in [4,9,14,19,24,29] else 6)
     for n in range(1, 36)]
)
SEM_LABELS = [s.semana for s in SEMANAS_DEFAULT]
PLANTAS_ACTIVAS = ["Chillan", "Parral", "Loncoche", "Ecoberry", "NN", "Copramar"]


def init_estado():
    if "plan" not in st.session_state:
        params = ParametrosCosto(tipo_cambio=860.0)
        st.session_state.plan = PlanMaestro(semanas=SEMANAS_DEFAULT, params_costo=params)
    if "tarifas" not in st.session_state:
        st.session_state.tarifas = TarifasManoObra()
    if "plan_calculado" not in st.session_state:
        st.session_state.plan_calculado = False
    if "rol" not in st.session_state:
        st.session_state.rol = "Agrícola"


def get_sem_labels():
    return SEM_LABELS


def formato_miles(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    return f"{v:,.0f}".replace(",", ".")
