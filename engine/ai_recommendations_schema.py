"""
Schema Pydantic de las recomendaciones generadas por engine.ai_recommendations.

Cotas duras sobre todos los campos numéricos y enumerados (validación pre-persistencia
contra hallucinations del LLM). La validación cruzada de campaign_id contra los IDs
realmente presentes en el payload se hace fuera de este módulo, en ai_recommendations.py,
porque el schema no tiene acceso al contexto en tiempo de parseo.

Coordenadas del proyecto:
- engine.memory.record_autonomous_decision: persistencia destino
- config.agent_config.BUDGET_CHANGE_MIN_DAILY_MXN = 20.0
- routes/negativos_ui aplica el corte de 80 chars para negative keywords (commit 1ae0ca3)
"""
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


ActionType = Literal["scale", "reduce", "negative", "quality_alert"]
Urgency = Literal["normal", "urgent", "critical"]
AlertType = Literal[
    "low_quality_score",
    "low_ctr",
    "ad_disapproval",
    "broken_landing",
    "tracking_issue",
    "other",
]


class _BaseRecommendation(BaseModel):
    """Campos comunes a todas las recomendaciones. No instanciar directamente."""

    action_type: ActionType
    campaign_id: str = Field(min_length=1, max_length=20)
    campaign_name: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=10, max_length=500)
    urgency: Urgency = "normal"
    # risk_level=2 ("proposed") es la única posición coherente con la semántica
    # legacy de engine.memory.record_autonomous_decision. La gradación de severidad
    # real se expresa vía `urgency`.
    risk_level: int = Field(default=2, ge=0, le=4)


class ScaleRecommendation(_BaseRecommendation):
    action_type: Literal["scale"]
    new_budget_mxn: float = Field(gt=20.0, le=500.0)


class ReduceRecommendation(_BaseRecommendation):
    action_type: Literal["reduce"]
    new_budget_mxn: float = Field(gt=20.0, le=500.0)
    # La validación contra BUDGET_CHANGE_MAX_REDUCTION_PCT (0.60) se hace en
    # routes/presupuestos al ejecutar — aquí solo cota dura absoluta.


class NegativeRecommendation(_BaseRecommendation):
    action_type: Literal["negative"]
    keyword: str = Field(min_length=1, max_length=80)
    # 80 chars = límite de Google Ads. Mantener alineado con el filtro
    # de routes/negativos_ui (commit 1ae0ca3).


class QualityAlertRecommendation(_BaseRecommendation):
    action_type: Literal["quality_alert"]
    alert_type: AlertType
    alert_text: str = Field(min_length=10, max_length=1000)
    # quality_alert NUNCA muta nada. Solo se reporta vía email.


Recommendation = Annotated[
    Union[
        ScaleRecommendation,
        ReduceRecommendation,
        NegativeRecommendation,
        QualityAlertRecommendation,
    ],
    Field(discriminator="action_type"),
]


class RecommendationsResponse(BaseModel):
    """Respuesta esperada del LLM. Entre 0 y 5 recomendaciones."""

    recommendations: list[Recommendation] = Field(default_factory=list, max_length=5)
