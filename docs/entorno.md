# Inventario de Entorno — Fase de Cierre Monitor

> Generado en Fase 0 del cierre `thai-thai-ads-agent` / Thai Thai Monitor.
> Fecha de verificación: 2026-06-10. Modo seguro (read-only, sin mutaciones).

## Repositorio
- **GitHub**: `thaithaimerida-ship-it/thai-thai-ads-agent` (remote `origin`, HTTPS)
- **Windows**: `C:\proyectos\thai-thai\thai-thai-ads-agent`
- **WSL**: `/mnt/c/proyectos/thai-thai/thai-thai-ads-agent`
- **Branch activo**: `fase-f2b-monitor-email-renderer`
  - Cambios sin commitear (se salvan y amplían, NO se descartan):
    - `?? engine/monitor_email_renderer.py` (10,643 B — renderer parcial)
    - `?? tests/test_monitor_email_renderer.py`
    - `M  engine/monitor_digest_v3.py`
- **Branches locales**: `main`, `fase-a-weak-local-action-gate`, `fase-b-negativos-cerebro-v2`, `fase-c-negativos-ui-v2-readonly`, `fase-d-negativos-clasificador-v3-readonly`, `fase-f1-monitor-digest-v3`, `fase-f2b-monitor-email-renderer`, `feature/ai-recommendations-presupuestos`, `sprint-12may-llm-migration`
- **Branch de trabajo nuevo de esta fase** (aún no creado): `fase-f2r-digest-completo-renderer-v2`

## Herramientas — dónde vive cada una

| Herramienta | Versión | Ubicación | Notas |
|---|---|---|---|
| git | 2.53.0.windows.1 | PowerShell | — |
| GitHub CLI (`gh`) | 2.89.0 | PowerShell | Auth ✓ como `thaithaimerida-ship-it`. Scopes: `gist`, `read:org`, `repo`, `workflow` |
| Python (host de tests) | 3.13.3 (py313) | Windows: `C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe` | venv del repo en `env/` (`Scripts\pytest.exe`) |
| pytest | 9.0.2 | Windows / py313 | **NO está en WSL** (ver discrepancia abajo) |
| Python (WSL) | 3.12.3 | WSL `/usr/bin/python3` | Sin pytest ni deps del proyecto |
| **CodeRabbit** | 0.5.4 | **WSL** `/home/hugo/.local/bin/coderabbit` | NO existe en PowerShell |
| **Semgrep** | 1.164.0 | **WSL** | NO en PowerShell |
| **Playwright** | 1.60.0 | **WSL** | Para screenshots de previews del correo |

## Baseline de tests (autoridad: py313 Windows)
```
1039 tests colectados
1038 passed, 1 skipped, 8 warnings  —  51.90s
```
Warnings = solo `DeprecationWarning` preexistentes (`on_event` de FastAPI, `datetime.utcnow()`). Suite **VERDE** como baseline.

Comando usado:
```powershell
$env:PYTHONPATH="C:\proyectos\thai-thai\thai-thai-ads-agent"; $env:PYTHONIOENCODING="utf-8"
& 'C:\Users\usuario\AppData\Local\Programs\Python\Python313\python.exe' -m pytest -q
```

## ⚠️ Discrepancia importante con el brief
El brief asume que **pytest corre en WSL**. La realidad verificada: **pytest NO está instalado en el python de WSL** (3.12.3) — las dependencias del proyecto y pytest 9.0.2 viven en el **venv de Windows (`env/`, py313)**. La suite ya pasa verde ahí.

- **CodeRabbit, Semgrep y Playwright** sí son genuinamente de **WSL** (confirmado).
- **pytest** se corre en **Windows / py313**.

**Recomendación**: mantener pytest en Windows/py313 (deps ya instaladas, baseline verde) y usar WSL solo para CodeRabbit/Semgrep/Playwright. Alternativa (si Hugo lo prefiere): instalar `requirements.txt` + pytest en WSL — más trabajo, sin beneficio claro. **Pendiente de decisión de Hugo.**

## MCP servers
- **Repo-local** (`.mcp.json`): `supabase` (modo `--read-only`, project-ref `oghtjvvasdhbjbuemhks`, token vía `SUPABASE_ACCESS_TOKEN`).
- **Sesión Claude Code** (conectados): `context7`, `nanobanana`, `claude_ai` (Facebook Ads, Gmail, Google Calendar, Google Drive), `21st-magic`, `plugin_wix`.

## Skills disponibles
- **Repo-local** (`.claude/skills/`): `ads-api-v23`, `ads-mutation-dry-run`, `ai-prompt-iterate`, `cloudrun-deploy-verify`.
- **Globales** (extracto relevante): `superpowers:*` (brainstorming, TDD, debugging, plans, worktrees, code-review), familia `ads-*` (audit, google, meta, etc.), `seo-audit`, `coderabbit:code-review`, `code-review`, `verify`, `schedule`, `loop`.

## Producción (referencia, NO se toca en esta fase)
- Cloud Run: `thai-thai-ads-agent` · `us-central1` · URL `https://thai-thai-ads-agent-624172071613.us-central1.run.app`
- `GET /monitor/digest` existe en prod (read-only, ≤5 decisiones, separa dinero de señales).
- PR #5 en curso (digest incompleto — esta fase lo completa).
