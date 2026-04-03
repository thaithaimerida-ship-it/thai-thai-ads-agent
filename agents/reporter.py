"""
Sub-agente Reportero — Genera reportes y dashboards.
Produce reportes diarios/semanales, guarda snapshots en GCS y alimenta Streamlit.
"""
import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# ── GCS config ────────────────────────────────────────────────────────────────
_GCS_BUCKET = os.getenv("AGENT_GCS_BUCKET", "")
_SNAPSHOTS_PREFIX = os.getenv("AGENT_GCS_SNAPSHOTS_PREFIX", "snapshots/daily")


def _get_gcs_bucket():
    """Lazy GCS bucket — returns None si no disponible."""
    if not _GCS_BUCKET:
        return None
    try:
        from google.cloud import storage
        client = storage.Client()
        return client.bucket(_GCS_BUCKET)
    except ImportError:
        logger.warning("reporter: google-cloud-storage no instalado — snapshots GCS desactivados")
        return None
    except Exception as e:
        logger.error("reporter: error iniciando GCS client: %s", e)
        return None


class Reporter:
    """Genera reportes, dashboards y persiste snapshots diarios en GCS."""

    # ── Reporte diario ────────────────────────────────────────────────────────

    def generate_daily_summary(self, audit_data: dict, analysis: dict) -> dict:
        """Genera resumen diario y lo guarda como snapshot en GCS."""
        campaigns = audit_data.get("campaigns", [])
        total_spend = sum(c.get("cost_micros", 0) / 1_000_000 for c in campaigns)
        total_conversions = sum(float(c.get("conversions", 0)) for c in campaigns)
        avg_cpa = total_spend / total_conversions if total_conversions > 0 else 0

        summary = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "metrics": {
                "spend": round(total_spend, 2),
                "conversions": round(total_conversions, 1),
                "cpa": round(avg_cpa, 2),
                "campaigns_active": len([c for c in campaigns if c.get("status") == "ENABLED"]),
            },
            "analysis_summary": analysis.get("executive_summary", {}),
            "proposals": analysis.get("proposals", []),
            "audit_run_type": audit_data.get("run_type", "daily"),
        }

        self._save_daily_snapshot(summary)
        return summary

    # ── Snapshot GCS ──────────────────────────────────────────────────────────

    def _save_daily_snapshot(self, summary: dict) -> bool:
        """
        Guarda el resumen diario como JSON en GCS.

        Path: gs://{bucket}/{prefix}/YYYY/MM/YYYY-MM-DD.json
        También actualiza latest.json con el snapshot más reciente.
        """
        bucket = _get_gcs_bucket()
        if bucket is None:
            logger.debug("reporter._save_daily_snapshot: GCS no disponible — skip")
            return False

        date_str = summary.get("date", datetime.now().strftime("%Y-%m-%d"))
        year, month, _ = date_str.split("-")
        blob_path = f"{_SNAPSHOTS_PREFIX}/{year}/{month}/{date_str}.json"
        latest_path = f"{_SNAPSHOTS_PREFIX}/latest.json"

        payload = json.dumps(summary, ensure_ascii=False, indent=2)

        try:
            bucket.blob(blob_path).upload_from_string(payload, content_type="application/json")
            bucket.blob(latest_path).upload_from_string(payload, content_type="application/json")
            logger.info("reporter: snapshot guardado → gs://%s/%s", _GCS_BUCKET, blob_path)
            return True
        except Exception as e:
            logger.error("reporter: fallo guardando snapshot: %s", e)
            return False

    # ── Lectura de snapshots ──────────────────────────────────────────────────

    def get_latest_snapshot(self) -> dict | None:
        """Lee el snapshot más reciente desde GCS."""
        bucket = _get_gcs_bucket()
        if bucket is None:
            return None
        try:
            blob = bucket.blob(f"{_SNAPSHOTS_PREFIX}/latest.json")
            if not blob.exists():
                return None
            return json.loads(blob.download_as_text())
        except Exception as e:
            logger.error("reporter.get_latest_snapshot: %s", e)
            return None

    def list_snapshots(self, year: str | None = None, month: str | None = None) -> list[dict]:
        """
        Lista snapshots disponibles.

        Si year/month se proveen, filtra por ese período.
        Retorna lista ordenada desc de {date, blob_path}.
        """
        bucket = _get_gcs_bucket()
        if bucket is None:
            return []

        prefix = _SNAPSHOTS_PREFIX
        if year:
            prefix = f"{prefix}/{year}"
            if month:
                prefix = f"{prefix}/{month}"

        try:
            blobs = list(bucket.list_blobs(prefix=prefix))
            results = []
            for b in blobs:
                name = b.name
                if name.endswith("latest.json"):
                    continue
                filename = name.split("/")[-1].replace(".json", "")
                if len(filename) == 10:  # YYYY-MM-DD
                    results.append({"date": filename, "blob_path": name})
            results.sort(key=lambda x: x["date"], reverse=True)
            return results
        except Exception as e:
            logger.error("reporter.list_snapshots: %s", e)
            return []

    def get_snapshot(self, date_str: str) -> dict | None:
        """Lee un snapshot específico por fecha (YYYY-MM-DD)."""
        bucket = _get_gcs_bucket()
        if bucket is None:
            return None
        year, month, _ = date_str.split("-")
        blob_path = f"{_SNAPSHOTS_PREFIX}/{year}/{month}/{date_str}.json"
        try:
            blob = bucket.blob(blob_path)
            if not blob.exists():
                return None
            return json.loads(blob.download_as_text())
        except Exception as e:
            logger.error("reporter.get_snapshot(%s): %s", date_str, e)
            return None

    def get_snapshots_range(self, dates: list[str]) -> list[dict]:
        """Lee múltiples snapshots por lista de fechas. Omite los que no existen."""
        results = []
        for date_str in dates:
            snap = self.get_snapshot(date_str)
            if snap:
                results.append(snap)
        return results

    # ── Reporte semanal ───────────────────────────────────────────────────────

    def generate_weekly_report(self, daily_summaries: list) -> dict:
        """Genera reporte semanal a partir de resúmenes diarios."""
        if not daily_summaries:
            return {}

        total_spend = sum(s.get("metrics", {}).get("spend", 0) for s in daily_summaries)
        total_conversions = sum(s.get("metrics", {}).get("conversions", 0) for s in daily_summaries)
        avg_cpa = total_spend / total_conversions if total_conversions > 0 else 0

        dates = [s.get("date", "") for s in daily_summaries if s.get("date")]
        date_range = f"{min(dates)} → {max(dates)}" if dates else "N/A"

        all_proposals = []
        for s in daily_summaries:
            all_proposals.extend(s.get("proposals", []))

        return {
            "week": date_range,
            "generated_at": datetime.now().isoformat(),
            "totals": {
                "spend": round(total_spend, 2),
                "conversions": round(total_conversions, 1),
                "avg_cpa": round(avg_cpa, 2),
                "days_with_data": len(daily_summaries),
            },
            "proposals_count": len(all_proposals),
            "proposals": all_proposals,
        }
