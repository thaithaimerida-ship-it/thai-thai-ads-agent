"""Generación de borradores de respuesta a reseñas 5★ (Fase G).

REUTILIZA el cliente LLM existente del backend (engine.llm_client.generate_text) —
UN solo punto de integración, sin duplicar cliente. El modelo concreto lo decide
llm_client por rol ("haiku"). La voz vive en data/voz_resenas.md.

Solo genera texto on-demand; NO publica nada (eso lo hace el endpoint con DRY_RUN).
"""
from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from typing import Any

from engine import llm_client

VOZ_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "voz_resenas.md")
MODEL_ROLE = "haiku"  # textos de 2 frases; el modelo grande queda para reportes
# Paleta de emojis de apertura: se asigna uno DISTINTO por borrador en la tanda
# (enforcement determinista — el modelo solo con prompt repite su favorito).
EMOJIS_APERTURA = ["😄", "🙌", "🥳", "😊", "⭐", "🤩", "😍", "🎉"]

# Rango de emojis (pictográficos) para contar y acotar a 3.
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U00002B00-\U00002BFF\U00002300-\U000023FF"
    "\U0001F1E6-\U0001F1FF✨❤⁉‼™]"
)
# Modificadores que NO cuentan como emoji propio: selector de variación, tonos de piel, ZWJ.
_EMOJI_MOD_RE = re.compile("[\U0000FE0F\U0001F3FB-\U0001F3FF\U0000200D]")

# Ángulos de apertura distintos por borrador (el modelo repite "¡Qué bonito leer!"
# si solo se le prohíbe por prompt — aquí se le asigna un arranque distinto a cada uno).
APERTURAS_ANGULO = [
    "Abre celebrando lo que más le gustó, usando SU palabra exacta.",
    "Abre con un '¡Nos hiciste el día!' (o equivalente con otras palabras).",
    "Abre agradeciéndole directo por tomarse el tiempo de escribir.",
    "Abre con sorpresa alegre por su comentario ('¡No puede ser qué linda reseña!' u otra).",
    "Abre con una exclamación cálida y alegre por su visita.",
    "Abre con orgullo de lo que hacen ('¡Esto nos llena de orgullo!').",
    "Abre nombrándolo y celebrando su visita.",
    "Abre con un guiño juguetón a lo que vivió.",
]

# Ángulos de cierre distintos por borrador (enforcement determinista — el modelo
# repite "ojalá nos visites otra vez muy pronto" si solo se le prohíbe por prompt).
CIERRES_ANGULO = [
    "Cierra invitándolo a volver pronto, con tus propias palabras (tuteo).",
    "Cierra sugiriéndole probar un platillo específico la próxima (arroz con mango, pad thai, curry…).",
    "Cierra agradeciéndole de corazón por tomarse el tiempo de escribir.",
    "Cierra afirmando en firme que aquí lo recibes con gusto la próxima.",
    "Cierra con un deseo cálido y breve, SIN usar frases tipo 'vuelve pronto' ni 'visítanos otra vez'.",
    "Cierra dándole la bienvenida a la familia Thai Thai.",
    "Cierra diciéndole que ya sabe dónde encontrarte para la próxima.",
    "Cierra con un agradecimiento corto y un guiño a que repita la experiencia.",
]

# ── Espejo de energía ─────────────────────────────────────────────────────────
# El generador clasifica la reseña en una energía y responde EN ESE CANAL.
_ENERGIA_KW = {
    "explosiva": ["sabor", "sabores", "picante", "picoso", "picosito", "delicioso", "deliciosa",
                  "rico", "rica", "riquisimo", "riquisima", "sabroso", "sabrosa", "exquisito",
                  "exquisita", "intenso", "fuego", "explosion", "manjar", "espectacular", "buenisima",
                  "buenisimo", "autentico", "autenticos", "platillo", "curry", "pad", "thai"],
    "zen": ["ambiente", "atencion", "atento", "atenta", "atentos", "trato", "servicio", "amable",
            "amables", "comodo", "comoda", "tranquilo", "tranquila", "acogedor", "personal", "lugar",
            "agradable", "limpio", "bonito", "bonita", "decoracion", "hospitalidad", "calido", "calida",
            "relajado", "experiencia"],
    "vibrante": ["rapido", "rapida", "rapidos", "rapidez", "rapidisimo", "antojo", "casual", "practico",
                 "facil", "domicilio", "pedido", "agil", "express", "puntual", "entrega", "fueron"],
}
ENERGIA_CANAL = {
    "explosiva": "Esta reseña elogia el SABOR / picante / intensidad. Responde con CHISPA y fuego verbal, con energía, retomando el sabor o el platillo que mencionó.",
    "zen": "Esta reseña elogia el AMBIENTE / atención / tranquilidad. Responde CÁLIDO y sereno, agradeciendo ese detalle del lugar o el servicio.",
    "vibrante": "Esta reseña elogia la RAPIDEZ / lo casual / el antojo. Responde con RITMO, juguetón y ágil.",
    "agradecimiento": "Reseña sin texto o muy breve. Da una gratitud GENUINA y CORTA (1-2 frases), sin inventar detalles que no mencionó.",
}
ENERGIA_EMOJIS = {
    "explosiva": ["🔥", "🌶️", "😍", "🤩"],
    "zen": ["😊", "🙌", "💛", "🌿"],
    "vibrante": ["😄", "⚡", "🥭", "🙌"],
    "agradecimiento": ["⭐", "🥳", "😊", "🙌"],
}


