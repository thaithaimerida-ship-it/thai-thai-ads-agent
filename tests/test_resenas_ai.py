"""Tests del generador de reseñas 5★ — los 10 candados + pool + banco + energía.

Deterministas: ejercitan las guardas y la selección directamente (sin LLM real); el único
test que toca el LLM (C7 naturalidad) lo mockea.
"""
from engine import resenas_ai as R


# ── Energía + sin-texto ───────────────────────────────────────────────────────
def test_energia_con_texto_nunca_agradecimiento():
    assert R.clasificar_energia({"comment": "El curry picante estuvo delicioso"}) == "explosiva"
    assert R.clasificar_energia({"comment": "Muy buen lugar, ambiente agradable"}) == "zen"
    assert R.clasificar_energia({"comment": "Todo rapidísimo y práctico"}) == "vibrante"


def test_energia_sin_texto_es_agradecimiento():
    assert R.clasificar_energia({"comment": ""}) == "agradecimiento"
    assert R.sin_texto({"comment": "   "}) is True
    assert R.sin_texto({"comment": "muy buen lugar"}) is False


# ── Pool + banco (cargados de voz_resenas.md) ─────────────────────────────────
def test_pool_cierres_tres_grupos():
    pool = R.cargar_pool_cierres()
    assert set(pool) == {"calido", "elegante", "antojo"}
    assert len(pool["calido"]) == 5 and len(pool["elegante"]) == 4 and len(pool["antojo"]) == 4


def test_banco_quince_respuestas():
    banco = R.cargar_banco_sin_texto()
    assert len(banco) == 15
    assert banco[0].startswith("¡Muchas gracias por tu visita!")


def test_pool_y_banco_no_estan_en_el_prompt_del_generador():
    # C9b: los cierres y el banco NO deben entrar al system prompt del generador (imanes).
    voz = R.load_voz()
    assert "Pool de cierres" not in voz
    assert "Banco 5" not in voz


def test_sin_texto_usa_banco_verbatim_sin_llm(monkeypatch):
    # Reseña sin texto → banco verbatim, sin llamar al LLM.
    def _boom(*a, **k):
        raise AssertionError("no debe llamar al LLM para reseñas sin texto")
    monkeypatch.setattr(R.llm_client, "generate_text", _boom)
    out = R.generar_borradores([{"stars": 5, "comment": "", "reviewer": "Ana"}])
    assert out[0]["fuente"] == "banco"
    assert out[0]["borrador"] in R.cargar_banco_sin_texto()
    assert "Ana" not in out[0]["borrador"]  # sin nombre, verbatim


def test_seleccion_cierre_por_energia_y_sin_repetir():
    pool = R.cargar_pool_cierres()
    c1, g1 = R.seleccionar_cierre("zen", pool, set(), [])
    assert g1 == "calido"
    c2, g2 = R.seleccionar_cierre("explosiva", pool, set(), [])
    assert g2 == "antojo"
    # no repetir en el lote
    c3, _ = R.seleccionar_cierre("zen", pool, {c1}, [])
    assert c3 != c1


def test_seleccion_banco_sin_repetir_y_evita_recientes():
    banco = R.cargar_banco_sin_texto()
    b1 = R.seleccionar_banco(banco, set(), [])
    b2 = R.seleccionar_banco(banco, {b1}, [])
    assert b1 != b2
    # evita una usada en publicaciones recientes
    b3 = R.seleccionar_banco(banco, set(), [banco[0]])
    assert b3 != banco[0]


def test_banco_rota_15_respuestas_distintas():
    # 15 reseñas sin texto → 15 respuestas distintas (rotación determinista por review_id).
    banco = R.cargar_banco_sin_texto()
    por_cubeta = {}
    i = 0
    while len(por_cubeta) < len(banco) and i < 100000:
        rid = f"rev-{i}"
        por_cubeta.setdefault(R._hash_idx(rid, len(banco)), rid)
        i += 1
    ids = list(por_cubeta.values())
    assert len(ids) == 15
    respuestas = [R.seleccionar_banco_por_review(banco, rid, []) for rid in ids]
    assert len(set(respuestas)) == 15


