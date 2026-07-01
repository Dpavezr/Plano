"""
PlanOp — Sistema de Planificación S&OP
Cadena de frío · Temporada 2025-26

Ejecutar:
    cd planop
    streamlit run app.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "motor"))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from estado import init_estado, get_sem_labels, PLANTAS_ACTIVAS
from motor.motor_planificacion import ESPECIES, ESPECIES_AGRUPADAS
from motor.modulo_dotacion import MotorDotacion

# ── Configuración de página ───────────────────────────────────────────────
st.set_page_config(
    page_title="PlanOp · S&OP",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS global ────────────────────────────────────────────────────────────
st.markdown("""
<style>
    [data-testid="stSidebar"] { min-width: 220px; max-width: 240px; }
    .metric-card {
        background: #f8f9fa; border-radius: 10px;
        padding: 14px 18px; margin-bottom: 0;
    }
    .metric-label { font-size: 12px; color: #6c757d; margin-bottom: 2px; }
    .metric-value { font-size: 22px; font-weight: 600; color: #212529; }
    .metric-delta { font-size: 11px; margin-top: 2px; }
    .delta-up   { color: #1D9E75; }
    .delta-down { color: #dc3545; }
    .status-pill {
        display:inline-block; padding:2px 10px; border-radius:20px;
        font-size:11px; font-weight:500;
    }
    .pill-green  { background:#d1f5e8; color:#0F6E56; }
    .pill-amber  { background:#fff3cd; color:#856404; }
    .pill-gray   { background:#e9ecef; color:#495057; }
    .section-header {
        font-size:13px; font-weight:600; color:#495057;
        text-transform:uppercase; letter-spacing:0.05em;
        margin-bottom:8px; margin-top:4px;
    }
    div[data-testid="stDataFrame"] { border-radius: 8px; }
    .stButton button { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

init_estado()

# ── Sidebar ───────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 🌿 PlanOp")
    st.caption("Temporada 2025–26")
    st.divider()

    rol = st.selectbox(
        "Rol activo",
        ["Agrícola", "Operaciones", "Gerencia"],
        index=["Agrícola", "Operaciones", "Gerencia"].index(st.session_state.rol),
        key="rol_selector"
    )
    st.session_state.rol = rol

    st.divider()
    st.markdown("**Plan maestro**")
    pagina = st.radio(
        "Módulo",
        ["📥 Llegada de fruta", "🏭 Distribución plantas", "📦 Producción PT", "📊 Stock y despachos"],
        label_visibility="collapsed"
    )

    if rol in ["Operaciones", "Gerencia"]:
        st.markdown("**Presupuesto**")
        pagina_op = st.radio(
            "Módulo op.",
            ["👥 Dotación MO", "📋 Resumen gerencial"],
            label_visibility="collapsed"
        )
    else:
        pagina_op = None

    st.divider()
    if st.button("⚡ Recalcular plan", use_container_width=True, type="primary"):
        with st.spinner("Calculando..."):
            st.session_state.plan.calcular()
            st.session_state.plan_calculado = True
        st.success("Plan recalculado")

    st.divider()
    estado_plan = "Borrador" if not st.session_state.plan_calculado else "Calculado"
    color_estado = "pill-amber" if not st.session_state.plan_calculado else "pill-green"
    st.markdown(f'Estado: <span class="status-pill {color_estado}">{estado_plan}</span>', unsafe_allow_html=True)

# ── Routing ───────────────────────────────────────────────────────────────
if pagina_op and pagina_op == "👥 Dotación MO":
    vista_activa = "dotacion"
elif pagina_op and pagina_op == "📋 Resumen gerencial":
    vista_activa = "resumen"
else:
    mapa = {
        "📥 Llegada de fruta":      "llegada",
        "🏭 Distribución plantas":  "distribucion",
        "📦 Producción PT":          "produccion",
        "📊 Stock y despachos":      "stock",
    }
    vista_activa = mapa.get(pagina, "llegada")

sem_labels = get_sem_labels()
plan = st.session_state.plan

# ═══════════════════════════════════════════════════════════════════════════
# VISTA: LLEGADA DE FRUTA
# ═══════════════════════════════════════════════════════════════════════════
if vista_activa == "llegada":
    st.markdown("## Proyección de llegada de fruta")
    st.caption("Ingresa las toneladas proyectadas por especie y semana. Los campos vacíos se tratan como cero.")

    # KPIs rápidos
    total_mmpp = float(plan.mmpp_total.sum()) if st.session_state.plan_calculado else 0
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total temporada", f"{total_mmpp:,.0f} t" if total_mmpp > 0 else "—")
    with col2:
        if st.session_state.plan_calculado and total_mmpp > 0:
            sem_pico = plan.mmpp_total.idxmax()
            st.metric("Semana pico", sem_pico, f"{plan.mmpp_total.max():,.0f} t")
        else:
            st.metric("Semana pico", "—")
    with col3:
        especies_activas = int((plan.mmpp_detalle.sum(axis=1) > 0).sum())
        st.metric("Especies con datos", f"{especies_activas} / {len(ESPECIES)}")
    with col4:
        st.metric("Estado", "Calculado ✓" if st.session_state.plan_calculado else "Sin calcular")

    st.divider()

    # Tabs por especie agrupada
    tab_names = list(ESPECIES_AGRUPADAS.keys())
    tabs = st.tabs(tab_names)

    for tab, (familia, subespecies) in zip(tabs, ESPECIES_AGRUPADAS.items()):
        with tab:
            st.markdown(f'<div class="section-header">{familia}</div>', unsafe_allow_html=True)

            # Mostrar solo semanas con datos o las primeras 20
            sems_mostrar = sem_labels[:20]

            # Construir DataFrame editable
            data_edit = {}
            for esp in subespecies:
                if esp in plan.mmpp_detalle.index:
                    data_edit[esp] = {
                        s: plan.mmpp_detalle.loc[esp, s]
                        for s in sems_mostrar
                    }

            if not data_edit:
                st.info("No hay subespecies configuradas para esta familia.")
                continue

            df_edit = pd.DataFrame(data_edit).T
            df_edit.index.name = "Especie"

            edited = st.data_editor(
                df_edit,
                use_container_width=True,
                key=f"editor_{familia}",
                column_config={
                    s: st.column_config.NumberColumn(s, min_value=0, format="%.0f", width="small")
                    for s in sems_mostrar
                }
            )

            if st.button(f"Guardar {familia}", key=f"save_{familia}", type="secondary"):
                for esp in edited.index:
                    for sem in sems_mostrar:
                        val = edited.loc[esp, sem]
                        if pd.notna(val):
                            plan.set_mmpp(esp, sem, float(val))
                st.success(f"✓ {familia} guardado")

    # Gráfico de curva de llegada
    if st.session_state.plan_calculado and total_mmpp > 0:
        st.divider()
        st.markdown('<div class="section-header">Curva de llegada total por especie</div>', unsafe_allow_html=True)

        fig = go.Figure()
        colors = px.colors.qualitative.Set2
        for i, (familia, _) in enumerate(ESPECIES_AGRUPADAS.items()):
            vals = plan.mmpp_agrupado.loc[familia].values
            if vals.sum() > 0:
                fig.add_trace(go.Bar(
                    name=familia, x=sem_labels, y=vals,
                    marker_color=colors[i % len(colors)]
                ))

        fig.update_layout(
            barmode="stack", height=300,
            margin=dict(l=0, r=0, t=20, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            yaxis_title="ton / semana",
        )
        st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# VISTA: DISTRIBUCIÓN A PLANTAS
# ═══════════════════════════════════════════════════════════════════════════
elif vista_activa == "distribucion":
    st.markdown("## Distribución de MMPP a plantas")
    st.caption("Asigna las toneladas de cada especie a cada planta de proceso.")

    modo = st.radio(
        "Modo de asignación",
        ["Manual por planta", "Proporcional automático"],
        horizontal=True
    )

    if modo == "Proporcional automático":
        st.markdown("**Proporciones por planta** (deben sumar 100%)")
        cols = st.columns(len(PLANTAS_ACTIVAS))
        props = {}
        for col, planta in zip(cols, PLANTAS_ACTIVAS):
            with col:
                defaults = {"Chillan": 55, "Parral": 25, "Loncoche": 12,
                            "Ecoberry": 5, "NN": 2, "Copramar": 1}
                props[planta] = st.number_input(
                    f"{planta} (%)", 0, 100,
                    value=defaults.get(planta, 0),
                    key=f"prop_{planta}"
                )

        total_props = sum(props.values())
        if abs(total_props - 100) > 0.5:
            st.warning(f"Las proporciones suman {total_props}% — deben sumar 100%")
        else:
            if st.button("Aplicar distribución proporcional", type="primary"):
                prop_dec = {p: v/100 for p, v in props.items()}
                plan.distribucion_proporcional(prop_dec)
                st.success("✓ Distribución aplicada")

    else:
        planta_sel = st.selectbox("Planta", PLANTAS_ACTIVAS)
        sems_mostrar = sem_labels[:20]

        if planta_sel in plan.distribucion:
            df_dist = plan.distribucion[planta_sel].loc[:, sems_mostrar]
            edited = st.data_editor(
                df_dist,
                use_container_width=True,
                key=f"dist_{planta_sel}",
                column_config={
                    s: st.column_config.NumberColumn(s, min_value=0, format="%.0f", width="small")
                    for s in sems_mostrar
                }
            )
            if st.button(f"Guardar distribución {planta_sel}", type="secondary"):
                for esp in edited.index:
                    for sem in sems_mostrar:
                        val = edited.loc[esp, sem]
                        if pd.notna(val):
                            plan.set_distribucion(planta_sel, esp, sem, float(val))
                st.success("✓ Guardado")

    if st.session_state.plan_calculado:
        st.divider()
        st.markdown('<div class="section-header">Distribución total por planta</div>', unsafe_allow_html=True)
        df_resumen = plan.resumen_distribucion()
        st.dataframe(df_resumen.style.format("{:.0f}"), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# VISTA: PRODUCCIÓN PT
# ═══════════════════════════════════════════════════════════════════════════
elif vista_activa == "produccion":
    st.markdown("## Producción PT proyectada")

    if not st.session_state.plan_calculado:
        st.info("Presiona **Recalcular plan** en el menú lateral para ver los resultados.")
    else:
        df_prod = plan.resumen_produccion()
        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown('<div class="section-header">PT por especie y semana (ton)</div>', unsafe_allow_html=True)
            st.dataframe(
                df_prod.style.format("{:.0f}").background_gradient(cmap="Greens", axis=1),
                use_container_width=True, height=420
            )
        with col2:
            st.markdown('<div class="section-header">Total temporada</div>', unsafe_allow_html=True)
            total_por_esp = df_prod.drop("TOTAL", errors="ignore").sum(axis=1).sort_values(ascending=False)
            fig = px.pie(
                values=total_por_esp[total_por_esp > 0].values,
                names=total_por_esp[total_por_esp > 0].index,
                color_discrete_sequence=px.colors.qualitative.Set2,
                hole=0.4,
            )
            fig.update_layout(
                height=350, margin=dict(l=0, r=0, t=10, b=0),
                paper_bgcolor="rgba(0,0,0,0)",
                showlegend=True,
                legend=dict(font=dict(size=11))
            )
            st.plotly_chart(fig, use_container_width=True)

        st.markdown('<div class="section-header">Curva de producción semanal</div>', unsafe_allow_html=True)
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=sem_labels, y=plan.pt_total.values,
            fill="tozeroy", mode="lines",
            line=dict(color="#1D9E75", width=2),
            fillcolor="rgba(29,158,117,0.15)",
            name="PT total"
        ))
        fig2.update_layout(
            height=220, margin=dict(l=0, r=0, t=10, b=40),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis_title="ton / semana",
        )
        st.plotly_chart(fig2, use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# VISTA: STOCK Y DESPACHOS
# ═══════════════════════════════════════════════════════════════════════════
elif vista_activa == "stock":
    st.markdown("## Stock proyectado y despachos")

    col1, col2 = st.columns(2)
    with col1:
        st.number_input(
            "Stock inicial temporada (ton)",
            min_value=0.0, value=float(plan.stock_inicial),
            key="stock_inicial_input",
            on_change=lambda: setattr(plan, "stock_inicial",
                                      st.session_state.stock_inicial_input)
        )
    with col2:
        st.info("Los despachos proyectados se basan en la curva histórica de la temporada anterior.")

    st.divider()

    if not st.session_state.plan_calculado:
        st.info("Presiona **Recalcular plan** para ver la proyección de stock.")
    else:
        df_stock = plan.resumen_stock()

        m1, m2, m3 = st.columns(3)
        m1.metric("Stock inicial", f"{plan.stock_inicial:,.0f} t")
        m2.metric("Stock final proyectado", f"{plan.stock_proyectado.iloc[-1]:,.0f} t")
        m3.metric("Total despachos", f"{plan.despachos.sum():,.0f} t")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=sem_labels, y=plan.stock_proyectado.values,
            name="Stock (ton)", fill="tozeroy", mode="lines",
            line=dict(color="#378ADD", width=2),
            fillcolor="rgba(55,138,221,0.12)"
        ))
        fig.add_trace(go.Bar(
            x=sem_labels, y=plan.pt_total.values,
            name="Entrada PT", marker_color="rgba(29,158,117,0.6)"
        ))
        fig.add_trace(go.Bar(
            x=sem_labels, y=plan.despachos.values,
            name="Despachos", marker_color="rgba(239,159,39,0.7)"
        ))
        fig.update_layout(
            barmode="group", height=350,
            margin=dict(l=0, r=0, t=20, b=40),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis_title="ton",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_stock.style.format("{:,.0f}"), use_container_width=True)


# ═══════════════════════════════════════════════════════════════════════════
# VISTA: DOTACIÓN MO
# ═══════════════════════════════════════════════════════════════════════════
elif vista_activa == "dotacion":
    st.markdown("## Dotación de mano de obra")
    st.caption("Calculada automáticamente a partir del plan de MMPP. Ajusta las tarifas antes de presupuestar.")

    with st.expander("⚙️ Tarifas de mano de obra (CLP / persona / semana de 6 días)", expanded=False):
        t = st.session_state.tarifas
        c1, c2, c3 = st.columns(3)
        with c1:
            t.operario_directo   = st.number_input("Op. directo", value=t.operario_directo,   step=10000)
            t.operario_recepcion = st.number_input("Op. recepción", value=t.operario_recepcion, step=10000)
        with c2:
            t.operario_frig = st.number_input("Op. frigorífico", value=t.operario_frig, step=10000)
            t.indirecto     = st.number_input("Indirecto / supervisión", value=t.indirecto, step=10000)
        with c3:
            t.mantencion  = st.number_input("Mantención", value=t.mantencion,  step=10000)
            t.hora_extra  = st.number_input("Hora extra ($/HH)", value=t.hora_extra, step=500)

        plan.params.tipo_cambio = st.number_input(
            "Tipo de cambio (CLP/USD)", value=plan.params.tipo_cambio, step=10.0
        )

    if st.button("Calcular dotación", type="primary"):
        motor_dot = MotorDotacion(st.session_state.tarifas)

        # Construir distribución por planta
        dist_dot = {}
        for planta in PLANTAS_ACTIVAS:
            sems_vals = {}
            for sem in sem_labels:
                total = float(plan.distribucion[planta].sum()[sem])
                sems_vals[sem] = total
            dist_dot[planta] = sems_vals

        dias_sem = {s.semana: s.dias_habiles for s in plan.semanas}
        resultados = motor_dot.calcular_temporada(dist_dot, dias_sem)
        resumen_dot = motor_dot.resumen_total(resultados)
        st.session_state.resumen_dotacion = resumen_dot
        st.success("✓ Dotación calculada")

    if "resumen_dotacion" in st.session_state:
        rd = st.session_state.resumen_dotacion

        m1, m2, m3 = st.columns(3)
        m1.metric("Costo total MO", f"MM$ {rd['costo_total_MM$']:,.1f}")
        m2.metric("Costo total MO (USD)", f"USD {rd['costo_total_USD']:,.0f}")
        m3.metric("Semanas planificadas", len(sem_labels))

        st.divider()
        tab1, tab2, tab3 = st.tabs(["Personas por planta", "Costo por planta", "KPIs eficiencia"])

        with tab1:
            st.markdown('<div class="section-header">Total personas × planta × semana</div>', unsafe_allow_html=True)
            st.dataframe(
                rd["personas_x_planta_semana"].style.format("{:.0f}")
                .background_gradient(cmap="Blues", axis=1),
                use_container_width=True
            )

        with tab2:
            st.markdown('<div class="section-header">Costo MO total (MM$) × planta × semana</div>', unsafe_allow_html=True)
            df_costo_mm = rd["costo_x_planta_semana"] / 1_000_000
            st.dataframe(
                df_costo_mm.style.format("{:.1f}")
                .background_gradient(cmap="Oranges", axis=1),
                use_container_width=True
            )

        with tab3:
            st.markdown('<div class="section-header">kg MMPP / HH directa · por planta y semana</div>', unsafe_allow_html=True)
            det = rd["detalle"]
            pivot_kpi = det.pivot_table(
                index="planta", columns="semana",
                values="kg/HH directa", aggfunc="mean"
            )
            st.dataframe(
                pivot_kpi.style.format("{:.1f}")
                .background_gradient(cmap="Greens", axis=1),
                use_container_width=True
            )

        # Gráfico costo por planta
        det = rd["detalle"]
        fig = px.bar(
            det.groupby(["planta","semana"])["costo_total ($)"].sum().reset_index(),
            x="semana", y="costo_total ($)", color="planta",
            color_discrete_sequence=px.colors.qualitative.Set2,
            labels={"costo_total ($)": "Costo MO ($)", "semana": ""},
            height=280,
        )
        fig.update_layout(
            margin=dict(l=0, r=0, t=20, b=40),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            yaxis_tickformat=",.0f",
        )
        st.plotly_chart(fig, use_container_width=True)

        if st.button("📥 Exportar a Excel"):
            import io
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                rd["personas_x_planta_semana"].to_excel(writer, sheet_name="Personas")
                (rd["costo_x_planta_semana"] / 1e6).round(2).to_excel(writer, sheet_name="Costo MM$")
                rd["detalle"].to_excel(writer, sheet_name="Detalle", index=False)
            st.download_button(
                "⬇️ Descargar Excel dotación",
                data=buf.getvalue(),
                file_name="dotacion_mo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )


# ═══════════════════════════════════════════════════════════════════════════
# VISTA: RESUMEN GERENCIAL
# ═══════════════════════════════════════════════════════════════════════════
elif vista_activa == "resumen":
    st.markdown("## Resumen gerencial · Temporada 2025–26")

    if not st.session_state.plan_calculado:
        st.warning("El plan aún no ha sido calculado. Usa el botón **Recalcular plan** en el menú lateral.")
    else:
        # KPIs principales
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("MMPP total", f"{plan.mmpp_total.sum():,.0f} t")
        c2.metric("PT proyectado", f"{plan.pt_total.sum():,.0f} t")
        c3.metric("Despachos proyectados", f"{plan.despachos.sum():,.0f} t")
        c4.metric("Stock final", f"{plan.stock_proyectado.iloc[-1]:,.0f} t")

        st.divider()

        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="section-header">Estado del plan</div>', unsafe_allow_html=True)
            modulos = [
                ("Llegada de fruta",     "Agrícola",    "pill-amber",  "Borrador"),
                ("Distribución plantas", "Operaciones", "pill-green",  "Aprobado"),
                ("Producción PT",        "Motor",       "pill-green",  "Calculado"),
                ("Stock proyectado",     "Motor",       "pill-green",  "Calculado"),
                ("Dotación MO",          "Operaciones", "pill-green" if "resumen_dotacion" in st.session_state else "pill-gray",
                 "Calculado" if "resumen_dotacion" in st.session_state else "Pendiente"),
                ("Embalaje",             "Operaciones", "pill-gray",   "Pendiente"),
                ("Frigorífico ext.",     "Logística",   "pill-gray",   "Pendiente"),
                ("Traslados",            "Logística",   "pill-green",  "Calculado"),
            ]
            df_estado = pd.DataFrame(modulos, columns=["Módulo", "Responsable", "_", "Estado"])
            for _, row in df_estado.iterrows():
                pill = f'<span class="status-pill {row["_"]}">{row["Estado"]}</span>'
                st.markdown(
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:6px 0;border-bottom:1px solid #f0f0f0">'
                    f'<span style="font-size:13px">{row["Módulo"]}</span>'
                    f'<span style="font-size:11px;color:#6c757d;margin-right:auto;margin-left:12px">'
                    f'{row["Responsable"]}</span>{pill}</div>',
                    unsafe_allow_html=True
                )

        with col2:
            st.markdown('<div class="section-header">Costos operacionales</div>', unsafe_allow_html=True)
            costo_mo  = st.session_state.resumen_dotacion["costo_total_MM$"] if "resumen_dotacion" in st.session_state else 0
            costo_frig = float(plan.costo_frig_ext.sum()) / 1e6
            costo_tras = float(plan.costo_traslados.sum()) / 1e6
            costo_tot  = costo_mo + costo_frig + costo_tras

            costos_data = {
                "Módulo": ["Mano de obra", "Frigorífico ext.", "Traslados"],
                "MM$":    [round(costo_mo, 1), round(costo_frig, 1), round(costo_tras, 1)],
            }
            fig_costos = px.bar(
                pd.DataFrame(costos_data),
                x="Módulo", y="MM$",
                color="Módulo",
                color_discrete_map={
                    "Mano de obra":     "#1D9E75",
                    "Frigorífico ext.": "#378ADD",
                    "Traslados":        "#EF9F27",
                },
                height=260,
                text="MM$",
            )
            fig_costos.update_traces(texttemplate="MM$ %{text:.1f}", textposition="outside")
            fig_costos.update_layout(
                showlegend=False,
                margin=dict(l=0, r=0, t=20, b=10),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_costos, use_container_width=True)
            st.metric("Costo operacional total", f"MM$ {costo_tot:,.1f}",
                      f"USD {costo_tot*1e6/plan.params.tipo_cambio:,.0f}")

        st.divider()
        st.markdown('<div class="section-header">Curva de stock proyectado</div>', unsafe_allow_html=True)
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(
            x=sem_labels, y=plan.stock_proyectado.values,
            fill="tozeroy", mode="lines+markers",
            line=dict(color="#378ADD", width=2),
            marker=dict(size=4),
            fillcolor="rgba(55,138,221,0.12)",
            name="Stock (ton)"
        ))
        fig3.update_layout(
            height=220, margin=dict(l=0, r=0, t=10, b=40),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis_title="ton",
        )
        st.plotly_chart(fig3, use_container_width=True)

        if st.button("📤 Exportar plan completo a Excel", type="primary"):
            import io
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                plan.resumen_mmpp().to_excel(writer, sheet_name="MMPP")
                plan.resumen_distribucion().to_excel(writer, sheet_name="Distribución")
                plan.resumen_produccion().to_excel(writer, sheet_name="Producción PT")
                plan.resumen_stock().to_excel(writer, sheet_name="Stock y Despachos")
                plan.resumen_costos().to_excel(writer, sheet_name="Costos CLP")
                if "resumen_dotacion" in st.session_state:
                    st.session_state.resumen_dotacion["detalle"].to_excel(
                        writer, sheet_name="Dotación", index=False
                    )
            st.download_button(
                "⬇️ Descargar plan completo",
                data=buf.getvalue(),
                file_name="plan_maestro_2025-26.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