def sin_texto(resena: dict[str, Any]) -> bool:
    """True si la reseña es solo estrellas (sin comentario) → va al banco, no se genera."""
    return not (resena.get("comment") or resena.get("comentario") or "").strip()


def clasificar_energia(resena: dict[str, Any]) -> str:
    """Energía de la reseña. SIN texto → 'agradecimiento' (banco). CON texto → explosiva /
    zen / vibrante (nunca agradecimiento; default zen)."""
    if sin_texto(resena):
        return "agradecimiento"
    palabras = _palabras(resena.get("comment") or resena.get("comentario") or "")
    scores = {k: sum(1 for w in palabras if w in kws) for k, kws in _ENERGIA_KW.items()}
    mejor = max(scores, key=scores.get)
    return mejor if scores[mejor] > 0 else "zen"


# Afinidad energía → grupo del pool de cierres (el selector puede cruzar si hace falta).
_ENERGIA_GRUPO = {"explosiva": "antojo", "vibrante": "antojo", "zen": "calido", "agradecimiento": "elegante"}


def seleccionar_cierre(energia: str, pool: dict[str, list[str]],
                       usados: set[str], recientes: list[str] | None = None) -> tuple[str, str]:
    """Elige un cierre del grupo afín (cruza si hace falta), sin repetir en el lote ni en las
    últimas publicaciones. Devuelve (cierre, grupo)."""
    recientes = [_norm(r) for r in (recientes or [])]
    afin = _ENERGIA_GRUPO.get(energia, "calido")
    orden = [afin] + [g for g in pool if g != afin]
    for evita_recientes in (True, False):       # primero respeta historial; si agota, relaja
        for g in orden:
            for c in pool.get(g, []):
                if c in usados:
                    continue
                if evita_recientes and any(_norm(c) in r for r in recientes):
                    continue
                return c, g
    # último recurso: el primero del grupo afín
    g0 = afin if pool.get(afin) else (next(iter(pool)) if pool else "")
    return (pool.get(g0, [""]) or [""])[0], g0


def seleccionar_cierre_idx(energia: str, pool: dict[str, list[str]], indice: int,
                           recientes: list[str] | None = None) -> tuple[str, str]:
    """Cierre determinista POR ÍNDICE (para generación per-card, sin estado cruzado): toma del
    grupo afín a la energía, evitando los usados en publicaciones recientes."""
    recientes_n = [_norm(r) for r in (recientes or [])]
    afin = _ENERGIA_GRUPO.get(energia, "calido")
    grupo = pool.get(afin) or (next(iter(pool.values())) if pool else [""])
    candidatos = [c for c in grupo if not any(_norm(c) in r for r in recientes_n)] or grupo
    return candidatos[indice % len(candidatos)], afin


def seleccionar_banco(banco: list[str], usados: set[str], recientes: list[str] | None = None) -> str:
    """Elige una respuesta del banco (verbatim), sin repetir en el lote ni en las últimas
    publicaciones."""
    recientes = [_norm(r) for r in (recientes or [])]
    for evita_recientes in (True, False):
        for b in banco:
            if b in usados:
                continue
            if evita_recientes and any(_norm(b) in r for r in recientes):
                continue
            return b
    return banco[0] if banco else ""


def _hash_idx(clave: str, n: int) -> int:
    """Hash ESTABLE (sha256, no el hash() de Python que es aleatorio por proceso) → [0, n)."""
    if n <= 0:
        return 0
    return int(hashlib.sha256((clave or "").encode("utf-8")).hexdigest(), 16) % n


def seleccionar_banco_por_review(banco: list[str], review_id: str, recientes: list[str] | None = None) -> str:
    """Banco verbatim ROTADO determinísticamente por review_id (per-card, sin contexto del lote):
    índice base = hash(review_id) % N; si esa respuesta está en las últimas publicaciones reales,
    avanza al siguiente índice libre. La MISMA reseña siempre da la MISMA respuesta (estable,
    independiente del orden de carga y del caché)."""
    if not banco:
        return ""
    n = len(banco)
    recientes_n = {_norm(r) for r in (recientes or [])}
    base = _hash_idx(review_id, n)
    for off in range(n):
        cand = banco[(base + off) % n]
        if _norm(cand) not in recientes_n:
            return cand
    return banco[base]  # todas en recientes (improbable: banco=15 vs últimas 10)


