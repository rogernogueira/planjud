# -*- coding: utf-8 -*-
"""Testes offline (não tocam a rede): resolução de critérios, datas, payload e extração.

Rode com:  pytest -q
"""
import pathlib
import sys
from datetime import date

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import planjud_calc as pc  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Isola cache e catálogo global entre testes (sem tocar a rede)."""
    monkeypatch.setenv("PLANJUD_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("PLANJUD_CATALOG", raising=False)
    pc._CATALOGO = {"correcao": None, "juros": None}
    yield
    pc._CATALOGO = {"correcao": None, "juros": None}


def test_resolve_por_alias_e_acento():
    assert pc.resolve(pc.CORRECAO, "INPC")[1] == "b17bff33-e054-48b4-bc47-759885db09e7"
    # aceita variação com acento/separador
    assert pc.resolve(pc.CORRECAO, "Fazenda Pública")[0] == "FAZENDA_PUBLICA"
    # GUID direto passa por id
    assert pc.resolve(pc.CORRECAO, "a4b46250-810a-4c58-8078-b721f9ca82c3")[1].startswith("a4b46250")


def test_parse_datas_variados_formatos():
    assert pc.parse_date("2011-04-01") == date(2011, 4, 1)
    assert pc.parse_date("2011-04") == date(2011, 4, 1)
    assert pc.parse_date("04/2011") == date(2011, 4, 1)
    assert pc.parse_date("01/04/2011") == date(2011, 4, 1)


def test_parse_parcela_com_e_sem_nome():
    p = pc.parse_parcela("645.36:2011-04-01:Aluguel")
    assert p["valor"] == 645.36 and p["nome"] == "Aluguel" and p["juros_mora"] is None
    p2 = pc.parse_parcela("1000:2015-06")
    assert p2["valor"] == 1000 and p2["nome"] == "Parcela"


def test_build_payload_multiplas_parcelas():
    ps = [pc.parse_parcela("10:2020-01-01"), pc.parse_parcela("20:2021-01-01"), pc.parse_parcela("30:2022-01-01")]
    cid = pc.CORRECAO["INPC"][0]
    jid = pc.JUROS["SEM_JUROS"]
    payload = pc.Planjud.build_payload(ps, cid, jid, date(2026, 8, 1))
    lista = payload["listaPartesParcelas"]
    assert len(lista) == 3
    assert [x["seq"] for x in lista] == [1, 2, 3]
    assert lista[0]["dataJurosCorrecao"] == "2020-01-01T00:00:00"
    assert all(x["tipoParteParcela"] == 1 for x in lista)
    assert payload["criterioCorrecaoMonetariaJurosMora"]["criterioCorrecaoMonetaria"] == cid


def test_extrair_resultado_sintetico():
    bruto = {
        "codigoCalculo": "2026 TMQ 000000",
        "dataBase": "2026-08-01T00:00:00",
        "criterioCorrecaoMonetario": "INPC (IBGE) em todo o período.",
        "criterioJurosMora": "Sem inclusão de juros de mora.",
        "partesParcelas": {"parcelasDetalhadoDetalhado": [
            {"listaPartesParcelasDetalhados": [{
                "nomeParcela": "Aluguel", "termoInicioCorrecaoMonetariaString": "04/2011",
                "valorParcela": 645.36, "fatorCorrecao": "2,3183389",
                "valorCorrigido": 1496.16, "valorJurosMora": 0.0, "valorSelic": 0.0, "total": 1496.16,
            }]}
        ]},
        "subTotal1": {"valorCorrigido": 1496.16},
        "total": {"total": 1496.16},
        "aplicarEC136": False,
    }
    out = pc.extrair_resultado(bruto)
    assert out["codigo_calculo"] == "2026 TMQ 000000"
    assert out["data_base"] == "2026-08"
    assert out["parcelas"][0]["fator_correcao"] == "2,3183389"
    assert out["total_geral"] == 1496.16


# ---------------------------------------------------------------------------
# Catálogo: extração do HTML + mescla/diff (offline)
# ---------------------------------------------------------------------------
HTML_FAKE = """
new Vue({ data() { return {
  opcoesCriterioCorrecaoMonetaria: [
    {"id":"b17bff33-e054-48b4-bc47-759885db09e7","descricao":"INPC/IBGE",
     "dataInicioCorrecao":"1979-04-01T00:00:00","dataBase":"2026-12-01T00:00:00","tipo":6},
    {"id":"aaaaaaaa-1111-2222-3333-444444444444",
     "descricao":"DEBITOS GERAIS + IPCA - [ORTN - OTN - IPCA]",
     "dataInicioCorrecao":"1964-10-01T00:00:00","dataBase":"2026-08-01T00:00:00","tipo":62}
  ],
  opcoesCriterioJurosMora: [ {"id":"19762eda-1aad-4b9f-9d57-f2ea46598b9f","nome":"SEM JUROS","tipo":50} ],
  outraCoisa: [1,2,3]
}; } });
"""


def test_extract_json_array_com_colchetes_em_string():
    # colchetes DENTRO da string nao devem quebrar o casamento
    assert pc._extract_json_array(HTML_FAKE, "outraCoisa") == [1, 2, 3]
    corr, jur = pc.extrair_opcoes_pagina(HTML_FAKE)
    assert len(corr) == 2 and len(jur) == 1
    assert "[ORTN - OTN - IPCA]" in corr[1]["descricao"]


def test_mesclar_catalogo_atualiza_databas_e_adiciona_novo():
    corr, jur = pc.extrair_opcoes_pagina(HTML_FAKE)
    novo = pc.mesclar_catalogo(corr, jur)
    # INPC existia com data-base 2026-08-01 no snapshot -> foi atualizado
    assert novo["correcao"]["INPC"][2] == "2026-12-01"
    # id novo (nao presente no snapshot) -> ganhou alias por slug
    assert any(a.startswith("DEBITOS_GERAIS_IPCA") for a in novo["correcao"])
    # juros conhecido foi preservado sem duplicar
    assert novo["juros"]["SEM_JUROS"] == pc.JUROS["SEM_JUROS"]


def test_diferenciar_catalogo_reporta_mudancas():
    corr, jur = pc.extrair_opcoes_pagina(HTML_FAKE)
    antigo = {"correcao": dict(pc.CORRECAO), "juros": dict(pc.JUROS)}
    mud = pc.diferenciar_catalogo(antigo, pc.mesclar_catalogo(corr, jur))
    assert any("INPC" in m and "->" in m for m in mud)
    assert any(m.startswith("+ correção NOVO") for m in mud)


def test_catalogo_cache_roundtrip():
    corr, jur = pc.extrair_opcoes_pagina(HTML_FAKE)
    novo = pc.mesclar_catalogo(corr, jur)
    pc.salvar_catalogo(novo)
    pc._CATALOGO = {"correcao": None, "juros": None}      # força recarregar
    lido = pc.carregar_catalogo()
    assert lido["correcao"]["INPC"][2] == "2026-12-01"


# ---------------------------------------------------------------------------
# Cache de resultados
# ---------------------------------------------------------------------------
def test_cache_key_deterministico_e_independente_de_ordem():
    ps = [pc.parse_parcela("10:2020-01-01:A"), pc.parse_parcela("20:2021-01-01:B")]
    cid, jid = pc.CORRECAO["INPC"][0], pc.JUROS["SEM_JUROS"]
    p1 = pc.Planjud.build_payload(ps, cid, jid, date(2026, 8, 1))
    p2 = pc.Planjud.build_payload(list(reversed(ps)), cid, jid, date(2026, 8, 1))
    assert pc._cache_key(p1) == pc._cache_key(p2)
    # muda a data-base -> muda a chave
    p3 = pc.Planjud.build_payload(ps, cid, jid, date(2026, 9, 1))
    assert pc._cache_key(p1) != pc._cache_key(p3)


# ---------------------------------------------------------------------------
# Motor local (séries do BACEN) — com cache semeado, sem rede
# ---------------------------------------------------------------------------
def test_motor_local_com_serie_semeada(tmp_path):
    import json
    from datetime import datetime
    # semeia a série do INPC (SGS 188) no diretório de cache isolado
    p = pathlib.Path(pc._sgs_path(188))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"salvo_em": datetime.now().isoformat(timespec="seconds"), "serie": 188,
                             "dados": {"2011-04": 0.72, "2011-05": 0.57, "2011-06": 0.22}}))
    res = pc.calcular_local([pc.parse_parcela("1000:2011-04-01")], "INPC", date(2011, 6, 1))
    esperado = (1.0072 * 1.0057 * 1.0022)
    it = res["partesParcelas"]["parcelasDetalhadoDetalhado"][0]["listaPartesParcelasDetalhados"][0]
    assert abs(float(it["fatorCorrecao"].replace(",", ".")) - esperado) < 1e-6  # fator formatado com 7 casas
    assert abs(it["valorCorrigido"] - 1000 * esperado) < 1e-9
    # e o formato normalizado continua compatível
    out = pc.extrair_resultado(res)
    assert out["codigo_calculo"] == "LOCAL-INPC" and out["parcelas"][0]["termo_correcao"] == "04/2011"


def test_motor_local_recusa_antes_de_1995_e_criterio_nao_suportado():
    with pytest.raises(ValueError):
        pc.calcular_local([pc.parse_parcela("100:1994-01-01")], "INPC", date(2026, 8, 1))
    with pytest.raises(ValueError):
        pc.calcular_local([pc.parse_parcela("100:2011-04-01")], "FAZENDA_PUBLICA", date(2026, 8, 1))


def test_motor_efetivo_decisoes():
    ps = [pc.parse_parcela("10:2011-04-01")]
    assert pc.motor_efetivo("planjud", "INPC", "SEM_JUROS", ps, False, False) == "planjud"
    assert pc.motor_efetivo("local", "INPC", "SEM_JUROS", ps, False, False) == "local"
    assert pc.motor_efetivo("auto", "INPC", "SEM_JUROS", ps, False, False) == "local"
    assert pc.motor_efetivo("auto", "INPC", "JUROS_12", ps, False, False) == "planjud"     # juros != SEM
    assert pc.motor_efetivo("auto", "FAZENDA_PUBLICA", "SEM_JUROS", ps, False, False) == "planjud"
    assert pc.motor_efetivo("auto", "INPC", "SEM_JUROS", ps, True, False) == "planjud"      # EC 136
    with pytest.raises(ValueError):
        pc.motor_efetivo("local", "INPC", "JUROS_12", ps, False, False)


def test_motor_local_e_o_padrao():
    """O motor local é o default do CLI (e do MCP), não o Planjud."""
    args = pc.build_parser().parse_args(["--parcela", "10:2011-04-01"])
    assert args.motor == "local"
    # o default nao pode cair no Planjud silenciosamente: caso fora do escopo -> erro claro
    with pytest.raises(ValueError) as ei:
        pc.motor_efetivo(args.motor, "FAZENDA_PUBLICA", "SEM_JUROS",
                         [pc.parse_parcela("10:2011-04-01")], False, False)
    assert "--motor planjud" in str(ei.value) and "--motor auto" in str(ei.value)


def test_mcp_calcular_correcao_default_local():
    """O default documentado da tool MCP tambem deve ser 'local' (sem depender de rede)."""
    import inspect
    pytest.importorskip("mcp", reason="SDK MCP não instalado (teste opcional)")
    import planjud_mcp as pm
    sig = inspect.signature(pm.calcular_correcao)
    assert sig.parameters["motor"].default == "local"
