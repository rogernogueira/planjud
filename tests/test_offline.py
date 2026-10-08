from datetime import date
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pymupdf as fitz

from demonstrativo_mcp import _planjud_calc
from demonstrativo_mcp.excel_export import write_payment_workbook
from demonstrativo_mcp.extractor import (
    PaymentRow,
    find_statement_pages,
    parse_brazilian_date,
    parse_brazilian_money,
)
from demonstrativo_mcp.server import handle_request


def test_tipos_brasileiros() -> None:
    assert parse_brazilian_money("1.169,63") == Decimal("1169.63")
    assert parse_brazilian_money("0,00") == Decimal("0.00")
    assert parse_brazilian_date("10/11/2016") == date(2016, 11, 10)


def test_localiza_demonstrativo_sem_ocr(tmp_path: Path) -> None:
    path = tmp_path / "sintetico.pdf"
    document = fitz.open()
    page = document.new_page()
    page.insert_text((50, 50), "DEMONSTRATIVO DE PAGAMENTOS")
    page.insert_text((50, 100), "P.1/180")
    document.save(path)
    document.close()

    with fitz.open(path) as reopened:
        assert find_statement_pages(reopened) == [0]


def test_mcp_expoe_apenas_ferramentas_offline() -> None:
    initialized = handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    )
    assert initialized["result"]["serverInfo"] == {
        "name": "distrato-planjud",
        "version": "2.0.0",
    }

    listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert [tool["name"] for tool in listed["result"]["tools"]] == [
        "localizar_paginas_demonstrativo",
        "extrair_demonstrativo_pagamentos",
        "listar_criterios",
        "indice_disponivel",
        "calcular_correcao",
    ]
    assert _planjud_calc.requests is None


def test_mcp_processa_exemplo_anonimizado_do_repositorio() -> None:
    example = Path(__file__).parents[1] / "examples" / "processo1_anonimizado.pdf"
    assert example.is_file()

    called = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "extrair_demonstrativo_pagamentos",
                "arguments": {
                    "pdf_path": str(example),
                    "exportar_arquivos": False,
                },
            },
        }
    )

    result = called["result"]["structuredContent"]
    assert result["paginas_pdf"] == [33, 34]
    assert result["quantidade_lancamentos"] == 66
    assert result["total_extraido"] == 56358.12
    assert result["total_recebido_documento"] == 56358.12
    assert result["validacao_ok"] is True


def test_calculo_local_com_snapshot_empacotado() -> None:
    called = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "calcular_correcao",
                "arguments": {
                    "parcelas": [{"valor": 645.36, "data": "2011-04-01"}],
                    "correcao": "INPC",
                    "data_base": "2026-08",
                },
            },
        }
    )
    result = called["result"]["structuredContent"]
    assert round(result["total_geral"], 2) == 1496.16
    assert result["modo_rede"] == "desativado"
    assert result["registro_publico"] is False


def test_planilha_tem_abas_e_formulas_cruzadas(tmp_path: Path) -> None:
    row = PaymentRow(
        pagina=1,
        parcela="P.1/180",
        tipo_lancamento="parcela",
        elegivel_restituicao=True,
        descricao="Parcela",
        vencimento=date(2016, 10, 10),
        atraso_dias=31,
        valor_pago=Decimal("1169.63"),
        data_recebimento=date(2016, 11, 10),
        valor_da_parcela=Decimal("1000.00"),
        principal=Decimal("1000.00"),
        juros=Decimal("0.00"),
        correcao=Decimal("100.00"),
        multa=Decimal("20.00"),
        juros_atraso=Decimal("49.63"),
        desconto_antecipacao=Decimal("0.00"),
        parcela_mais=Decimal("1169.63"),
    )
    output = tmp_path / "resultado.xlsx"
    series = Path(__file__).parents[1] / "src" / "demonstrativo_mcp" / "data" / "sgs_188.json"
    write_payment_workbook([row], output, series, retention_percent=10)

    with ZipFile(output) as archive:
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        payments = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        inpc = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")

    assert 'name="Pagamentos"' in workbook
    assert 'name="INPC"' in workbook
    assert 'LEFT($B4,2)="P."' in payments
    assert "VLOOKUP(L4,INPC!$A$6:$D$" in payments
    assert "O4*$B$2" in payments
    assert "C6*(1+B6)" in inpc
