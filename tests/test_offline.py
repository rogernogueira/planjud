# -*- coding: utf-8 -*-
"""Testes offline (não tocam a rede): resolução de critérios, datas, payload e extração.

Rode com:  pytest -q
"""
import pathlib
import sys
from datetime import date

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import planjud_calc as pc  # noqa: E402


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