def contar_emojis(texto: str) -> int:
    # Descuenta selector de variación, tonos de piel y ZWJ (no son emoji propio).
    return len(_EMOJI_RE.findall(_EMOJI_MOD_RE.sub("", texto or "")))


_EMOJI_SEQ_RE = re.compile(_EMOJI_RE.pattern + "[\U0000FE0F\U0001F3FB-\U0001F3FF\U0000200D]*")


def limitar_emojis(texto: str, maximo: int = 3) -> str:
    """Recorta emojis sobrantes (deja los primeros `maximo`) — hard cap de la regla."""
    n = 0

    def _repl(m):
        nonlocal n
        n += 1
        return m.group(0) if n <= maximo else ""

    return _EMOJI_SEQ_RE.sub(_repl, texto or "")


# V2 — paleta de emojis UNIVERSALES aprobada (voz + banco). Cualquier emoji fuera de aquí
# (o un tono de piel) se prohíbe y se limpia, aunque la reseña del cliente lo traiga.
ALLOWED_EMOJIS = set("😄🙌🥳😊⭐🤩😍🎉🔥🌶💛🌿⚡🥭✨🙏🍛🌟🍜🥰👋🥢🥘")
_SKIN_RE = re.compile("[\U0001F3FB-\U0001F3FF]")


def emoji_no_aprobado(texto: str) -> bool:
    if _SKIN_RE.search(texto or ""):
        return True
    limpio = _EMOJI_MOD_RE.sub("", texto or "")
    return any(e not in ALLOWED_EMOJIS for e in _EMOJI_RE.findall(limpio))


def limpiar_emojis_no_aprobados(texto: str) -> str:
    """Quita modificadores de piel/variación y cualquier emoji fuera de la paleta (backstop)."""
    limpio = _EMOJI_MOD_RE.sub("", texto or "")
    return _EMOJI_RE.sub(lambda m: m.group(0) if m.group(0) in ALLOWED_EMOJIS else "", limpio)


# V1 — la voz firma SIEMPRE en plural (nosotros). Prohibida la primera persona singular.
_SINGULAR_RE = re.compile(r"\b(yo|mi|mia|mias|mio|mios|me|conmigo)\b")


def voz_singular(texto: str) -> bool:
    return bool(_SINGULAR_RE.search(_norm(texto)))


def _palabras(texto: str) -> list[str]:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = _EMOJI_RE.sub(" ", t)
    return re.findall(r"[a-z0-9]+", t)


def apertura(texto: str, n: int = 3) -> str:
    """Primeras n palabras normalizadas (para detectar aperturas repetidas)."""
    return " ".join(_palabras(texto)[:n])


def cierre(texto: str, n: int = 3) -> str:
    """Últimas n palabras normalizadas (para detectar cierres repetidos)."""
    return " ".join(_palabras(texto)[-n:])


def apertura_emoji(texto: str) -> str:
    """Primer emoji del texto (para no repetir emoji de apertura en la tanda)."""
    m = _EMOJI_RE.search(texto or "")
    return m.group(0) if m else ""


def cierre_nucleo(texto: str, n: int = 4) -> str:
    """Frase núcleo del cierre = últimas n palabras normalizadas (para detectar
    cierres que comparten la misma idea: 'aqui te esperamos', 'cuando se te antoje')."""
    return " ".join(_palabras(texto)[-n:])


def _norm(texto: str) -> str:
    """minúsculas sin acentos (para guardas léxicas)."""
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


# C1 — raíces de cierre: dos cierres no pueden compartir la idea (antoj-, esper-…).
_RAICES_CIERRE = ("antoj", "esper", "regres", "vuelv", "visit", "recib")


def raices_cierre(texto: str) -> set[str]:
    cola = _palabras(texto)[-8:]
    return {r for r in _RAICES_CIERRE for w in cola if w.startswith(r)}


# C2 — prohibido dirigir cariño/abrazos/saludos a la cocina o al equipo propio.
_CARINO_RE = re.compile(r"(carin|abraz|saludo|beso|aplauso)\w*")
_EQUIPO_RE = re.compile(r"\b(cocina|cociner\w*|equipo|chef|personal|meser\w*|staff)\b")


def viola_carino_equipo(texto: str) -> bool:
    t = _norm(texto)
    for m in _CARINO_RE.finditer(t):
        if _EQUIPO_RE.search(t[m.start():m.start() + 45]):
            return True
    return False


# C3 — consistencia de persona: tú O usted, jamás mezcla. Default tuteo.
_USTED = ("usted", "lo espera", "la espera", "le espera", "se le antoj", "su mesa lo",
          "su mesa la", "consentirlo", "consentirla", "recibirlo", "recibirla",
          "atenderlo", "atenderla", "lo recibimos", "la recibimos", "verlo de nuevo", "verla de nuevo")
