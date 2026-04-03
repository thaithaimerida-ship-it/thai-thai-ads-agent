"""
Thai Thai Ads Agent — Sincronización de base de datos con Google Cloud Storage

Resuelve el problema de SQLite efímero en Cloud Run:
  - Cloud Run puede reciclar instancias entre el audit diario y el weekly report
  - Cada instancia nueva comienza con un filesystem vacío
  - Esta capa sincroniza la DB con GCS en startup y al terminar auditorías

Flujo:
  1. Al iniciar la instancia: download_from_gcs() → restaura el estado más reciente
  2. Después de cada audit: upload_to_gcs() → persiste el estado actualizado
  3. Los endpoints de aprobación funcionan porque la instancia descargó en el paso 1

Configuración (variables de entorno):
  AGENT_GCS_BUCKET  — nombre del bucket GCS (ej. "thai-thai-agent-data")
                      Si no está definida, la sincronización es no-op (dev local)
  AGENT_GCS_DB_BLOB — path del blob dentro del bucket (default: "memory/thai_thai_memory.db")

Path local:
  En Cloud Run: /tmp/thai_thai_memory.db  (filesystem efímero pero writable)
  En local:     ./thai_thai_memory.db
"""

import os
import logging

logger = logging.getLogger(__name__)

# ── Paths canónicos ───────────────────────────────────────────────────────────

_IS_CLOUD_RUN = bool(os.getenv("K_SERVICE") or os.getenv("GOOGLE_CLOUD_PROJECT"))

_LOCAL_DB_PATH  = "/tmp/thai_thai_memory.db" if _IS_CLOUD_RUN else "./thai_thai_memory.db"
_GCS_BUCKET     = os.getenv("AGENT_GCS_BUCKET", "")
_GCS_DB_BLOB    = os.getenv("AGENT_GCS_DB_BLOB", "memory/thai_thai_memory.db")

# ── Exportación pública ───────────────────────────────────────────────────────

def get_db_path() -> str:
    """
    Retorna el path canónico de la base de datos para el entorno actual.

    - Cloud Run: /tmp/thai_thai_memory.db
    - Local dev: ./thai_thai_memory.db
    """
    return _LOCAL_DB_PATH


# ── Cliente GCS (lazy) ────────────────────────────────────────────────────────

_gcs_client = None

def _get_gcs_client():
    global _gcs_client
    if _gcs_client is None:
        try:
            from google.cloud import storage
            _gcs_client = storage.Client()
        except ImportError:
            logger.warning("db_sync: google-cloud-storage no instalado — sync desactivada")
        except Exception as e:
            logger.warning("db_sync: no se pudo inicializar GCS client: %s", e)
    return _gcs_client


# ── Operaciones de sync ───────────────────────────────────────────────────────

def download_from_gcs() -> bool:
    """
    Descarga la DB desde GCS al path local si:
      1. AGENT_GCS_BUCKET está configurado
      2. El blob existe en GCS
      3. La DB local no existe o está vacía

    Retorna True si se descargó, False si no aplica o falló.

    Se llama en startup_event() — solo una vez por instancia.
    """
    if not _GCS_BUCKET:
        logger.debug("db_sync.download: AGENT_GCS_BUCKET no configurado — skip")
        return False

    local = _LOCAL_DB_PATH

    # Si ya existe la DB local con datos, no sobrescribir
    if os.path.exists(local) and os.path.getsize(local) > 0:
        logger.info("db_sync.download: DB local ya existe (%d bytes) — skip", os.path.getsize(local))
        return False

    client = _get_gcs_client()
    if not client:
        return False

    try:
        bucket = client.bucket(_GCS_BUCKET)
        blob   = bucket.blob(_GCS_DB_BLOB)

        if not blob.exists():
            logger.info("db_sync.download: blob gs://%s/%s no existe — DB nueva", _GCS_BUCKET, _GCS_DB_BLOB)
            return False

        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        blob.download_to_filename(local)
        size = os.path.getsize(local)
        logger.info("db_sync.download: ✓ descargado gs://%s/%s → %s (%d bytes)",
                    _GCS_BUCKET, _GCS_DB_BLOB, local, size)
        return True

    except Exception as e:
        logger.error("db_sync.download: fallo descargando DB desde GCS: %s", e)
        return False


def upload_to_gcs() -> bool:
    """
    Sube la DB local a GCS.

    Retorna True si se subió, False si no aplica o falló.

    Se llama al final de run_autonomous_audit() — después de registrar
    todas las decisiones de la corrida.
    """
    if not _GCS_BUCKET:
        logger.debug("db_sync.upload: AGENT_GCS_BUCKET no configurado — skip")
        return False

    local = _LOCAL_DB_PATH

    if not os.path.exists(local):
        logger.warning("db_sync.upload: DB local no existe en %s — skip", local)
        return False

    client = _get_gcs_client()
    if not client:
        return False

    try:
        bucket = client.bucket(_GCS_BUCKET)
        blob   = bucket.blob(_GCS_DB_BLOB)
        blob.upload_from_filename(local)
        size = os.path.getsize(local)
        logger.info("db_sync.upload: ✓ subido %s → gs://%s/%s (%d bytes)",
                    local, _GCS_BUCKET, _GCS_DB_BLOB, size)
        return True

    except Exception as e:
        logger.error("db_sync.upload: fallo subiendo DB a GCS: %s", e)
        return False