def test_banco_misma_resena_misma_respuesta_estable():
    banco = R.cargar_banco_sin_texto()
    a = R.seleccionar_banco_por_review(banco, "AbFvOq_estable_xyz", [])
    b = R.seleccionar_banco_por_review(banco, "AbFvOq_estable_xyz", [])
    assert a == b and a in banco  # misma reseña recargada → misma respuesta


def test_banco_evita_respuesta_en_ultimas_publicadas():
    banco = R.cargar_banco_sin_texto()
    rid = "rev-7"
    base = R.seleccionar_banco_por_review(banco, rid, [])      # la del hash
    otra = R.seleccionar_banco_por_review(banco, rid, [base])  # base ya publicada → avanza
    assert otra != base and otra in banco


# ── Variedad + emojis ─────────────────────────────────────────────────────────
def test_borradores_misma_corrida_no_comparten_apertura_ni_cierre():
    distintos = ["😄 Qué gusto leerte, gracias", "🙌 No puede ser qué linda reseña", "⭐ Mil gracias de corazón"]
    assert R.validar_variedad(distintos) == []
    repetidos = ["😄 Qué gusto leerte amigo", "😄 Qué gusto leerte de nuevo"]
    assert R.validar_variedad(repetidos)  # apertura + emoji repetidos


def test_borrador_max_3_emojis():
    assert R.contar_emojis("😄🙌⭐ hola") == 3
    assert R.contar_emojis("hola 😄🙌⭐🥳 mundo") == 4
    assert R.contar_emojis(R.limitar_emojis("😄🙌⭐🥳🤩 hola")) == 3


# ── C1..C10 ───────────────────────────────────────────────────────────────────
def test_c1_cierre_por_raiz_antoje_antojo():
    # caso real #4/#5: "antoje" vs "antojo" comparten raíz → colisión.
    a = "Gracias por venir cuando se te antoje"
    b = "Aquí cuando te dé el antojo"
    assert R.validar_variedad([a, b])


def test_c2_carino_a_equipo():
    assert R.viola_carino_equipo("Le mando un abrazo a la cocina y al equipo")
    assert not R.viola_carino_equipo("Gracias por tu visita, un abrazo para ti")


def test_c3_mezcla_persona():
    # caso real #4: "te sentiste" (tú) + "Su mesa lo espera" (usted)
    assert R.persona_mezclada("Qué gusto que te sentiste a gusto; su mesa lo espera")
    assert not R.persona_mezclada("Qué gusto que te sentiste a gusto; tu mesa te espera")


def test_c4_bienvenida_sin_primera_visita():
    resena_repetida = {"comment": "La comida estuvo deliciosa otra vez"}
    assert R.bienvenida_indebida("¡Bienvenido a Thai Thai!", resena_repetida)
    resena_primera = {"comment": "Primera vez que vengo y me encantó"}
    assert not R.bienvenida_indebida("¡Bienvenido!", resena_primera)


def test_c5_genero_karol_comodo_falla():
    # Karol = ambiguo → adjetivo con género ("cómodo") es violación; neutro pasa.
    karol = {"reviewer": "Karol Villalba", "comment": "muy buen lugar"}
    assert R.inferir_genero("Karol Villalba") == "ambiguo"
    assert R.genero_incorrecto("Qué gusto que te sentiste cómodo", karol)
    assert not R.genero_incorrecto("Qué gusto que te sentiste a gusto", karol)


def test_c6_cierre_no_afirmativo_ojala():
    # caso real Wendy: "ojalá" en el cierre.
    assert R.cierre_no_afirmativo("Gracias, ojalá te des otra vuelta")
    assert not R.cierre_no_afirmativo("Gracias, te esperamos pronto")


