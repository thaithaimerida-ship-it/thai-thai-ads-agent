"""
Sub-agente Ejecutor — Escribe cambios en Google Ads API.
Acciones: block_keyword, update_budget, pause_adgroup, add_keyword, remove_theme
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class Executor:
    def __init__(self):
        self.customer_id = os.getenv("GOOGLE_ADS_TARGET_CUSTOMER_ID", "4021070209")

    def _get_client(self):
        from engine.ads_client import get_ads_client
        return get_ads_client()

    def _log_action(self, action_type, target, details, result):
        try:
            from engine.ads_client import log_agent_action
            log_agent_action(
                action_type=action_type, target=target,
                details_before=details,
                details_after={"result": result, "timestamp": datetime.now().isoformat()},
                decision="executed",
            )
        except Exception as e:
            logger.warning("Executor._log_action failed: %s", e)

    def block_keyword(self, campaign_id, keyword):
        from engine.ads_client import add_negative_keyword
        client = self._get_client()
        try:
            add_negative_keyword(client, self.customer_id, campaign_id, keyword)
            self._log_action("block_keyword", keyword, {"campaign_id": campaign_id}, "success")
            return {"status": "executed", "action": "block_keyword", "keyword": keyword, "campaign_id": campaign_id}
        except Exception as e:
            return {"status": "error", "action": "block_keyword", "error": str(e)}

    def update_budget(self, campaign_id, new_budget_mxn, reason=""):
        from engine.ads_client import fetch_campaign_budget_info, update_campaign_budget, verify_budget_still_actionable
        client = self._get_client()
        try:
            budget_info = fetch_campaign_budget_info(client, self.customer_id, campaign_id)
        except Exception as e:
            return {"status": "error", "action": "update_budget", "error": f"No se pudo leer presupuesto: {e}"}
        budget_resource = budget_info.get("budget_resource_name")
        current_budget = budget_info.get("budget_amount_micros", 0) / 1_000_000
        if not budget_resource:
            return {"status": "error", "action": "update_budget", "error": "No budget resource found"}
        try:
            v = verify_budget_still_actionable(
                client, self.customer_id, campaign_id,
                budget_at_proposal_mxn=current_budget,
                suggested_budget_mxn=new_budget_mxn,
            )
            if not v.get("actionable", False):
                return {"status": "blocked", "action": "update_budget", "reason": v.get("reason", "Verification failed")}
        except Exception as e:
            logger.warning("Budget verification failed: %s", e)
        try:
            update_campaign_budget(client, self.customer_id, budget_resource, int(new_budget_mxn * 1_000_000))
            self._log_action("update_budget", campaign_id, {"old": current_budget, "new": new_budget_mxn, "reason": reason}, "success")
            return {
                "status": "executed", "action": "update_budget",
                "campaign_id": campaign_id,
                "old_budget_mxn": round(current_budget, 2),
                "new_budget_mxn": round(new_budget_mxn, 2),
            }
        except Exception as e:
            return {"status": "error", "action": "update_budget", "error": str(e)}

    def pause_adgroup(self, campaign_id, adgroup_id, reason=""):
        from engine.ads_client import pause_ad_group, verify_adgroup_still_pausable
        client = self._get_client()
        try:
            v = verify_adgroup_still_pausable(client, self.customer_id, campaign_id, adgroup_id)
            if not v.get("pausable", False):
                return {"status": "blocked", "action": "pause_adgroup", "reason": v.get("reason", "Verification failed")}
        except Exception as e:
            logger.warning("Adgroup verification failed: %s", e)
        try:
            pause_ad_group(client, self.customer_id, campaign_id, adgroup_id)
            self._log_action("pause_adgroup", f"{campaign_id}/{adgroup_id}", {"reason": reason}, "success")
            return {"status": "executed", "action": "pause_adgroup", "campaign_id": campaign_id, "adgroup_id": adgroup_id}
        except Exception as e:
            return {"status": "error", "action": "pause_adgroup", "error": str(e)}

    def add_keyword(self, ad_group_resource, keyword_text, match_type="PHRASE", cpc_bid_micros=None):
        from engine.ads_client import add_keyword_to_ad_group
        client = self._get_client()
        try:
            add_keyword_to_ad_group(client, self.customer_id, ad_group_resource, keyword_text, match_type)
            self._log_action("add_keyword", keyword_text, {"ad_group": ad_group_resource}, "success")
            return {"status": "executed", "action": "add_keyword", "keyword": keyword_text, "match_type": match_type}
        except Exception as e:
            return {"status": "error", "action": "add_keyword", "error": str(e)}

    def pause_campaign(self, campaign_id):
        from engine.ads_client import get_ads_client
        client = self._get_client()
        try:
            campaign_service = client.get_service("CampaignService")
            campaign_operation = client.get_type("CampaignOperation")
            campaign = campaign_operation.update
            campaign.resource_name = campaign_service.campaign_path(self.customer_id, campaign_id)
            campaign.status = client.enums.CampaignStatusEnum.PAUSED
            campaign_operation.update_mask.paths[:] = ["status"]
            campaign_service.mutate_campaigns(customer_id=self.customer_id, operations=[campaign_operation])
            self._log_action("pause_campaign", campaign_id, {}, "success")
            return {"status": "executed", "action": "pause_campaign", "campaign_id": campaign_id}
        except Exception as e:
            return {"status": "error", "action": "pause_campaign", "error": str(e)}

    def remove_theme(self, criterion_resource_name):
        from engine.ads_client import remove_smart_campaign_theme
        client = self._get_client()
        try:
            remove_smart_campaign_theme(client, self.customer_id, criterion_resource_name)
            self._log_action("remove_theme", criterion_resource_name, {}, "success")
            return {"status": "executed", "action": "remove_theme", "criterion": criterion_resource_name}
        except Exception as e:
            return {"status": "error", "action": "remove_theme", "error": str(e)}

    def add_ad_headlines(self, ad_group_resource, ad_id, new_headlines):
        from engine.ads_client import update_rsa_headlines
        client = self._get_client()
        # Validar max 30 chars
        valid = [h for h in new_headlines if len(h) <= 30]
        invalid = [h for h in new_headlines if len(h) > 30]
        if invalid:
            logger.warning("add_ad_headlines: %d headlines exceden 30 chars — descartados", len(invalid))
        if not valid:
            return {"status": "skipped", "action": "add_ad_headlines", "reason": "no headlines válidos"}
        try:
            result = update_rsa_headlines(client, self.customer_id, ad_group_resource, ad_id, valid)
            self._log_action("add_ad_headlines", ad_id, {"ad_group": ad_group_resource, "headlines": valid}, result.get("status"))
            return {"status": result.get("status", "error"), "action": "add_ad_headlines", "ad_id": ad_id, "detail": result}
        except Exception as e:
            return {"status": "error", "action": "add_ad_headlines", "error": str(e)}

    def replace_rsa_headlines(self, ad_group_resource, ad_id, new_headlines):
        """Reemplaza headlines de un RSA con lista optimizada para QS. Replace real, no append."""
        from engine.ads_client import replace_rsa_headlines as _replace_fn
        client = self._get_client()
        # Guardrail: solo RSA válidos — ad_group_resource y ad_id deben existir
        if not ad_group_resource or not ad_id or str(ad_id) in ("0", ""):
            return {"status": "skipped", "action": "replace_rsa_headlines", "reason": "RSA inválido (sin resource o ad_id)"}
        if not new_headlines:
            return {"status": "skipped", "action": "replace_rsa_headlines", "reason": "lista de headlines vacía"}
        try:
            result = _replace_fn(client, self.customer_id, ad_group_resource, ad_id, new_headlines)
            self._log_action("replace_rsa_headlines", ad_id, {"ad_group": ad_group_resource, "headlines": new_headlines}, result.get("status"))
            return {"status": result.get("status", "error"), "action": "replace_rsa_headlines", "ad_id": ad_id, "detail": result}
        except Exception as e:
            return {"status": "error", "action": "replace_rsa_headlines", "error": str(e)}

    def add_ad_descriptions(self, ad_group_resource, ad_id, new_descriptions):
        from engine.ads_client import update_rsa_descriptions
        client = self._get_client()
        valid = [d for d in new_descriptions if len(d) <= 90]
        invalid = [d for d in new_descriptions if len(d) > 90]
        if invalid:
            logger.warning("add_ad_descriptions: %d descriptions exceden 90 chars — descartadas", len(invalid))
        if not valid:
            return {"status": "skipped", "action": "add_ad_descriptions", "reason": "no descriptions válidas"}
        try:
            result = update_rsa_descriptions(client, self.customer_id, ad_group_resource, ad_id, valid)
            self._log_action("add_ad_descriptions", ad_id, {"ad_group": ad_group_resource, "descriptions": valid}, result.get("status"))
            return {"status": result.get("status", "error"), "action": "add_ad_descriptions", "ad_id": ad_id, "detail": result}
        except Exception as e:
            return {"status": "error", "action": "add_ad_descriptions", "error": str(e)}

    def remove_ad_asset(self, ad_group_resource, ad_id, asset_text, asset_type):
        from engine.ads_client import remove_rsa_asset
        client = self._get_client()
        try:
            result = remove_rsa_asset(client, self.customer_id, ad_group_resource, ad_id, asset_text, asset_type)
            self._log_action("remove_ad_asset", ad_id, {"text": asset_text, "type": asset_type}, result.get("status"))
            return {"status": result.get("status", "error"), "action": "remove_ad_asset", "ad_id": ad_id, "detail": result}
        except Exception as e:
            return {"status": "error", "action": "remove_ad_asset", "error": str(e)}

    def execute_approved(self, actions):
        dispatch = {
            "block_keyword":      lambda a: self.block_keyword(a["campaign_id"], a["keyword"]),
            "update_budget":      lambda a: self.update_budget(a["campaign_id"], a["new_budget_mxn"], a.get("reason", "")),
            "pause_adgroup":      lambda a: self.pause_adgroup(a["campaign_id"], a["adgroup_id"], a.get("reason", "")),
            "add_keyword":        lambda a: self.add_keyword(a["ad_group_resource"], a["keyword_text"], a.get("match_type", "PHRASE"), a.get("cpc_bid_micros")),
            "remove_theme":       lambda a: self.remove_theme(a["criterion_resource_name"]),
            "add_ad_headlines":   lambda a: self.add_ad_headlines(a["ad_group_resource"], a["ad_id"], a["headlines"]),
            "replace_headlines":  lambda a: self.replace_rsa_headlines(a["ad_group_resource"], a["ad_id"], a["headlines"]),
            "add_ad_descriptions": lambda a: self.add_ad_descriptions(a["ad_group_resource"], a["ad_id"], a["descriptions"]),
            "remove_ad_asset":    lambda a: self.remove_ad_asset(a["ad_group_resource"], a["ad_id"], a["asset_text"], a["asset_type"]),
        }
        results = []
        for action in actions:
            t = action.get("type", "")
            handler = dispatch.get(t)
            try:
                result = handler(action) if handler else {"status": "unsupported", "action": t}
            except KeyError as e:
                result = {"status": "error", "action": t, "error": f"Missing param: {e}"}
            except Exception as e:
                result = {"status": "error", "action": t, "error": str(e)}
            results.append(result)
        return results