_TU = ("se te antoj", "tu mesa te", "vente", "lanzate", "anímate", "animate", "contigo", "tuteo")
_TU_RE = re.compile(r"\b(te|ti|tu|tus)\b|\b\w+(aste|iste)\b")


def persona_mezclada(texto: str) -> bool:
    t = _norm(texto)
    usa_usted = any(p in t for p in _USTED)
    usa_tu = any(p in t for p in _TU) or bool(_TU_RE.search(t))
    return usa_usted and usa_tu


# C4 — "bienvenido/a" solo si la reseña indica primera visita.
_PRIMERA_VISITA_RE = re.compile(
    r"primera vez|primera visita|por primera|mi primera|nuestra primera|"
    r"estren|conoci|conocimos|descubri|primer\w* vez|nuevo client|al fin vin")


def indica_primera_visita(resena: dict[str, Any]) -> bool:
    return bool(_PRIMERA_VISITA_RE.search(_norm(resena.get("comment") or resena.get("comentario") or "")))


def bienvenida_indebida(texto: str, resena: dict[str, Any]) -> bool:
    return "bienvenid" in _norm(texto) and not indica_primera_visita(resena)


# C5 — concordancia de género TOTAL: adjetivos/participios dirigidos al cliente.
_NOMBRES_F = {"roselyn", "wendy", "iliana", "maria", "ana", "sofia", "lucia", "fernanda",
              "karla", "paola", "andrea", "gabriela", "laura", "diana", "valeria", "alejandra"}
_NOMBRES_M = {"fabian", "gilmer", "david", "cesar", "juan", "carlos", "luis", "jose", "miguel",
              "jorge", "alejandro", "ricardo", "roberto", "eduardo", "fernando", "pedro"}
_NOMBRES_AMB = {"karol", "guadalupe", "alexis", "cruz", "trinidad", "rene", "noa", "ariel", "guille"}
_ADJ_GEN_STEMS = ["comod", "content", "satisfech", "encantad", "bienvenid", "agradecid",
                  "consentid", "complacid", "emocionad", "fascinad", "sorprendid", "mimad",
                  "atendid", "recibid", "acompañad", "tranquil", "acogid"]


def inferir_genero(nombre: str) -> str:
    """'f' / 'm' / 'ambiguo' a partir del nombre (default seguro = ambiguo → neutro)."""
    pals = _palabras(nombre or "")
    first = pals[0] if pals else ""
    if not first or first in _NOMBRES_AMB:
        return "ambiguo"
    if first in _NOMBRES_F:
        return "f"
    if first in _NOMBRES_M:
        return "m"
    if first.endswith("a"):
        return "f"
    if first.endswith("o"):
        return "m"
    return "ambiguo"


def _adjetivos_con_genero(texto: str) -> list[tuple[str, str]]:
    out = []
    for w in _palabras(texto):
        for s in _ADJ_GEN_STEMS:
            if w in (s + "o", s + "os"):
                out.append((w, "m"))
            elif w in (s + "a", s + "as"):
                out.append((w, "f"))
    return out


def genero_incorrecto(texto: str, resena: dict[str, Any]) -> bool:
    adjs = _adjetivos_con_genero(texto)
    if not adjs:
        return False
    g = inferir_genero(resena.get("reviewer") or "")
    if g == "ambiguo":
        return True  # nombre ambiguo + adjetivo con género → obligatorio neutro
    return any(ag != g for _, ag in adjs)


# C6 — la invitación a volver va en afirmativo; prohibido lo tentativo en el cierre.
_TENTATIVO_RE = re.compile(r"\bojala\b|ojala que|esperemos que|\bquiza\b|\bquizas\b|a ver si|\btal vez\b")


def cierre_no_afirmativo(texto: str) -> bool:
    return bool(_TENTATIVO_RE.search(_norm(texto)))


# C8 — no repetir una frase significativa dentro de la misma respuesta.
def _shingles(texto: str, n: int = 4) -> set[tuple[str, ...]]:
    pals = _palabras(texto)
    return {tuple(pals[i:i + n]) for i in range(len(pals) - n + 1)}


def frase_repetida_interna(texto: str, n: int = 4) -> bool:
    pals = _palabras(texto)
    vistos = set()
    for i in range(len(pals) - n + 1):
        sh = tuple(pals[i:i + n])
        if sh in vistos:
            return True
        vistos.add(sh)
    return False


# C10 — agencia: no atribuir al cliente acciones del restaurante ("la comida te salió deliciosa").
_AGENCIA_RE = re.compile(r"\bte (sali[oó]|salieron|qued[oó]|quedaron|cocin\w+|prepar\w+|sazon\w+|hiciste la comida)\b")


def viola_agencia(texto: str) -> bool:
    return bool(_AGENCIA_RE.search(_norm(texto)))