def test_c7_naturalidad_mockea_llm(monkeypatch):
    monkeypatch.setattr(R.llm_client, "generate_text", lambda **k: "ARTIFICIAL: así da gusto recibirte")
    natural, motivo = R.evaluar_naturalidad("Gracias, así da gusto recibirte")
    assert natural is False and "así da gusto" in motivo
    monkeypatch.setattr(R.llm_client, "generate_text", lambda **k: "NATURAL")
    assert R.evaluar_naturalidad("Gracias por tu visita")[0] is True


def test_c7_doble_pase_discrepancia_da_natural(monkeypatch):
    # El juez LLM es ruidoso: si un pase dice artificial pero el otro natural, NO se flaggea
    # (default natural). Recalibración 2026-06-14: evita falsos positivos en respuestas cálidas.
    respuestas = iter(["ARTIFICIAL: auténtica comida tailandesa", "NATURAL"])
    monkeypatch.setattr(R.llm_client, "generate_text", lambda **k: next(respuestas))
    assert R.evaluar_naturalidad("Qué gusto que te encantara, vente por más")[0] is True


def test_c7_doble_pase_confirma_artificial(monkeypatch):
    # Dos pases coinciden en artificial (frase de folleto real) → SÍ se flaggea.
    monkeypatch.setattr(R.llm_client, "generate_text", lambda **k: "ARTIFICIAL: deleitar tu paladar")
    natural, motivo = R.evaluar_naturalidad("Ven a deleitar tu paladar")
    assert natural is False and "deleitar tu paladar" in motivo


def test_c8_frase_repetida_interna():
    # caso real Wendy: "gracias por tomarte el tiempo de escribir" ×2.
    doble = "Gracias por tomarte el tiempo de escribir; de corazón, gracias por tomarte el tiempo de escribir"
    assert R.frase_repetida_interna(doble)
    assert not R.frase_repetida_interna("Gracias por tu reseña, nos alegra mucho leerte")


def test_c9_cierre_repetido_en_lote():
    # caso real: tres "tu mesa te espera" deben fallar.
    trio = ["A 😄 aquí tu mesa te espera", "B 🙌 ya sabes, tu mesa te espera", "C ⭐ tu mesa te espera siempre"]
    assert R.validar_variedad(trio)


def test_c10_agencia_fabian():
    # caso real Fabián: "la comida te salió deliciosa" (él no cocinó).
    assert R.viola_agencia("Qué gusto que la comida te salió deliciosa")
    assert not R.viola_agencia("Qué gusto que la comida estuvo deliciosa")


def test_frase_artificial_backstop():
    assert R.tiene_frase_artificial("y así da gusto leer eso")
    assert R.tiene_frase_artificial("nos encanta la comida ágil")
    assert not R.tiene_frase_artificial("gracias por tu visita")


def test_v1_voz_plural_no_singular():
    # caso real: "la atención de Alejandro y la mía" → primera persona singular, MAL.
    assert R.voz_singular("Qué gusto, la atención de Alejandro y la mía estuvo al pendiente")
    assert R.voz_singular("a mí me encantó")
    assert not R.voz_singular("Nuestra atención y la de Alejandro te cuidaron; nos encantó")
    assert R.violaciones_contenido("me dio mucho gusto", {"reviewer": "Ana"}).count("voz_singular") == 1


def test_v2_emoji_solo_paleta_aprobada():
    # caso real: 🫶🏻 copiado de la reseña (base fuera de paleta + tono de piel) → MAL.
    assert R.emoji_no_aprobado("Gracias 🫶🏻 por tu visita")
    assert R.emoji_no_aprobado("Gracias 😄🏽")            # tono de piel solo
    assert not R.emoji_no_aprobado("Gracias 😄 por tu visita ⭐")
    limpio = R.limpiar_emojis_no_aprobados("Gracias 🫶🏻 por tu visita 😄")
    assert "🫶" not in limpio and "🏻" not in limpio and "😄" in limpio


def test_cuerpo_no_invita():
    assert R.cuerpo_invita("Gracias, te esperamos pronto")
    assert R.cuerpo_invita("Vuelve cuando quieras")
    assert not R.cuerpo_invita("Qué gusto que la comida estuvo deliciosa")
