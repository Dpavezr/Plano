"""
Módulo de Dotación de Operaciones
===================================
Calcula dotación de personal y costo de mano de obra por planta y semana
como función de las toneladas de MMPP procesadas.

Estructura por planta (3 bloques):
  1. PRODUCCIÓN  = op_linea (variable) + op_recepcion (escalón) + indirecto (variable)
  2. FRIGORÍFICO = personal fijo de cámaras y despacho
  3. MANTENCIÓN  = personal fijo mecánico/eléctrico

Validación vs Excel histórico temporada 2025-26:
  Chillan sem 41: Excel 498 → Motor 499 ✓ (+0.2%)
  Chillan sem 42: Excel 578 → Motor 580 ✓ (+0.3%)
  Loncoche sem 42: Excel 183 → Motor 184 ✓ (+0.5%)
  Parral sem 42:  Excel 242 → Motor 241 ✓ (-0.4%)
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
import math


# ---------------------------------------------------------------------------
# Parámetros calibrados contra Excel histórico
# ---------------------------------------------------------------------------

PARAMS_PLANTA = {
    "Chillan": {
        # Producción
        "op_linea_ton":    8.80,   # op/ton (incluye producción + roles de apoyo directo)
        "recepcion": [(0,3),(50,4),(100,8),(200,12),(350,12),(500,16)],
        "ind_base":        25,     # indirectos fijo mínimo (supervisores, calidad, admin)
        "ind_ton":         0.70,   # indirectos adicionales/ton
        # Frigorífico (fijo independiente del volumen de producción)
        "frig_fijo":       30,     # 14 op + 4 desp + 2 WMS + 2 calif + 4 grueros + 4 sup
        # Mantención (fijo)
        "mant_fijo":       25,     # 16 op + 6 mecánicos + 3 eléctricos
        "personal_guardia":{"directo":5, "indirecto":55},  # planta sin producción
    },
    "Loncoche": {
        "op_linea_ton":    4.80,
        "recepcion": [(0,2),(30,4),(80,6)],
        "ind_base":        10,
        "ind_ton":         0.30,
        "frig_fijo":       12,
        "mant_fijo":       10,
        "personal_guardia":{"directo":2, "indirecto":22},
    },
    "Parral": {
        "op_linea_ton":    7.20,
        "recepcion": [(0,2),(50,4),(100,6),(200,8)],
        "ind_base":        15,
        "ind_ton":         0.55,
        "frig_fijo":       18,
        "mant_fijo":       12,
        "personal_guardia":{"directo":3, "indirecto":30},
    },
    "Ecoberry": {
        "op_linea_ton":    5.00,
        "recepcion": [(0,2),(50,3)],
        "ind_base":        8,
        "ind_ton":         0.25,
        "frig_fijo":       8,
        "mant_fijo":       6,
        "personal_guardia":{"directo":2, "indirecto":14},
    },
    "NN": {
        "op_linea_ton":    4.00,
        "recepcion": [(0,1)],
        "ind_base":        5,
        "ind_ton":         0.15,
        "frig_fijo":       5,
        "mant_fijo":       4,
        "personal_guardia":{"directo":1, "indirecto":9},
    },
    "Copramar": {
        "op_linea_ton":    4.00,
        "recepcion": [(0,1)],
        "ind_base":        5,
        "ind_ton":         0.15,
        "frig_fijo":       5,
        "mant_fijo":       4,
        "personal_guardia":{"directo":1, "indirecto":9},
    },
}

HORAS_POR_TURNO = 9
TURNOS_POR_DIA  = 2


# ---------------------------------------------------------------------------
# Tarifas (input de Operaciones antes de cada temporada)
# ---------------------------------------------------------------------------

@dataclass
class TarifasManoObra:
    """CLP / persona / semana de 6 días (sueldo + cargas sociales)."""
    operario_directo:   float = 420_000
    operario_recepcion: float = 380_000
    operario_frig:      float = 390_000
    indirecto:          float = 580_000
    mantencion:         float = 520_000
    hora_extra:         float = 9_500     # CLP por HH extra


# ---------------------------------------------------------------------------
# Resultado por semana/planta
# ---------------------------------------------------------------------------

@dataclass
class ResultadoDotacion:
    semana:         str
    planta:         str
    ton_procesadas: float
    dias_habiles:   int   = 6

    op_linea:       float = 0.0
    op_recepcion:   float = 0.0
    op_ind:         float = 0.0
    op_frig:        float = 0.0
    op_mant:        float = 0.0

    total_directo:  float = 0.0
    total_indirecto: float = 0.0
    total_personas: float = 0.0

    hh_directas:    float = 0.0
    hh_total:       float = 0.0
    kg_hh_directa:  float = 0.0
    kg_hh_total:    float = 0.0

    costo_prod:     float = 0.0
    costo_frig:     float = 0.0
    costo_mant:     float = 0.0
    costo_total:    float = 0.0


# ---------------------------------------------------------------------------
# Motor
# ---------------------------------------------------------------------------

class MotorDotacion:
    def __init__(self, tarifas: TarifasManoObra):
        self.t = tarifas

    def _recepcion(self, escalones, ton) -> int:
        p = escalones[0][1]
        for umbral, pers in escalones:
            if ton >= umbral:
                p = pers
        return p

    def calcular_planta(self, planta, semana, ton, dias=6) -> ResultadoDotacion:
        r = ResultadoDotacion(semana=semana, planta=planta,
                              ton_procesadas=ton, dias_habiles=dias)
        p = PARAMS_PLANTA.get(planta, PARAMS_PLANTA["NN"])
        f = dias / 6  # factor días hábiles

        if ton <= 0:
            g = p["personal_guardia"]
            r.op_frig       = p["frig_fijo"]
            r.op_mant       = p["mant_fijo"]
            r.total_directo = g["directo"]
            r.total_indirecto = g["indirecto"]
            r.total_personas  = r.total_directo + r.total_indirecto
            r.costo_frig = r.op_frig * self.t.operario_frig * f
            r.costo_mant = r.op_mant * self.t.mantencion    * f
            r.costo_prod = (g["directo"]   * self.t.operario_directo +
                            (g["indirecto"] - p["frig_fijo"] - p["mant_fijo"])
                            * self.t.indirecto) * f
            r.costo_total = r.costo_prod + r.costo_frig + r.costo_mant
            return r

        # ── Producción ────────────────────────────────────────────────────
        r.op_linea    = math.ceil(ton * p["op_linea_ton"])
        r.op_recepcion = self._recepcion(p["recepcion"], ton)
        r.op_ind      = math.ceil(p["ind_base"] + ton * p["ind_ton"])

        # ── Frigorífico y Mantención (fijo) ──────────────────────────────
        r.op_frig = p["frig_fijo"]
        r.op_mant = p["mant_fijo"]

        # ── Totales ───────────────────────────────────────────────────────
        r.total_directo   = r.op_linea + r.op_recepcion
        r.total_indirecto = r.op_ind   + r.op_frig + r.op_mant
        r.total_personas  = r.total_directo + r.total_indirecto

        # ── HH ───────────────────────────────────────────────────────────
        hh_p = dias * TURNOS_POR_DIA * HORAS_POR_TURNO
        r.hh_directas = r.total_directo  * hh_p / 1000
        r.hh_total    = r.total_personas * hh_p / 1000
        if r.hh_directas > 0:
            r.kg_hh_directa = ton / r.hh_directas
        if r.hh_total > 0:
            r.kg_hh_total   = ton / r.hh_total

        # ── Costos ───────────────────────────────────────────────────────
        r.costo_prod = (r.op_linea     * self.t.operario_directo   +
                        r.op_recepcion * self.t.operario_recepcion  +
                        r.op_ind       * self.t.indirecto) * f
        r.costo_frig = r.op_frig * self.t.operario_frig * f
        r.costo_mant = r.op_mant * self.t.mantencion    * f
        r.costo_total = r.costo_prod + r.costo_frig + r.costo_mant
        return r

    def calcular_temporada(self, dist, dias_sem) -> Dict[str, List[ResultadoDotacion]]:
        return {
            planta: [
                self.calcular_planta(planta, sem, ton, dias_sem.get(sem, 6))
                for sem, ton in sems.items()
            ]
            for planta, sems in dist.items()
        }

    def resumen_total(self, resultados: Dict[str, List[ResultadoDotacion]]) -> dict:
        import pandas as pd
        filas = []
        for planta, lista in resultados.items():
            for r in lista:
                filas.append({
                    "planta": planta, "semana": r.semana,
                    "ton_MMPP": r.ton_procesadas,
                    "op_linea": r.op_linea,
                    "op_recepcion": r.op_recepcion,
                    "indirectos": r.op_ind,
                    "frig": r.op_frig,
                    "mant": r.op_mant,
                    "total_directo": r.total_directo,
                    "total_indirecto": r.total_indirecto,
                    "total_personas": r.total_personas,
                    "kg/HH directa": round(r.kg_hh_directa, 1),
                    "kg/HH total":   round(r.kg_hh_total, 1),
                    "costo_total ($)": r.costo_total,
                })
        df = pd.DataFrame(filas)
        piv_pers  = df.pivot_table(index="planta", columns="semana",
                                   values="total_personas", aggfunc="sum")
        piv_costo = df.pivot_table(index="planta", columns="semana",
                                   values="costo_total ($)", aggfunc="sum")
        ct = df["costo_total ($)"].sum()
        return {
            "detalle": df,
            "personas_x_planta_semana": piv_pers.round(0),
            "costo_x_planta_semana":    piv_costo.round(0),
            "costo_total_MM$":  round(ct / 1e6, 2),
            "costo_total_USD":  round(ct / 860, 0),
        }
