"""
Thai Thai Ads Agent — Sub-agents package.
Lazy imports to prevent cascading failures.
"""


def __getattr__(name):
    if name == "Auditor":
        from agents.auditor import Auditor
        return Auditor
    if name == "Strategist":
        from agents.strategist import Strategist
        return Strategist
    if name == "Executor":
        from agents.executor import Executor
        return Executor
    if name == "Reporter":
        from agents.reporter import Reporter
        return Reporter
    if name == "Builder":
        from agents.builder import Builder
        return Builder
    raise AttributeError(f"module 'agents' has no attribute {name!r}")
