"""
Thai Thai Ads Agent — Dashboard de Operaciones (Streamlit)

4 páginas:
  1. Cruce Negocio    — ads spend vs comensales, costo por comensal
  2. Actividad Agente — últimas auditorías, propuestas pendientes
  3. Tendencias       — gasto e inversión histórica por mes
  4. Historial Builder — campañas creadas con el sub-agente Builder

Consume endpoints del agente vía HTTP (no accede a DB ni API directamente).
"""
import os
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
AGENT_URL = os.getenv(
    "AGENT_URL",
    "https://thai-thai-ads-agent-624172071613.us-central1.run.app",
)

st.set_page_config(
    page_title="Thai Thai · Ops Dashboard",
    page_icon="🍜",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Helpers ───────────────────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def fetch(path: str, params: dict | None = None) -> dict | None:
    """GET al agente con caché de 5 minutos."""
    try:
        r = requests.get(f"{AGENT_URL}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Error al conectar con el agente: {e}")
        return None


def fmt_mxn(v: float) -> str:
    return f"${v:,.2f} MXN"


def metric_card(label: str, value: str, delta: str | None = None):
    st.metric(label=label, value=value, delta=delta)


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image("https://thaithaimerida.com/logo.png", width=120) if False else None
    st.title("🍜 Thai Thai Ops")
    st.caption("Dashboard de operaciones del agente de ads")
    st.divider()

    page = st.radio(
        "Página",
        ["Cruce Negocio", "Actividad del Agente", "Tendencias", "Historial Builder"],
        index=0,
    )

    st.divider()
    if st.button("🔄 Refrescar datos"):
        st.cache_data.clear()
        st.rerun()

    health = fetch("/ecosystem/health")
    if health:
        age_hours = health.get("snapshot_age_hours", 0)
        status_color = "🟢" if age_hours < 2 else "🟡" if age_hours < 6 else "🔴"
        st.caption(f"{status_color} Último snapshot: hace {age_hours:.1f}h")
    else:
        st.caption("⚠️ Agente no disponible")


# ── Página 1: Cruce Negocio ───────────────────────────────────────────────────

if page == "Cruce Negocio":
    st.header("📊 Cruce Negocio")
    st.caption("Inversión en ads vs actividad real del restaurante")

    data = fetch("/ecosystem/business-metrics")

    if not data:
        st.warning("No hay datos disponibles. Verifica la conexión con el agente.")
        st.stop()

    ads = data.get("ads", {})
    cross = data.get("cross_metrics", {})

    # KPIs principales
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("Inversión total (ads)", fmt_mxn(ads.get("total_spend", 0)))
    with col2:
        metric_card("Conversiones", str(ads.get("total_conversions", 0)))
    with col3:
        cpa = ads.get("avg_cpa", 0)
        cpa_color = "normal" if cpa <= 60 else "inverse"
        st.metric("CPA Promedio", fmt_mxn(cpa))
    with col4:
        cpc_comensal = cross.get("costo_por_comensal", 0)
        if cpc_comensal > 0:
            metric_card("Costo por comensal", fmt_mxn(cpc_comensal))
        else:
            st.metric("Costo por comensal", "N/D")

    st.divider()

    # Desglose local vs delivery
    campaign_sep = ads.get("campaign_separation", {})
    local = campaign_sep.get("local", {})
    delivery = campaign_sep.get("delivery", {})

    if local or delivery:
        st.subheader("Desglose por campaña")
        col_l, col_d = st.columns(2)

        with col_l:
            st.markdown("**🏪 Local (restaurante)**")
            st.metric("Gasto", fmt_mxn(local.get("spend", 0)))
            st.metric("Conversiones", local.get("conversions", 0))
            st.metric("CPA", fmt_mxn(local.get("cpa", 0)))

        with col_d:
            st.markdown("**🛵 Delivery**")
            st.metric("Gasto", fmt_mxn(delivery.get("spend", 0)))
            st.metric("Conversiones", delivery.get("conversions", 0))
            st.metric("CPA", fmt_mxn(delivery.get("cpa", 0)))

        # Gráfico de torta gasto
        if local.get("spend", 0) + delivery.get("spend", 0) > 0:
            fig = px.pie(
                values=[local.get("spend", 0), delivery.get("spend", 0)],
                names=["Local", "Delivery"],
                title="Distribución del gasto",
                color_discrete_sequence=["#FF6B6B", "#4ECDC4"],
            )
            st.plotly_chart(fig, use_container_width=True)

    # Cruce comensales
    comensales = cross.get("comensales", 0)
    ads_spend = cross.get("ads_spend", 0)
    if comensales > 0:
        st.divider()
        st.subheader("Cruce ads ↔ comensales")
        st.info(
            f"Se invirtieron **{fmt_mxn(ads_spend)}** en ads → "
            f"**{comensales} comensales** registrados → "
            f"**{fmt_mxn(cpc_comensal)} por comensal**"
        )

    # Waste alert
    waste = ads.get("total_waste", 0)
    if waste > 50:
        st.warning(f"⚠️ Desperdicio detectado: {fmt_mxn(waste)} en keywords sin conversión.")


# ── Página 2: Actividad del Agente ───────────────────────────────────────────

elif page == "Actividad del Agente":
    st.header("🤖 Actividad del Agente")
    st.caption("Últimas auditorías y propuestas de optimización")

    data = fetch("/ecosystem/ads-summary")

    if not data:
        st.warning("No hay datos disponibles.")
        st.stop()

    # Estado general
    col1, col2 = st.columns(2)
    with col1:
        status = data.get("status", "unknown")
        color = "🟢" if status == "active" else "🔴"
        st.metric("Estado del agente", f"{color} {status.upper()}")
    with col2:
        last_audit = data.get("last_audit_at", "N/D")
        st.metric("Última auditoría", last_audit[:16] if last_audit and last_audit != "N/D" else "N/D")

    st.divider()

    # Propuestas pendientes
    proposals = data.get("proposals", [])
    if proposals:
        st.subheader(f"📋 Propuestas pendientes ({len(proposals)})")
        for i, p in enumerate(proposals[:10], 1):
            with st.expander(f"#{i} — {p.get('action', 'Sin título')}"):
                st.write(f"**Descripción:** {p.get('description', 'N/D')}")
                if p.get("estimated_impact"):
                    st.write(f"**Impacto estimado:** {p['estimated_impact']}")
                if p.get("priority"):
                    st.write(f"**Prioridad:** {p['priority']}")
    else:
        st.success("✅ Sin propuestas pendientes")

    # Campañas activas
    campaigns = data.get("campaigns", [])
    if campaigns:
        st.divider()
        st.subheader(f"📡 Campañas activas ({len(campaigns)})")
        df = pd.DataFrame(campaigns)
        if not df.empty:
            # Mostrar columnas relevantes si existen
            cols = [c for c in ["name", "status", "spend", "conversions", "cpa"] if c in df.columns]
            if cols:
                st.dataframe(df[cols], use_container_width=True)
            else:
                st.dataframe(df, use_container_width=True)


# ── Página 3: Tendencias ──────────────────────────────────────────────────────

elif page == "Tendencias":
    st.header("📈 Tendencias")
    st.caption("Historial de gasto y conversiones por mes")

    # Selector de período
    months_back = st.slider("Meses a mostrar", min_value=1, max_value=12, value=6)

    # Generar lista de meses
    month_list = []
    now = datetime.now()
    for i in range(months_back):
        d = datetime(now.year, now.month, 1) - timedelta(days=i * 28)
        month_list.append(f"{d.year}-{d.month:02d}")

    # Fetch datos por mes
    records = []
    progress = st.progress(0, text="Cargando datos históricos...")

    for idx, month in enumerate(reversed(month_list)):
        data = fetch("/mission-control", params={"month": month})
        if data:
            metrics = data.get("metrics", {})
            records.append({
                "mes": month,
                "gasto": metrics.get("total_spend", 0),
                "conversiones": metrics.get("total_conversions", 0),
                "cpa": metrics.get("avg_cpa", 0),
                "desperdicio": metrics.get("total_waste", 0),
            })
        progress.progress((idx + 1) / len(month_list), text=f"Cargando {month}...")

    progress.empty()

    if not records:
        st.warning("No hay datos históricos disponibles.")
        st.stop()

    df = pd.DataFrame(records)

    # Gráfico gasto + conversiones
    st.subheader("Gasto mensual")
    fig_gasto = px.bar(
        df, x="mes", y="gasto",
        title="Inversión mensual en ads (MXN)",
        color_discrete_sequence=["#FF6B6B"],
        labels={"mes": "Mes", "gasto": "Gasto (MXN)"},
    )
    st.plotly_chart(fig_gasto, use_container_width=True)

    # CPA por mes
    st.subheader("CPA promedio por mes")
    fig_cpa = go.Figure()
    fig_cpa.add_trace(go.Scatter(
        x=df["mes"], y=df["cpa"],
        mode="lines+markers",
        name="CPA",
        line=dict(color="#4ECDC4", width=2),
        marker=dict(size=8),
    ))
    # Líneas de referencia de targets
    fig_cpa.add_hline(y=60, line_dash="dash", line_color="orange",
                      annotation_text="CPA Máx ($60)", annotation_position="right")
    fig_cpa.add_hline(y=100, line_dash="dash", line_color="red",
                      annotation_text="CPA Crítico ($100)", annotation_position="right")
    fig_cpa.update_layout(title="CPA mensual vs targets", xaxis_title="Mes", yaxis_title="CPA (MXN)")
    st.plotly_chart(fig_cpa, use_container_width=True)

    # Desperdicio
    if df["desperdicio"].sum() > 0:
        st.subheader("Desperdicio (keywords sin conversión)")
        fig_waste = px.bar(
            df, x="mes", y="desperdicio",
            title="Desperdicio mensual (MXN)",
            color_discrete_sequence=["#FFE66D"],
            labels={"mes": "Mes", "desperdicio": "Desperdicio (MXN)"},
        )
        st.plotly_chart(fig_waste, use_container_width=True)

    # Tabla resumen
    st.subheader("Tabla resumen")
    df_display = df.copy()
    df_display["gasto"] = df_display["gasto"].apply(lambda x: f"${x:,.2f}")
    df_display["cpa"] = df_display["cpa"].apply(lambda x: f"${x:,.2f}")
    df_display["desperdicio"] = df_display["desperdicio"].apply(lambda x: f"${x:,.2f}")
    st.dataframe(df_display.rename(columns={
        "mes": "Mes", "gasto": "Gasto", "conversiones": "Conversiones",
        "cpa": "CPA", "desperdicio": "Desperdicio"
    }), use_container_width=True)


# ── Página 4: Historial Builder ───────────────────────────────────────────────

elif page == "Historial Builder":
    st.header("🏗️ Historial Builder")
    st.caption("Campañas creadas con el sub-agente Builder")

    data = fetch("/pending-configs")

    if data is None:
        st.warning("No se pudo conectar al agente.")
        st.stop()

    configs = data if isinstance(data, list) else data.get("configs", [])

    if not configs:
        st.info("No hay configuraciones pendientes o desplegadas registradas.")
        st.markdown("""
        **¿Qué es el Builder?**
        El sub-agente Builder crea campañas de Google Ads desde lenguaje natural.

        **Ejemplo de uso vía API:**
        ```
        POST /build-campaign
        {"prompt": "Campaña de delivery para el fin de semana con presupuesto de $50 MXN/día"}
        ```
        """)
    else:
        st.subheader(f"{len(configs)} configuraciones registradas")

        for cfg in configs:
            cfg_id = cfg.get("id", "N/D")
            name = cfg.get("config", {}).get("name", cfg_id)
            status = cfg.get("status", "pending")
            created = cfg.get("created_at", "N/D")

            status_icon = {"pending": "⏳", "deployed": "✅", "failed": "❌"}.get(status, "❓")

            with st.expander(f"{status_icon} {name} — {status.upper()}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**ID:** `{cfg_id}`")
                    st.write(f"**Estado:** {status}")
                    st.write(f"**Creado:** {created[:16] if len(str(created)) > 16 else created}")

                config = cfg.get("config", {})
                if config:
                    with col2:
                        budget = config.get("daily_budget_mxn", 0)
                        st.write(f"**Presupuesto diario:** {fmt_mxn(budget)}")
                        geo = config.get("geo_target", "N/D")
                        st.write(f"**Geo target:** {geo}")
                        ad_groups = config.get("ad_groups", [])
                        st.write(f"**Grupos de anuncios:** {len(ad_groups)}")

                prompt = cfg.get("prompt", "")
                if prompt:
                    st.write(f"**Prompt original:** _{prompt}_")

                # Acción de deploy si está pendiente
                if status == "pending":
                    if st.button(f"🚀 Desplegar {cfg_id}", key=f"deploy_{cfg_id}"):
                        try:
                            r = requests.post(
                                f"{AGENT_URL}/deploy-pending/{cfg_id}",
                                timeout=30,
                            )
                            if r.ok:
                                st.success("¡Campaña desplegada correctamente!")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(f"Error al desplegar: {r.text}")
                        except Exception as e:
                            st.error(f"Error de conexión: {e}")

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    f"Thai Thai Ads Agent · {datetime.now().strftime('%Y-%m-%d %H:%M')} · "
    f"[Agente]({AGENT_URL}/health)"
)
