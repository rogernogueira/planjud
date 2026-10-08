from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import xlsxwriter


INPC_SOURCE_URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.188/dados?formato=json"
)


def _excel_serial(value: date) -> int:
    return (value - date(1899, 12, 30)).days


def _load_inpc(series_path: Path) -> list[tuple[date, float]]:
    payload = json.loads(series_path.read_text(encoding="utf-8"))
    rows = []
    for competence, percentage in payload["dados"].items():
        year, month = (int(part) for part in competence.split("-"))
        if (year, month) >= (1995, 7):
            rows.append((date(year, month, 1), float(percentage) / 100.0))
    return sorted(rows)


def write_payment_workbook(
    rows: Iterable[Any],
    output_path: str | Path,
    inpc_series_path: str | Path,
    retention_percent: float = 0.0,
) -> Path:
    """Gera a planilha de pagamentos e a memória mensal do INPC com fórmulas."""
    if not 0 <= retention_percent <= 100:
        raise ValueError("retencao_percentual deve estar entre 0 e 100")

    payments = list(rows)
    inpc_rows = _load_inpc(Path(inpc_series_path))
    if not inpc_rows:
        raise ValueError("a série offline do INPC está vazia")

    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = xlsxwriter.Workbook(output)
    workbook.set_properties(
        {
            "title": "Demonstrativo de pagamentos e atualização pelo INPC",
            "subject": "Memória de cálculo de restituição",
            "author": "MCP Distrato Planjud",
        }
    )
    workbook.set_calc_mode("auto")

    payments_sheet = workbook.add_worksheet("Pagamentos")
    inpc_sheet = workbook.add_worksheet("INPC")
    payments_sheet.hide_gridlines(2)
    inpc_sheet.hide_gridlines(2)
    payments_sheet.set_tab_color("#17365D")
    inpc_sheet.set_tab_color("#95B3D7")

    title_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 14, "bold": True, "font_color": "#17365D"}
    )
    label_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "bold": True, "font_color": "#1F2937"}
    )
    input_percent_format = workbook.add_format(
        {
            "font_name": "Arial",
            "font_size": 10,
            "font_color": "#0000FF",
            "bg_color": "#FFF2CC",
            "border": 1,
            "border_color": "#D6B656",
            "num_format": "0.00%",
        }
    )
    header_format = workbook.add_format(
        {
            "font_name": "Arial",
            "font_size": 10,
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#17365D",
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "border": 1,
            "border_color": "#FFFFFF",
        }
    )
    text_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "font_color": "#1F2937", "valign": "vcenter"}
    )
    center_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "font_color": "#1F2937", "align": "center", "valign": "vcenter"}
    )
    date_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "num_format": "dd/mm/yyyy", "align": "center"}
    )
    currency_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "num_format": 'R$ #,##0.00;[Red](R$ #,##0.00);-'}
    )
    formula_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "font_color": "#000000", "num_format": 'R$ #,##0.00;[Red](R$ #,##0.00);-'}
    )
    linked_number_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "font_color": "#008000", "num_format": "0.0000000"}
    )
    linked_date_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "font_color": "#008000", "num_format": "mm/yyyy", "align": "center"}
    )
    date_formula_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "font_color": "#000000", "num_format": "mm/yyyy", "align": "center"}
    )
    percent_source_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "font_color": "#1F2937", "num_format": "0.00%"}
    )
    total_label_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 10, "bold": True, "top": 2, "font_color": "#17365D"}
    )
    total_currency_format = workbook.add_format(
        {
            "font_name": "Arial",
            "font_size": 10,
            "bold": True,
            "top": 2,
            "num_format": 'R$ #,##0.00;[Red](R$ #,##0.00);-',
        }
    )
    note_format = workbook.add_format(
        {"font_name": "Arial", "font_size": 9, "font_color": "#666666", "italic": True}
    )

    payments_sheet.merge_range("A1:T1", "Demonstrativo de pagamentos e atualização pelo INPC", title_format)
    payments_sheet.write("A2", "Retenção (%)", label_format)
    payments_sheet.write_number("B2", retention_percent / 100.0, input_percent_format)
    payments_sheet.data_validation("B2", {"validate": "decimal", "criteria": "between", "minimum": 0, "maximum": 1})
    payments_sheet.write("C2", "Célula editável; aplicada sobre o valor atualizado.", note_format)

    headers = [
        "Ordem",
        "Parcela",
        "Descrição",
        "Vencimento",
        "Pagamento",
        "Valor pago (R$)",
        "Principal (R$)",
        "Correção contratual (R$)",
        "Multa (R$)",
        "Juros mora (R$)",
        "Base restituível (R$)",
        "Competência INPC",
        "Índice anterior",
        "Fator INPC",
        "Valor atualizado (R$)",
        "Retenção (R$)",
        "Líquido a restituir (R$)",
        "",
        "",
        "Observação",
    ]
    payments_sheet.write_row("A3", headers, header_format)
    payments_sheet.set_row(2, 42)

    cumulative = 1.0
    previous_index_by_competence: dict[date, float] = {}
    for competence, monthly_rate in inpc_rows:
        previous_index_by_competence[competence] = cumulative
        cumulative *= 1.0 + monthly_rate
    final_index = cumulative
    inpc_first_excel_row = 6
    inpc_last_excel_row = inpc_first_excel_row + len(inpc_rows) - 1
    totals = {column: 0.0 for column in (5, 6, 7, 8, 9, 10, 14, 15, 16)}

    for offset, row in enumerate(payments, start=4):
        excel_row = offset
        worksheet_row = excel_row - 1
        eligible = bool(row.elegivel_restituicao)
        description = row.descricao or ""
        payment_date = row.data_recebimento
        due_date = row.vencimento
        principal = float(row.principal or Decimal("0"))
        correction = float(row.correcao or Decimal("0"))
        fine = float(row.multa or Decimal("0"))
        late_interest = float((row.juros or Decimal("0")) + (row.juros_atraso or Decimal("0")))
        paid = float(row.valor_pago or Decimal("0"))
        base = principal + correction if eligible else 0.0
        competence = date(payment_date.year, payment_date.month, 1) if eligible and payment_date else None
        previous_index = previous_index_by_competence.get(competence, 0.0) if competence else 0.0
        factor = final_index / previous_index if previous_index else 1.0
        updated = base * factor
        retention = updated * retention_percent / 100.0
        net = updated - retention
        for column, value in (
            (5, paid),
            (6, principal),
            (7, correction),
            (8, fine),
            (9, late_interest),
            (10, base),
            (14, updated),
            (15, retention),
            (16, net),
        ):
            totals[column] += value

        payments_sheet.write_number(worksheet_row, 0, excel_row - 3, center_format)
        payments_sheet.write(worksheet_row, 1, row.parcela, text_format)
        payments_sheet.write(worksheet_row, 2, description, text_format)
        if due_date:
            payments_sheet.write_datetime(worksheet_row, 3, due_date, date_format)
        if payment_date:
            payments_sheet.write_datetime(worksheet_row, 4, payment_date, date_format)
        for column, value in ((5, paid), (6, principal), (7, correction), (8, fine), (9, late_interest)):
            payments_sheet.write_number(worksheet_row, column, value, currency_format)

        payments_sheet.write_formula(
            worksheet_row,
            10,
            f'=IF(LEFT($B{excel_row},2)="P.",G{excel_row}+H{excel_row},0)',
            formula_format,
            base,
        )
        payments_sheet.write_formula(
            worksheet_row,
            11,
            f'=IF(LEFT($B{excel_row},2)="P.",DATE(YEAR(E{excel_row}),MONTH(E{excel_row}),1),"")',
            date_formula_format,
            _excel_serial(competence) if competence else "",
        )
        payments_sheet.write_formula(
            worksheet_row,
            12,
            f'=IF(LEFT($B{excel_row},2)="P.",VLOOKUP(L{excel_row},INPC!$A$6:$D${inpc_last_excel_row},3,FALSE),0)',
            linked_number_format,
            previous_index,
        )
        payments_sheet.write_formula(
            worksheet_row,
            13,
            f'=IF(LEFT($B{excel_row},2)="P.",INPC!$D$2/M{excel_row},1)',
            linked_number_format,
            factor,
        )
        payments_sheet.write_formula(
            worksheet_row, 14, f"=K{excel_row}*N{excel_row}", formula_format, updated
        )
        payments_sheet.write_formula(
            worksheet_row, 15, f"=O{excel_row}*$B$2", formula_format, retention
        )
        payments_sheet.write_formula(
            worksheet_row, 16, f"=O{excel_row}-P{excel_row}", formula_format, net
        )
        observation = "" if eligible else "Lançamento administrativo fora da base de restituição"
        payments_sheet.write(worksheet_row, 19, observation, text_format)

    first_data_row = 4
    last_data_row = first_data_row + len(payments) - 1
    total_row = last_data_row + 1
    payments_sheet.write(total_row - 1, 0, "TOTAL", total_label_format)
    for column in (5, 6, 7, 8, 9, 10, 14, 15, 16):
        letter = xlsxwriter.utility.xl_col_to_name(column)
        payments_sheet.write_formula(
            total_row - 1,
            column,
            f"=SUM({letter}{first_data_row}:{letter}{last_data_row})",
            total_currency_format,
            totals[column],
        )

    payments_sheet.add_table(
        f"A3:Q{last_data_row}",
        {
            "name": "TabelaPagamentos",
            "style": "Table Style Medium 2",
            "columns": [{"header": header} for header in headers[:17]],
        },
    )
    payments_sheet.freeze_panes(3, 3)
    payments_sheet.set_column("A:A", 8)
    payments_sheet.set_column("B:B", 13)
    payments_sheet.set_column("C:C", 31)
    payments_sheet.set_column("D:E", 12)
    payments_sheet.set_column("F:G", 17)
    payments_sheet.set_column("H:H", 24)
    payments_sheet.set_column("I:J", 16)
    payments_sheet.set_column("K:K", 20)
    payments_sheet.set_column("L:L", 15)
    payments_sheet.set_column("M:N", 14)
    payments_sheet.set_column("O:Q", 20)
    payments_sheet.set_column("R:S", 3)
    payments_sheet.set_column("T:T", 48)
    payments_sheet.set_landscape()
    payments_sheet.fit_to_pages(1, 0)
    payments_sheet.repeat_rows(0, 2)

    inpc_sheet.write("A1", "Fonte", label_format)
    inpc_sheet.write_url("B1", INPC_SOURCE_URL, string="Banco Central do Brasil — SGS 188")
    inpc_sheet.write("C1", "Última competência", label_format)
    inpc_sheet.write_datetime("D1", inpc_rows[-1][0], linked_date_format)
    inpc_sheet.write("A2", "Observação", label_format)
    inpc_sheet.write(
        "B2",
        "Série 188 – INPC, variação percentual mensal, fonte IBGE, disponibilizada pelo Banco Central.",
        text_format,
    )
    inpc_sheet.write("C2", "Índice acumulado final", label_format)
    inpc_sheet.write_formula("D2", f"=D{inpc_last_excel_row}", linked_number_format, final_index)
    inpc_sheet.write_row(
        "A5", ["Competência", "INPC mensal", "Índice anterior", "Índice acumulado"], header_format
    )
    inpc_sheet.set_row(4, 30)

    previous = 1.0
    for offset, (competence, monthly_rate) in enumerate(inpc_rows, start=6):
        worksheet_row = offset - 1
        accumulated = previous * (1.0 + monthly_rate)
        inpc_sheet.write_datetime(worksheet_row, 0, competence, date_format)
        inpc_sheet.write_number(worksheet_row, 1, monthly_rate, percent_source_format)
        if offset == 6:
            inpc_sheet.write_number(worksheet_row, 2, 1.0, linked_number_format)
        else:
            inpc_sheet.write_formula(
                worksheet_row, 2, f"=D{offset - 1}", linked_number_format, previous
            )
        inpc_sheet.write_formula(
            worksheet_row, 3, f"=C{offset}*(1+B{offset})", linked_number_format, accumulated
        )
        previous = accumulated

    inpc_sheet.add_table(
        f"A5:D{inpc_last_excel_row}",
        {
            "name": "TabelaINPC",
            "style": "Table Style Medium 2",
            "columns": [
                {"header": "Competência"},
                {"header": "INPC mensal"},
                {"header": "Índice anterior"},
                {"header": "Índice acumulado"},
            ],
        },
    )
    inpc_sheet.freeze_panes(5, 1)
    inpc_sheet.set_column("A:A", 15)
    inpc_sheet.set_column("B:B", 92)
    inpc_sheet.set_column("C:D", 23)
    inpc_sheet.set_row(1, 38)
    inpc_sheet.set_landscape()
    inpc_sheet.fit_to_pages(1, 0)
    inpc_sheet.repeat_rows(0, 4)

    workbook.close()
    return output
