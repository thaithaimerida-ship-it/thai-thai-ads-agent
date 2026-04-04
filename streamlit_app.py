"""
Thai Thai Ads Agent — Dashboard de Operaciones (Streamlit)

Fuentes de datos:
  - /ecosystem/ads-summary      → rápido, snapshot GCS (<200ms)
  - /ecosystem/business-metrics → rápido, snapshot GCS (<200ms)
  - /ecosystem/health           → rápido, metadata del snapshot
  - /pending-configs            → rápido, in-memory
  - /mission-control            → PESADO, NO se llama al render inicial
"""
import os
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from datetime import datetime

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
    """GET al agente con caché de 5 minutos. Retorna None sin mostrar error — el caller decide."""
    try:
        r = requests.get(f"{AGENT_URL}{path}", params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        return {"_error": "timeout"}
    except Exception:
        return None


def fmt_mxn(v: float) -> str:
    return f"${v:,.2f} MXN"


def _show_snapshot_error(data: dict | None) -> bool:
    """
    Muestra mensaje apropiado si no hay datos. Retorna True si debe detenerse.
    """
    if data is None:
        st.error("El backend no respondió. Verifica que Cloud Run esté activo.")
        return True
    if data.get("_error") == "timeout":
        st.error("Timeout al conectar con el agente (>15s). El backend puede estar en cold start.")
        return True
    if data.get("status") == "no_snapshot":
        st.warning("No hay snapshot disponible aún.")
        st.info("Ejecuta `GET /run-autonomous-audit` en el backend para generar el primer snapshot.")
        return True
    return False


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
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
    if health and not health.get("_error") and health.get("snapshot_available"):
        age_min = health.get("snapshot_age_minutes") or 0
        age_h = age_min / 60
        color = "🟢" if age_h < 2 else "🟡" if age_h < 6 else "🔴"
        st.caption(f"{color} Snapshot: hace {age_min:.0f} min")
    elif health is None or health.get("_error"):
        st.caption("⚠️ Agente no disponible")
    else:
        st.caption("⚪ Sin snapshot aún")


# ── Página 1: Cruce Negocio ───────────────────────────────────────────────────

if page == "Cruce Negocio":
    st.header("📊 Cruce Negocio")
    st.caption("Inversión en ads vs actividad real del restaurante — datos del último snapshot")

    data = fetch("/ecosystem/business-metrics")
    if _show_snapshot_error(data):
        st.stop()

    ads = data.get("ads", {})
    cross = data.get("cross_metrics", {})

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Inversión total", fmt_mxn(ads.get("total_spend", 0)))
    with col2:
        st.metric("Conversiones", str(ads.get("total_conversions", 0)))
    with col3:
        st.metric("CPA Promedio", fmt_mxn(ads.get("avg_cpa", 0)))
    with col4:
        cpc = cross.get("costo_por_comensal", 0)
        st.metric("Costo por comensal", fmt_mxn(cpc) if cpc > 0 else "N/D")

    st.divider()

    campaign_sep = ads.get("campaign_separation", {})
    local = campaign_sep.get("local", {})
    delivery = campaign_sep.get("delivery", {})

    if local or delivery:
        st.subheader("Desglose por campaña")
        col_l, col_d = st.columns(2)
        with col_l:
            st.markdown("**Local (restaurante)**")
            st.metric("Gasto", fmt_mxn(local.get("spend", 0)))
            st.metric("Conversiones", local.get("conversions", 0))
            st.metric("CPA", fmt_mxn(local.get("cpa", 0)))
        with col_d:
            st.markdown("**Delivery**")
            st.metric("Gasto", fmt_mxn(delivery.get("spend", 0)))
            st.metric("Conversiones", delivery.get("conversions", 0))
            st.metric("CPA", fmt_mxn(delivery.get("cpa", 0)))

        if local.get("spend", 0) + delivery.get("spend", 0) > 0:
            fig = px.pie(
                values=[local.get("spend", 0), delivery.get("spend", 0)],
                names=["Local", "Delivery"],
                title="Distribución del gasto",
                color_discrete_sequence=["#FF6B6B", "#4ECDC4"],
            )
            st.plotly_chart(fig, use_container_width=True)

    comensales = cross.get("comensales", 0)
    ads_spend = cross.get("ads_spend", 0)
    if comensales > 0:
        st.divider()
        st.subheader("Cruce ads ↔ comensales")
        st.info(
            f"Se invirtieron **{fmt_mxn(ads_spend)}** en ads → "
            f"**{comensales} comensales** registrados → "
            f"**{fmt_mxn(cpc)} por comensal**"
        )

    waste = ads.get("total_waste", 0)
    if waste > 50:
        st.warning(f"Desperdicio detectado: {fmt_mxn(waste)} en keywords sin conversión.")


# ── Página 2: Actividad del Agente ───────────────────────────────────────────

elif page == "Actividad del Agente":
    st.header("🤖 Actividad del Agente")
    st.caption("Propuestas y campañas — datos del último snapshot")

    data = fetch("/ecosystem/ads-summary")
    if _show_snapshot_error(data):
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        ts = data.get("timestamp", "N/D")
        st.metric("Snapshot generado", ts[:16] if ts and ts != "N/D" else "N/D")
    with col2:
        st.metric("Propuestas pendientes", data.get("proposals_count", 0))

    st.divider()

    campaigns = data.get("campaigns", [])
    if campaigns:
        st.subheader(f"Campañas ({len(campaigns)})")
        df = pd.DataFrame(campaigns)
        cols = [c for c in ["name", "status", "spend", "conversions", "cpa"] if c in df.columns]
        st.dataframe(df[cols] if cols else df, use_container_width=True)

    summary = data.get("summary", {})
    if summary:
        st.divider()
        st.subheader("Resumen del snapshot")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Inversión", fmt_mxn(summary.get("spend", 0)))
        with col_b:
            st.metric("Conversiones", summary.get("conversions", 0))
        with col_c:
            st.metric("Desperdicio estimado", fmt_mxn(summary.get("estimated_waste", 0)))


# ── Página 3: Tendencias ──────────────────────────────────────────────────────

elif page == "Tendencias":
    st.header("📈 Tendencias")
    st.caption("Historial de gasto y conversiones por mes")

    st.warning(
        "Carga de histórico desactivada temporalmente. "
        "Esta vista requiere múltiples llamadas seriales a `/mission-control` "
        "(una por mes), lo que puede saturar el backend en cold start."
    )
    st.info("Se habilitará cuando los snapshots históricos estén disponibles en GCS.")

    if st.button("Cargar histórico ahora (puede tardar 1-2 min)"):
        months_back = st.slider("Meses a cargar", min_value=1, max_value=6, value=3)
        now = datetime.now()
        month_list = []
        for i in range(months_back):
            d = datetime(now.year, now.month, 1)
            m = d.month - i
            y = d.year
            while m <= 0:
                m += 12
                y -= 1
            month_list.append(f"{y}-{m:02d}")

        records = []
        progress = st.progress(0, text="Cargando...")
        for idx, month in enumerate(reversed(month_list)):
            r = fetch("/mission-control", params={"month": month})
            if r and not r.get("_error") and r.get("metrics"):
                metrics = r["metrics"]
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
            st.error("No se obtuvieron datos. El backend puede estar en cold start.")
        else:
            df = pd.DataFrame(records)
            st.subheader("Gasto mensual")
            fig = px.bar(df, x="mes", y="gasto", labels={"mes": "Mes", "gasto": "Gasto (MXN)"})
            st.plotly_chart(fig, use_container_width=True)

            fig_cpa = go.Figure()
            fig_cpa.add_trace(go.Scatter(x=df["mes"], y=df["cpa"], mode="lines+markers", name="CPA"))
            fig_cpa.add_hline(y=60, line_dash="dash", line_color="orange", annotation_text="Máx $60")
            fig_cpa.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="Crítico $100")
            fig_cpa.update_layout(title="CPA mensual", xaxis_title="Mes", yaxis_title="CPA (MXN)")
            st.plotly_chart(fig_cpa, use_container_width=True)