# El cuerpo NO invita a volver (la invitación es trabajo del cierre del pool).
_INVITA_RE = re.compile(
    r"\b(vuelv\w*|regres\w*|te esperam\w*|los esperam\w*|aqui te esper\w*|nos vemos|tu mesa|"
    r"proxima visita|de vuelta|otra visita|visitanos|esperamos vert|vente|lanzate|"
    r"te esperamos|cuando gustes|la proxima)\b")


def cuerpo_invita(texto: str) -> bool:
    return bool(_INVITA_RE.search(_norm(texto)))


# Backstop léxico determinista de frases artificiales conocidas (complementa al juez C7,
# que es probabilístico). El dueño puede ampliar esta lista.
_FRASES_ARTIFICIALES = ("asi da gusto", "comida agil", "deleitar tu paladar", "experiencia culinaria",
                        "sabor de golpe", "viaje culinario", "explosion de sabor en cada bocado")


def tiene_frase_artificial(texto: str) -> bool:
    t = _norm(texto)
    return any(f in t for f in _FRASES_ARTIFICIALES)


def violaciones_contenido(texto: str, resena: dict[str, Any]) -> list[str]:
    """Guardas léxicas C2-C6 — lista de reglas violadas (vacía = limpio)."""
    v = []
    if viola_carino_equipo(texto):
        v.append("carino_a_equipo")
    if persona_mezclada(texto):
        v.append("mezcla_persona")
    if bienvenida_indebida(texto, resena):
        v.append("bienvenida_indebida")
    if genero_incorrecto(texto, resena):
        v.append("genero_incorrecto")
    if cierre_no_afirmativo(texto):
        v.append("cierre_no_afirmativo")
    if frase_repetida_interna(texto):
        v.append("frase_repetida_interna")
    if viola_agencia(texto):
        v.append("agencia_incorrecta")
    if tiene_frase_artificial(texto):
        v.append("frase_artificial")
    if voz_singular(texto):
        v.append("voz_singular")
    if emoji_no_aprobado(texto):
        v.append("emoji_no_aprobado")
    return v


_NAT_SYS = (
    "Eres un mesero veterano y franco. Revisas respuestas a reseñas y eres INDULGENTE: el "
    "lenguaje cálido, coloquial y mexicano PASA. Solo marcas algo como artificial si suena a "
    "robot, a folleto publicitario o a traducción rara.\n"
    "PASAN (natural): 'Tu mesa te espera', 'Te esperamos pronto', 'Gracias de corazón', "
    "'Nos hiciste el día', 'Vente por un pad thai', 'Qué gusto que la pasaras bien'.\n"
    "NO PASAN (artificial): 'así da gusto recibirte', 'comida ágil', 'deleitar tu paladar', "
    "'experiencia culinaria', 'sabor de golpe', frases acartonadas o de marketing.")


def evaluar_naturalidad(texto: str) -> tuple[bool, str]:
    """C7 — segundo pase: ¿suena humano? Devuelve (natural, frase_artificial)."""
    prompt = ("Revisa esta respuesta:\n\n\"" + texto + "\"\n\n"
              "Dos preguntas: (1) ¿suena natural y humano? (2) ¿alguna frase atribuye a la persona "
              "equivocada la acción (p. ej. 'la comida te salió deliciosa' — el cliente no cocinó)?\n"
              "Si todo suena natural y la agencia es correcta, responde solo 'NATURAL'. Si hay una frase "
              "robótica, de folleto, forzada o con agencia equivocada, responde 'ARTIFICIAL: <esa frase>'. "
              "Ante la duda en naturalidad, es NATURAL; pero los errores de agencia SIEMPRE se marcan.")
    r = (llm_client.generate_text(model_role=MODEL_ROLE, user_prompt=prompt,
                                  system_prompt=_NAT_SYS, max_tokens=60) or "").strip()
    natural = _norm(r).startswith("natural")
    return natural, ("" if natural else r)


def validar_variedad(borradores: list[str]) -> list[str]:
    """Devuelve la lista de colisiones (vacía = variedad OK). Compara aperturas,
    cierres, emoji de apertura, núcleo de cierre y RAÍZ de cierre (C1)."""
    colisiones = []
    for clave, fn in (("apertura", apertura), ("cierre", cierre),
                      ("emoji_apertura", apertura_emoji), ("nucleo_cierre", cierre_nucleo)):
        vistos = {}
        for i, b in enumerate(borradores):
            v = fn(b)
            if not v:
                continue
            if v in vistos:
                colisiones.append(f"{clave} repetido entre #{vistos[v] + 1} y #{i + 1}: {v!r}")
            else:
                vistos[v] = i
    # C1 — raíz de cierre compartida (antoje/antojo, esperamos/espera…).
    raices = [raices_cierre(b) for b in borradores]
    for i in range(len(borradores)):
        for j in range(i):
            comun = raices[i] & raices[j]
            if comun:
                colisiones.append(f"raiz_cierre repetida entre #{j + 1} y #{i + 1}: {sorted(comun)}")
    # C9 — ninguna frase de 4 palabras se repite entre borradores del lote
    # (incluidos 1 y 2): caza "tu mesa te espera" aparezca donde aparezca.
    shings = [_shingles(b, 4) for b in borradores]
    for i in range(len(borradores)):
        for j in range(i):
            comun = shings[i] & shings[j]
            if comun:
                frase = " ".join(sorted(comun)[0])
                colisiones.append(f"frase repetida en el lote entre #{j + 1} y #{i + 1}: {frase!r}")
    return colisiones


