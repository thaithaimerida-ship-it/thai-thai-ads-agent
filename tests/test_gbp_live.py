"""GBP en vivo para el monitor: mapeo de datos + red de seguridad (degradación por slice).

Sin red: se mockean fetch_performance_30d_cached / fetch_reviews_cached. Lo que se prueba
es que load_gbp_context_live arma bien las secciones con dato real Y que si UNA API falla,
esa sola sección sale data_broken (la otra sobrevive) — nunca un correo a medias.
"""
from engine import gbp_reviews, monitor_sources


def _raw_review(stars="FIVE", comment="Rico todo", reply=False):
    r = {"starRating": stars, "comment": comment, "createTime": "2026-06-10T00:00:00Z",
         "reviewer": {"displayName": "Cliente"}}
    if reply:
        r["reviewReply"] = {"comment": "¡Gracias!"}
    return r


def _full(reviews, completo=True):
    """Salida de la FUENTE ÚNICA fetch_reviews_full."""
    return {"reviews": reviews, "average_rating": 4.7, "total_reviews": 100,
            "distribucion": {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}, "pendientes": [], "completo": completo}


def test_live_arma_ambas_secciones_con_dato(monkeypatch):
    monkeypatch.setattr(gbp_reviews, "fetch_performance_30d_cached",
                        lambda *a, **k: {"BUSINESS_IMPRESSIONS_MOBILE_MAPS": 22173,
                                         "BUSINESS_DIRECTION_REQUESTS": 1284})
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_full",
                        lambda *a, **k: _full([_raw_review(), _raw_review(stars="TWO", comment="meh")]))
    ctx = monitor_sources.load_gbp_context_live()
    assert ctx["gbp"]["data_broken"] is False
    assert ctx["gbp"]["metricas"]["vistas_maps"]["valor"] == 22173
    assert ctx["reviews"]["data_broken"] is False
    assert len(ctx["reviews"]["reviews"]) == 2


def test_maps_caido_no_tumba_resenas(monkeypatch):
    # La Performance API falla; las reseñas siguen vivas → solo Maps en reparación.
    def _boom(*a, **k):
        raise RuntimeError("perf API 500")
    monkeypatch.setattr(gbp_reviews, "fetch_performance_30d_cached", _boom)
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_full", lambda *a, **k: _full([_raw_review()]))
    ctx = monitor_sources.load_gbp_context_live()
    assert ctx["gbp"]["data_broken"] is True          # Maps cae
    assert ctx["reviews"]["data_broken"] is False      # reseñas sobreviven


def test_resenas_caidas_no_tumban_maps(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("reviews API 403")
    monkeypatch.setattr(gbp_reviews, "fetch_performance_30d_cached",
                        lambda *a, **k: {"BUSINESS_IMPRESSIONS_MOBILE_MAPS": 100})
    monkeypatch.setattr(gbp_reviews, "fetch_reviews_full", _boom)
    ctx = monitor_sources.load_gbp_context_live()
    assert ctx["gbp"]["data_broken"] is False          # Maps sobrevive
    assert ctx["reviews"]["data_broken"] is True        # reseñas caen