# ── Página 4: Historial Builder ───────────────────────────────────────────────

elif page == "Historial Builder":
    st.header("🏗️ Historial Builder")
    st.caption("Campañas creadas con el sub-agente Builder")

    data = fetch("/pending-configs")
    if data is None or data.get("_error"):
        st.error("No se pudo conectar al agente.")
        st.stop()

    configs = data if isinstance(data, list) else data.get("configs", [])

    if not configs:
        st.info("No hay configuraciones registradas.")
        st.markdown(
            "**¿Qué es el Builder?** Crea campañas de Google Ads desde lenguaje natural.\n\n"
            "Uso: `POST /build-campaign` con `{\"prompt\": \"...\"}`"
        )
    else:
        st.subheader(f"{len(configs)} configuraciones registradas")
        for cfg in configs:
            cfg_id = cfg.get("id", "N/D")
            name = cfg.get("config", {}).get("name", cfg_id)
            status = cfg.get("status", "pending")
            created = cfg.get("created_at", "N/D")
            icon = {"pending": "⏳", "deployed": "✅", "failed": "❌"}.get(status, "❓")

            with st.expander(f"{icon} {name} — {status.upper()}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**ID:** `{cfg_id}`")
                    st.write(f"**Estado:** {status}")
                    st.write(f"**Creado:** {str(created)[:16]}")
                config = cfg.get("config", {})
                if config:
                    with col2:
                        st.write(f"**Presupuesto diario:** {fmt_mxn(config.get('daily_budget_mxn', 0))}")
                        st.write(f"**Geo:** {config.get('geo_target', 'N/D')}")
                        st.write(f"**Grupos:** {len(config.get('ad_groups', []))}")
                if cfg.get("prompt"):
                    st.write(f"**Prompt:** _{cfg['prompt']}_")
                if status == "pending":
                    if st.button(f"Desplegar {cfg_id}", key=f"deploy_{cfg_id}"):
                        try:
                            r = requests.post(f"{AGENT_URL}/deploy-pending/{cfg_id}", timeout=30)
                            if r.ok:
                                st.success("Campaña desplegada.")
                                st.cache_data.clear()
                                st.rerun()
                            else:
                                st.error(f"Error: {r.text}")
                        except Exception as e:
                            st.error(f"Error de conexión: {e}")

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption(f"Thai Thai Ops · {datetime.now().strftime('%Y-%m-%d %H:%M')} · {AGENT_URL}/health")
