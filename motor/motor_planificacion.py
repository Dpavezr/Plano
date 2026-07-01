"""
Motor de Planificación S&OP - Cadena de Frío
Replica la lógica del archivo PPTO 25-26 V2.xlsx

Estructura:
  - PlanMaestro: clase principal que orquesta todos los cálculos
  - Módulos: mmpp, distribucion_plantas, congelacion, produccion_pt, stock, costos
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# Constantes del dominio
# ---------------------------------------------------------------------------

ESPECIES = [
    "Arándano Conv", "Arándano Org",
    "Espárrago Conv", "Espárrago Org",
    "Frambuesa Conv", "Frambuesa Meeker", "Frambuesa Org",
    "Frutilla Conv", "Frutilla Org",
    "Cerezas Conv", "Cerezas Org",
    "Granada", "Limon", "Uva con Palo",
    "Kiwi Conv", "Kiwi Org",
    "Mora silvestre",
    "Boysenberry Conv", "Boysenberry Org",
    "Mora Cultivada Conv", "Mora Cultivada Org",
]

ESPECIES_AGRUPADAS = {
    "Arándano":      ["Arándano Conv", "Arándano Org"],
    "Espárrago":     ["Espárrago Conv", "Espárrago Org"],
    "Frambuesa":     ["Frambuesa Conv", "Frambuesa Meeker", "Frambuesa Org"],
    "Frutilla":      ["Frutilla Conv", "Frutilla Org"],
    "Cerezas":       ["Cerezas Conv", "Cerezas Org"],
    "Granada":       ["Granada"],
    "Limon":         ["Limon"],
    "Uva":           ["Uva con Palo"],
    "Kiwi":          ["Kiwi Conv", "Kiwi Org"],
    "Mora silvestre":["Mora silvestre"],
    "Boysenberry":   ["Boysenberry Conv", "Boysenberry Org"],
    "Mora Cultivada":["Mora Cultivada Conv", "Mora Cultivada Org"],
}

PLANTAS = ["Chillan", "Parral", "Loncoche", "Ecoberry", "NN", "Copramar"]

TUNELES_CHILLAN = {
    "UNIDEX II": ["Arándano", "Frambuesa", "Frutilla", "Granada", "Cerezas",
                  "Uva", "Kiwi", "Mora silvestre", "Boysenberry", "Mora Cultivada"],
    "UNIDEX":    ["Arándano", "Granada", "Kiwi", "Mora silvestre", "Cerezas", "Frutilla"],
    "AERO":      ["Arándano", "Espárrago", "Frambuesa", "Frutilla", "Uva",
                  "Kiwi", "Mora silvestre", "Boysenberry", "Mora Cultivada"],
    "ESTATICOS": ["Espárrago", "Arándano", "Frambuesa", "Frutilla", "Uva",
                  "Kiwi", "Boysenberry", "Mora Cultivada"],
}

# Tarifas de traslado entre plantas en pesos CLP
TARIFAS_TRASLADO = {
    ("Loncoche", "Chillan"):     {"rampla": 720_000, "camion": 600_000, "camion_sf": 375_000},
    ("Parral",   "Chillan"):     {"rampla": 185_000, "camion": 160_000, "camion_sf": 107_000},
    ("Parral",   "Valparaiso"):  {"rampla": 800_000, "camion": 567_000, "camion_sf": 0},
    ("Parral",   "Talcahuano"):  {"rampla": 400_000, "camion": 321_000, "camion_sf": 0},
    ("Chillan",  "Valparaiso"):  {"rampla": 802_000, "camion": 567_000, "camion_sf": 480_000},
    ("Chillan",  "Talcahuano"):  {"rampla": 360_000, "camion": 256_000, "camion_sf": 192_000},
    ("Chillan",  "Chillan"):     {"rampla": 120_000, "camion":  95_000, "camion_sf":  65_000},
}

# Costos in/out frigoríficos externos ($/pallet)
COSTO_INOUT_TRASLADO   = 4_000
COSTO_INOUT_EXPORTACION = 6_500
COSTO_ETIQUETA_EXPO     = 100
PESO_PROM_PALLET        = 22_000   # kg
TIPO_CAMBIO_USD         = 860      # CLP por USD


# ---------------------------------------------------------------------------
# Estructuras de datos de entrada
# ---------------------------------------------------------------------------

@dataclass
class SemanaConfig:
    """Configuración de una semana del plan."""
    semana: str        # "sem 36"
    numero: int        # 36
    fecha_inicio: Optional[str]
    dias_habiles: int  # 4 o 6


@dataclass
class ParametrosCosto:
    """Parámetros de costos operacionales ingresados por el equipo de Operaciones."""
    # Dotación (personas por planta y semana)
    dotacion: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # {planta: {semana: n_personas}}

    # Tarifas embalaje ($/ton por tipo de producto)
    tarifas_embalaje: Dict[str, float] = field(default_factory=dict)
    # {tipo_producto: tarifa_clp_por_ton}

    # Capacidad frigoríficos externos (ton por semana)
    cap_frigorifico_ext: Dict[str, Dict[str, float]] = field(default_factory=dict)
    # {nombre_frig: {semana: toneladas}}

    # Tarifa frigorífico externo (USD/ton/mes)
    tarifa_frig_ext: Dict[str, float] = field(default_factory=dict)
    # {nombre_frig: tarifa_usd}

    # Fletes (n° camiones/ramplas por planta y semana)
    fletes: Dict[str, Dict[str, Dict[str, int]]] = field(default_factory=dict)
    # {planta: {semana: {"ramplas": n, "camiones": n}}}

    # Tipo de cambio USD/CLP
    tipo_cambio: float = TIPO_CAMBIO_USD


# ---------------------------------------------------------------------------
# Motor de planificación
# ---------------------------------------------------------------------------

class PlanMaestro:
    """
    Motor principal del plan maestro de temporada.

    Flujo de cálculo:
      1. MMPP por especie (input agrícola)
      2. Agrupación por especie familia
      3. Distribución a plantas
      4. Capacidad de congelación (ton/día)
      5. Producción PT por planta y especie
      6. Compra de producto congelado
      7. Total PT semana
      8. Proyección de stock congelado
      9. Despachos proyectados
     10. Cálculo de costos (dotación, embalaje, frigorífico ext, traslados)
    """

    def __init__(self, semanas: List[SemanaConfig], params_costo: ParametrosCosto):
        self.semanas = semanas
        self.sem_labels = [s.semana for s in semanas]
        self.params = params_costo

        # DataFrames principales (índice = especie o agrupación, columnas = semanas)
        self.mmpp_detalle: pd.DataFrame = pd.DataFrame(0.0, index=ESPECIES, columns=self.sem_labels)
        self.mmpp_agrupado: pd.DataFrame = pd.DataFrame(0.0, index=list(ESPECIES_AGRUPADAS.keys()), columns=self.sem_labels)
        self.mmpp_total: pd.Series = pd.Series(0.0, index=self.sem_labels)

        # Distribución a plantas: {planta: DataFrame(especie × semana)}
        self.distribucion: Dict[str, pd.DataFrame] = {
            p: pd.DataFrame(0.0, index=ESPECIES, columns=self.sem_labels)
            for p in PLANTAS
        }
        self.dist_total_semana: pd.Series = pd.Series(0.0, index=self.sem_labels)

        # Congelación ton/día por túnel/planta
        self.congelacion: pd.DataFrame = pd.DataFrame(0.0,
            index=list(TUNELES_CHILLAN.keys()) + ["Otras plantas"],
            columns=self.sem_labels
        )
        self.congelacion_total: pd.Series = pd.Series(0.0, index=self.sem_labels)

        # Producción PT
        self.produccion_pt: pd.DataFrame = pd.DataFrame(0.0,
            index=list(ESPECIES_AGRUPADAS.keys()),
            columns=self.sem_labels
        )
        self.compra_congelado: pd.DataFrame = pd.DataFrame(0.0,
            index=["Espárrago", "Mora Cultivada", "Frambuesa", "Frutilla",
                   "Boysenberry", "Arándano", "Manzana", "Mango", "Otros"],
            columns=self.sem_labels
        )
        self.pt_total: pd.Series = pd.Series(0.0, index=self.sem_labels)

        # Stock proyectado
        self.stock_inicial: float = 0.0
        self.stock_proyectado: pd.Series = pd.Series(0.0, index=self.sem_labels)
        self.despachos: pd.Series = pd.Series(0.0, index=self.sem_labels)

        # Costos calculados
        self.costo_dotacion: pd.Series = pd.Series(0.0, index=self.sem_labels)
        self.costo_embalaje: pd.Series = pd.Series(0.0, index=self.sem_labels)
        self.costo_frig_ext: pd.Series = pd.Series(0.0, index=self.sem_labels)
        self.costo_traslados: pd.Series = pd.Series(0.0, index=self.sem_labels)
        self.costo_total: pd.Series = pd.Series(0.0, index=self.sem_labels)

    # ------------------------------------------------------------------
    # 1. Input de MMPP (agrícola)
    # ------------------------------------------------------------------

    def set_mmpp(self, especie: str, semana: str, toneladas: float):
        """Registra proyección de llegada de fruta para una especie y semana."""
        if especie not in ESPECIES:
            raise ValueError(f"Especie '{especie}' no reconocida. Opciones: {ESPECIES}")
        if semana not in self.sem_labels:
            raise ValueError(f"Semana '{semana}' no existe en el plan.")
        self.mmpp_detalle.loc[especie, semana] = toneladas

    def set_mmpp_bulk(self, data: Dict[str, Dict[str, float]]):
        """Carga masiva: {especie: {semana: toneladas}}"""
        for especie, semanas in data.items():
            for semana, ton in semanas.items():
                self.set_mmpp(especie, semana, ton)

    # ------------------------------------------------------------------
    # 2. Distribución a plantas (input operaciones o reglas automáticas)
    # ------------------------------------------------------------------

    def set_distribucion(self, planta: str, especie: str, semana: str, toneladas: float):
        """Asigna MMPP de una especie a una planta para una semana."""
        if planta not in PLANTAS:
            raise ValueError(f"Planta '{planta}' no reconocida. Opciones: {PLANTAS}")
        self.distribucion[planta].loc[especie, semana] = toneladas

    def distribucion_proporcional(self, proporciones: Dict[str, float]):
        """
        Distribuye automáticamente el total de MMPP entre plantas
        según proporciones fijas. proporciones = {"Chillan": 0.6, "Parral": 0.3, ...}
        """
        assert abs(sum(proporciones.values()) - 1.0) < 0.01, "Las proporciones deben sumar 1.0"
        for especie in ESPECIES:
            for semana in self.sem_labels:
                total = self.mmpp_detalle.loc[especie, semana]
                for planta, prop in proporciones.items():
                    self.distribucion[planta].loc[especie, semana] = total * prop

    # ------------------------------------------------------------------
    # 3. Parámetros de congelación (input operaciones)
    # ------------------------------------------------------------------

    def set_congelacion(self, tunel: str, semana: str, ton_dia: float):
        """Registra capacidad de congelación de un túnel para una semana."""
        self.congelacion.loc[tunel, semana] = ton_dia

    # ------------------------------------------------------------------
    # Cálculo principal - ejecutar en orden
    # ------------------------------------------------------------------

    def calcular(self):
        """Ejecuta todos los módulos de cálculo en secuencia."""
        self._calc_mmpp_agrupado()
        self._calc_distribucion_total()
        self._calc_congelacion_total()
        self._calc_produccion_pt()
        self._calc_pt_total()
        self._calc_stock()
        self._calc_costos()

    def _calc_mmpp_agrupado(self):
        """Agrupa MMPP por familia de especie y calcula total semana."""
        for familia, especies in ESPECIES_AGRUPADAS.items():
            self.mmpp_agrupado.loc[familia] = self.mmpp_detalle.loc[
                [e for e in especies if e in self.mmpp_detalle.index]
            ].sum()
        self.mmpp_total = self.mmpp_agrupado.sum()

    def _calc_distribucion_total(self):
        """Valida que la distribución a plantas no supere el total de MMPP."""
        total_dist = pd.DataFrame(0.0, index=ESPECIES, columns=self.sem_labels)
        for planta in PLANTAS:
            total_dist += self.distribucion[planta]
        self.dist_total_semana = total_dist.sum()

        # Alerta si la distribución supera la llegada de MMPP
        exceso = self.dist_total_semana - self.mmpp_total
        if (exceso > 0.01).any():
            semanas_con_exceso = exceso[exceso > 0.01].index.tolist()
            print(f"⚠️  Advertencia: distribución supera MMPP en semanas: {semanas_con_exceso}")

    def _calc_congelacion_total(self):
        """Suma capacidad de congelación diaria por túnel."""
        self.congelacion_total = self.congelacion.sum()

    def _calc_produccion_pt(self):
        """
        Calcula producción de PT por especie agrupada.
        Lógica: PT = distribución a plantas × rendimiento implícito.
        Por defecto se usa la distribución total (sin merma) como proxy.
        El rendimiento real por especie debe calibrarse con datos históricos de FactoryOS.
        """
        for familia, especies in ESPECIES_AGRUPADAS.items():
            total_fam = pd.Series(0.0, index=self.sem_labels)
            for planta in PLANTAS:
                for esp in especies:
                    if esp in self.distribucion[planta].index:
                        total_fam += self.distribucion[planta].loc[esp]
            self.produccion_pt.loc[familia] = total_fam

    def _calc_pt_total(self):
        """Total de PT = producción propia + compra de congelado."""
        self.pt_total = self.produccion_pt.sum() + self.compra_congelado.sum()

    def _calc_stock(self):
        """
        Proyección de stock congelado semana a semana.
        stock(t) = stock(t-1) + PT(t) - despachos(t)
        """
        stock_anterior = self.stock_inicial
        for sem in self.sem_labels:
            entrada = self.pt_total[sem]
            salida  = self.despachos[sem]
            self.stock_proyectado[sem] = stock_anterior + entrada - salida
            stock_anterior = self.stock_proyectado[sem]

    def _calc_costos(self):
        """Calcula los cuatro módulos de costo."""
        self._calc_costo_embalaje()
        self._calc_costo_frig_ext()
        self._calc_costo_traslados()
        self.costo_total = (
            self.costo_embalaje
            + self.costo_frig_ext
            + self.costo_traslados
        )

    def _calc_costo_embalaje(self):
        """Costo embalaje = PT total × tarifa promedio ponderada."""
        tarifa_prom = self.params.tarifas_embalaje.get("__promedio__", 0.0)
        if tarifa_prom > 0:
            self.costo_embalaje = self.pt_total * tarifa_prom
        else:
            # Calcular por especie si hay tarifas individuales
            for sem in self.sem_labels:
                costo = 0.0
                for familia in self.produccion_pt.index:
                    tarifa = self.params.tarifas_embalaje.get(familia, 0.0)
                    costo += self.produccion_pt.loc[familia, sem] * tarifa
                self.costo_embalaje[sem] = costo

    def _calc_costo_frig_ext(self):
        """
        Costo almacenamiento frigorífico externo.
        Costo mensual (USD) = toneladas × tarifa USD/ton/mes
        Convertido a CLP con tipo de cambio.
        """
        for sem in self.sem_labels:
            costo_usd = 0.0
            for frig, semanas_cap in self.params.cap_frigorifico_ext.items():
                ton = semanas_cap.get(sem, 0.0)
                tarifa = self.params.tarifa_frig_ext.get(frig, 0.0)
                costo_usd += ton * tarifa
            self.costo_frig_ext[sem] = costo_usd * self.params.tipo_cambio

    def _calc_costo_traslados(self):
        """
        Costo fletes = (n° ramplas × tarifa_rampla) + (n° camiones × tarifa_camion)
        por planta de origen hacia Chillan (destino principal).
        """
        for sem in self.sem_labels:
            costo = 0.0
            for planta in PLANTAS:
                fletes_planta = self.params.fletes.get(planta, {}).get(sem, {})
                n_ramplas  = fletes_planta.get("ramplas", 0)
                n_camiones = fletes_planta.get("camiones", 0)
                ruta = (planta, "Chillan")
                if ruta in TARIFAS_TRASLADO:
                    tarifas = TARIFAS_TRASLADO[ruta]
                    costo += n_ramplas  * tarifas["rampla"]
                    costo += n_camiones * tarifas["camion"]
            self.costo_traslados[sem] = costo

    # ------------------------------------------------------------------
    # Outputs / reportes
    # ------------------------------------------------------------------

    def resumen_mmpp(self) -> pd.DataFrame:
        """DataFrame con llegada de MMPP agrupada por especie familiar y semana."""
        df = self.mmpp_agrupado.copy()
        df.loc["TOTAL"] = self.mmpp_total
        return df.round(2)

    def resumen_distribucion(self) -> pd.DataFrame:
        """DataFrame con distribución total a cada planta por semana."""
        rows = {}
        for planta in PLANTAS:
            rows[planta] = self.distribucion[planta].sum()
        df = pd.DataFrame(rows).T
        df.loc["TOTAL"] = self.dist_total_semana
        return df.round(2)

    def resumen_produccion(self) -> pd.DataFrame:
        """DataFrame con producción PT por especie y semana."""
        df = self.produccion_pt.copy()
        df.loc["TOTAL"] = self.pt_total
        return df.round(2)

    def resumen_stock(self) -> pd.DataFrame:
        """DataFrame con stock, despachos y PT por semana."""
        return pd.DataFrame({
            "PT (ton)":       self.pt_total,
            "Despachos (ton)": self.despachos,
            "Stock (ton)":    self.stock_proyectado,
        }).round(2)

    def resumen_costos(self) -> pd.DataFrame:
        """DataFrame con todos los costos operacionales por semana (CLP)."""
        return pd.DataFrame({
            "Embalaje ($)":       self.costo_embalaje,
            "Frigorífico ext ($)": self.costo_frig_ext,
            "Traslados ($)":      self.costo_traslados,
            "TOTAL ($)":          self.costo_total,
        }).round(0)

    def resumen_costos_usd(self) -> pd.DataFrame:
        """Mismo resumen de costos en USD."""
        tc = self.params.tipo_cambio or TIPO_CAMBIO_USD
        return (self.resumen_costos() / tc).round(0)

    def presupuesto_anual(self) -> Dict[str, float]:
        """Totales anuales de los indicadores clave."""
        return {
            "MMPP total temporada (ton)":      float(self.mmpp_total.sum()),
            "PT total temporada (ton)":        float(self.pt_total.sum()),
            "Despachos totales (ton)":         float(self.despachos.sum()),
            "Stock final proyectado (ton)":    float(self.stock_proyectado.iloc[-1]),
            "Costo embalaje total (MM$)":      round(float(self.costo_embalaje.sum()) / 1e6, 2),
            "Costo frigorífico ext total (MM$)": round(float(self.costo_frig_ext.sum()) / 1e6, 2),
            "Costo traslados total (MM$)":     round(float(self.costo_traslados.sum()) / 1e6, 2),
            "Costo operacional total (MM$)":   round(float(self.costo_total.sum()) / 1e6, 2),
            "Costo operacional total (USD M)": round(float(self.costo_total.sum()) / self.params.tipo_cambio / 1e6, 3),
        }

    def exportar_excel(self, path: str):
        """Exporta el plan maestro completo a un archivo Excel."""
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            self.resumen_mmpp().to_excel(writer, sheet_name="MMPP por Especie")
            self.resumen_distribucion().to_excel(writer, sheet_name="Distribución Plantas")
            pd.DataFrame({
                "Túnel": self.congelacion.index,
                **{sem: self.congelacion[sem].values for sem in self.sem_labels}
            }).set_index("Túnel").to_excel(writer, sheet_name="Congelación ton-día")
            self.resumen_produccion().to_excel(writer, sheet_name="Producción PT")
            self.resumen_stock().to_excel(writer, sheet_name="Stock y Despachos")
            self.resumen_costos().to_excel(writer, sheet_name="Costos CLP")
            self.resumen_costos_usd().to_excel(writer, sheet_name="Costos USD")
            pd.DataFrame([self.presupuesto_anual()], index=["Temporada"]).T.to_excel(
                writer, sheet_name="Resumen Anual"
            )
        print(f"✅ Plan exportado a: {path}")