def _voz_full(path: str = VOZ_PATH) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_voz(path: str = VOZ_PATH) -> str:
    """Solo las reglas de voz (hasta el Pool): el pool y el banco NO se le muestran al
    generador (serían imanes); el sistema los parsea aparte."""
    full = _voz_full(path)
    idx = full.find("## Pool de cierres")
    return full[:idx].rstrip() if idx != -1 else full


def _seccion(full: str, titulo: str) -> str:
    ini = full.find(titulo)
    if ini == -1:
        return ""
    resto = full[ini + len(titulo):]
    sig = resto.find("\n## ")
    return resto[:sig] if sig != -1 else resto


def cargar_pool_cierres(path: str = VOZ_PATH) -> dict[str, list[str]]:
    """Parsea el Pool de cierres de voz_resenas.md → {grupo: [cierres]}."""
    seg = _seccion(_voz_full(path), "## Pool de cierres")
    pool: dict[str, list[str]] = {}
    grupo = None
    for linea in seg.splitlines():
        s = linea.strip()
        if s.startswith("### "):
            grupo = _norm(s[4:].strip())
            pool[grupo] = []
        elif s.startswith("- ") and grupo:
            pool[grupo].append(s[2:].strip().strip('"'))
    return pool


def cargar_banco_sin_texto(path: str = VOZ_PATH) -> list[str]:
    """Parsea el Banco 5★ sin texto → [15 respuestas verbatim]."""
    seg = _seccion(_voz_full(path), "## Banco 5★ sin texto")
    out = []
    for linea in seg.splitlines():
        m = re.match(r"\s*\d+\.\s+(.*\S)\s*$", linea)
        if m:
            out.append(m.group(1).strip())
    return out


def _build_user_prompt(resena: dict[str, Any], respuestas_previas: list[str],
                       emoji_objetivo: str = "", energia: str = "",
                       apertura_angulo: str = "", genero: str = "", extra: str = "") -> str:
    estrellas = int(resena.get("stars") or resena.get("estrellas") or 5)
    comentario = (resena.get("comment") or resena.get("comentario") or "").strip()
    reviewer = (resena.get("reviewer") or "").strip()

    aperturas = sorted({apertura(r) for r in respuestas_previas if r.strip()})
    cierres = sorted({cierre(r) for r in respuestas_previas if r.strip()})
    emojis_ap = sorted({apertura_emoji(r) for r in respuestas_previas if apertura_emoji(r)})
    nucleos = sorted({cierre_nucleo(r) for r in respuestas_previas if r.strip()})

    partes = [f"Reseña de {estrellas}★" + (f" de {reviewer}" if reviewer else "") + ":"]
    partes.append(f"\"{comentario}\"" if comentario else "(sin texto, solo calificación)")
    if energia and energia in ENERGIA_CANAL:
        partes.append("\nESPEJO DE ENERGÍA — " + ENERGIA_CANAL[energia])
    if aperturas:
        partes.append("\nNO repitas estas aperturas (ya usadas): " + "; ".join(aperturas))
    if emojis_ap:
        partes.append("NO uses como PRIMER emoji ninguno de estos (ya usados): " + " ".join(emojis_ap))
    if cierres:
        partes.append("NO repitas estos cierres (ya usados): " + "; ".join(cierres))
    if nucleos:
        partes.append("NO repitas estas frases de cierre (ya usadas): " + "; ".join(nucleos))
    raices_prev = sorted({r for prev in respuestas_previas for r in raices_cierre(prev)})
    if raices_prev:
        partes.append("NO cierres con palabras de estas raíces (ya usadas): " + ", ".join(f"{r}-" for r in raices_prev))
    if emoji_objetivo:
        partes.append(f"Usa EXACTAMENTE {emoji_objetivo} como tu PRIMER emoji (puedes sumar 1-2 más distintos después).")
    if apertura_angulo:
        partes.append(apertura_angulo)
    # El cuerpo NO invita a volver (el sistema añade el cierre).
    partes.append("Escribe SOLO el saludo y el cuerpo (agradecimiento + lo específico). NO invites a "
                  "volver ni te despidas; NO uses 'vuelve', 'te esperamos', 'tu mesa', 'la próxima'. Eso lo añade el sistema.")
    # Guardas permanentes (C2-C6, C10).
    partes.append("Usa SIEMPRE tuteo (tú / te / tu) en TODA la respuesta; nunca usted ni mezcles.")
    partes.append("NO mandes saludos, abrazos ni cariño a la cocina, al chef ni al equipo: el cariño es para quien escribió.")
    partes.append("No atribuyas al cliente acciones del restaurante: él no cocinó. Di 'la comida estuvo deliciosa', "
                  "no 'la comida te salió deliciosa'.")
    partes.append("Firma SIEMPRE en PLURAL (nosotros): 'nuestra atención', 'nos encantó', 'te esperamos'. PROHIBIDA la "
                  "primera persona singular (yo / mí / me / mía). Puedes nombrar al equipo (ej. Alejandro), pero la voz es del restaurante en plural.")
    partes.append("Usa SOLO emojis de la paleta aprobada (😄🙌⭐🥳😊🥭🔥🌶️ y los del banco). NUNCA copies emojis de la reseña del cliente ni uses tonos de piel.")
    if genero == "f":
        partes.append("Concuerda en FEMENINO los adjetivos dirigidos a la clienta (contenta, cómoda…).")
    elif genero == "m":
        partes.append("Concuerda en MASCULINO los adjetivos dirigidos al cliente (contento, cómodo…).")
    else:
        partes.append("El nombre NO permite inferir género: redacta en NEUTRO, SIN adjetivos con género "
                      "(en vez de 'cómodo/a' usa 'a gusto'; en vez de 'contento/a' usa 'que la pasaras bien').")
    if indica_primera_visita(resena):
        partes.append("Es su PRIMERA visita: puedes darle la bienvenida (género concordado o forma neutra).")
    else:
        partes.append("NO uses 'bienvenido/a' (la reseña no indica primera visita).")
    if extra:
        partes.append(extra)
    partes.append("\nEscribe la respuesta del dueño a esta reseña, siguiendo la voz. Solo el texto.")
    return "\n".join(partes)


def generar_cuerpo(resena: dict[str, Any], respuestas_previas: list[str] | None = None,
                   emoji_objetivo: str = "", energia: str = "",
                   apertura_angulo: str = "", genero: str = "", extra: str = "") -> str:
    """Genera el SALUDO + CUERPO de una reseña (sin invitación a volver: el cierre lo añade
    el sistema), en el canal de energía dado y evitando aperturas ya usadas."""
    respuestas_previas = list(respuestas_previas or [])
    system = load_voz()
    user = _build_user_prompt(resena, respuestas_previas, emoji_objetivo, energia,
                              apertura_angulo, genero, extra)
    draft = llm_client.generate_text(model_role=MODEL_ROLE, user_prompt=user, system_prompt=system, max_tokens=160)
    draft = " ".join((draft or "").split()).strip('"').strip()  # normaliza espacios/saltos
    draft = limpiar_emojis_no_aprobados(draft)                  # V2: solo paleta aprobada, sin tonos de piel
    return " ".join(limitar_emojis(draft, 3).split())           # hard cap 3 emojis + re-normaliza


def generar_borradores(
    resenas: list[dict[str, Any]],
    respuestas_previas: list[str] | None = None,
    max_reintentos: int = 4,
    iniciales: list[dict[str, Any]] | None = None,
    cierres_recientes: list[str] | None = None,
    banco_recientes: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Genera un borrador por reseña con ESPEJO DE ENERGÍA + variedad + guardas de contenido.
    Devuelve [{energia, borrador, emoji_apertura}, ...]. Cada borrador no comparte apertura,
    cierre, emoji de apertura, núcleo ni raíz de cierre con los anteriores de la tanda ni con
    las respuestas publicadas, y no viola las guardas C2/C3/C4. `iniciales` pre-siembra
    borradores ya aceptados (para regenerar solo algunos índices)."""
    pool = cargar_pool_cierres()
    banco = cargar_banco_sin_texto()
    base = list(respuestas_previas or [])
    out: list[dict[str, Any]] = list(iniciales or [])
    usados_emoji: set[str] = {x["emoji_apertura"] for x in out if x.get("emoji_apertura")}
    cierres_usados: set[str] = {x["cierre"] for x in out if x.get("cierre")}
    banco_usados: set[str] = {x["borrador"] for x in out if x.get("fuente") == "banco"}
    for i, r in enumerate(resenas):
        if i < len(out):  # ya generado (fijo)
            continue

        # Reseña SIN texto → banco verbatim, sin IA.
        if sin_texto(r):
            sel = seleccionar_banco(banco, banco_usados, banco_recientes)
            banco_usados.add(sel)
            out.append({"energia": "agradecimiento", "borrador": sel, "cuerpo": "", "cierre": "",
                        "grupo_cierre": "", "emoji_apertura": apertura_emoji(sel), "fuente": "banco",
                        "revisar_manual": False, "motivo_revision": ""})
            continue

        # Reseña CON texto → generador (cuerpo) + cierre del pool.
        energia = clasificar_energia(r)
        paleta = ENERGIA_EMOJIS.get(energia, EMOJIS_APERTURA)
        emoji_obj = next((e for e in paleta if e not in usados_emoji), paleta[i % len(paleta)])
        usados_emoji.add(emoji_obj)
        apertura_ang = APERTURAS_ANGULO[i % len(APERTURAS_ANGULO)]
        genero = inferir_genero(r.get("reviewer") or "")
        cierre_sel, grupo = seleccionar_cierre(energia, pool, cierres_usados, cierres_recientes)
        cierres_usados.add(cierre_sel)
        previos = base + [x["borrador"] for x in out]
        cuerpos_prev = [(x.get("cuerpo") or x["borrador"]) for x in out if x.get("fuente") != "banco"]

        def _ensamblar(cuerpo: str) -> str:
            return (cuerpo + " " + cierre_sel).strip()

        def _malo(cuerpo: str) -> bool:
            return bool(cuerpo_invita(cuerpo)
                        or violaciones_contenido(_ensamblar(cuerpo), r)
                        or validar_variedad(cuerpos_prev + [cuerpo]))

        def _gen(extra: str = "") -> str:
            c = generar_cuerpo(r, previos, emoji_obj, energia, apertura_ang, genero, extra)
            n = 0
            while _malo(c) and n < max_reintentos:
                c = generar_cuerpo(r, previos + [c], emoji_obj, energia, apertura_ang, genero, extra)
                n += 1
            return c

        cuerpo = _gen()
        full = _ensamblar(cuerpo)
        natural, motivo = evaluar_naturalidad(full)  # C7 sobre el texto final (cuerpo + cierre)
        nat_try = 0
        while not natural and nat_try < 2:
            cuerpo = _gen(extra=f"NO uses frases que suenen artificiales o de marketing como: {motivo}")
            full = _ensamblar(cuerpo)
            natural, motivo = evaluar_naturalidad(full)
            nat_try += 1
        out.append({"energia": energia, "borrador": full, "cuerpo": cuerpo, "cierre": cierre_sel,
                    "grupo_cierre": grupo, "emoji_apertura": apertura_emoji(full), "fuente": "generado",
                    "revisar_manual": not natural, "motivo_revision": "" if natural else motivo})
    return out


def generar_uno(resena: dict[str, Any], indice: int = 0, respuestas_previas: list[str] | None = None,
                cierres_recientes: list[str] | None = None, banco_recientes: list[str] | None = None,
                max_reintentos: int = 2) -> dict[str, Any]:
    """Genera UN borrador independiente (per-card): variedad por ÍNDICE (paleta/ángulos/cierre),
    sin acumular estado de otros borradores (prompts pequeños → sin 431). Reintentos acotados
    para responder rápido; el front tiene su propio timeout y reintento por tarjeta."""
    base = (respuestas_previas or [])[:6]  # lista de prohibidos ACOTADA (prompts chicos)

    if sin_texto(resena):
        sel = seleccionar_banco(cargar_banco_sin_texto(), set(), banco_recientes)
        return {"energia": "agradecimiento", "borrador": sel, "cuerpo": "", "cierre": "",
                "grupo_cierre": "", "emoji_apertura": apertura_emoji(sel), "fuente": "banco",
                "revisar_manual": False, "motivo_revision": ""}

    energia = clasificar_energia(resena)
    paleta = ENERGIA_EMOJIS.get(energia, EMOJIS_APERTURA)
    emoji_obj = paleta[indice % len(paleta)]
    apertura_ang = APERTURAS_ANGULO[indice % len(APERTURAS_ANGULO)]
    genero = inferir_genero(resena.get("reviewer") or "")
    cierre_sel, grupo = seleccionar_cierre_idx(energia, cargar_pool_cierres(), indice, cierres_recientes)

    def _ensamblar(c: str) -> str:
        return (c + " " + cierre_sel).strip()

    def _malo(c: str) -> bool:
        return bool(cuerpo_invita(c) or violaciones_contenido(_ensamblar(c), resena))

    def _gen(extra: str = "") -> str:
        c = generar_cuerpo(resena, base, emoji_obj, energia, apertura_ang, genero, extra)
        n = 0
        while _malo(c) and n < max_reintentos:
            c = generar_cuerpo(resena, base + [c], emoji_obj, energia, apertura_ang, genero, extra)
            n += 1
        return c

    cuerpo = _gen()
    full = _ensamblar(cuerpo)
    natural, motivo = evaluar_naturalidad(full)
    if not natural:
        cuerpo = _gen(extra=f"NO uses frases artificiales o de marketing como: {motivo}")
        full = _ensamblar(cuerpo)
        natural, motivo = evaluar_naturalidad(full)
    return {"energia": energia, "borrador": full, "cuerpo": cuerpo, "cierre": cierre_sel,
            "grupo_cierre": grupo, "emoji_apertura": apertura_emoji(full), "fuente": "generado",
            "revisar_manual": not natural, "motivo_revision": "" if natural else motivo}
