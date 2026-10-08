from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

import pymupdf as fitz

from .excel_export import write_payment_workbook


TITLE = "DEMONSTRATIVO DE PAGAMENTOS"
INSTALLMENT_RE = re.compile(r"^P\.\d+/\d+$", re.IGNORECASE)
ADMIN_RE = re.compile(r"^\d+(?:\.\d+)+/\d+$")
MONEY_RE = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d{2}$|^-?\d+,\d{2}$")

# Limites horizontais medidos no relatório A4 do UAU. Eles são convertidos em
# proporções para continuarem válidos quando o PDF tiver outra escala.
REFERENCE_WIDTH = 595.28
COLUMN_BOUNDS = (
    ("parcela", 0.0, 50.0),
    ("descricao", 50.0, 105.0),
    ("vencimento", 105.0, 146.0),
    ("atraso_dias", 146.0, 175.0),
    ("valor_pago", 175.0, 215.0),
    ("data_recebimento", 215.0, 253.0),
    ("valor_da_parcela", 253.0, 315.0),
    ("principal", 315.0, 364.0),
    ("juros", 364.0, 390.0),
    ("correcao", 390.0, 440.0),
    ("multa", 440.0, 464.0),
    ("juros_atraso", 464.0, 502.0),
    ("desconto_antecipacao", 502.0, 538.0),
    ("parcela_mais", 538.0, REFERENCE_WIDTH + 1.0),
)
MONEY_FIELDS = {
    "valor_pago",
    "valor_da_parcela",
    "principal",
    "juros",
    "correcao",
    "multa",
    "juros_atraso",
    "desconto_antecipacao",
    "parcela_mais",
}


@dataclass(frozen=True)
class PaymentRow:
    pagina: int
    parcela: str
    tipo_lancamento: str
    elegivel_restituicao: bool
    descricao: str | None
    vencimento: date | None
    atraso_dias: int | None
    valor_pago: Decimal | None
    data_recebimento: date | None
    valor_da_parcela: Decimal | None
    principal: Decimal | None
    juros: Decimal | None
    correcao: Decimal | None
    multa: Decimal | None
    juros_atraso: Decimal | None
    desconto_antecipacao: Decimal | None
    parcela_mais: Decimal | None

    def to_dict(self) -> dict[str, Any]:
        raw = asdict(self)
        for key, value in raw.items():
            if isinstance(value, date):
                raw[key] = value.strftime("%d/%m/%Y")
            elif isinstance(value, Decimal):
                raw[key] = float(value)
        return raw


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).upper()


def parse_brazilian_money(value: str | None) -> Decimal | None:
    if not value:
        return None
    cleaned = value.strip().replace("R$", "").replace(" ", "")
    if not MONEY_RE.match(cleaned):
        return None
    try:
        return Decimal(cleaned.replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def parse_brazilian_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def find_statement_pages(document: fitz.Document) -> list[int]:
    title = _normalize_text(TITLE)
    pages: list[int] = []
    for index, page in enumerate(document):
        if title not in _normalize_text(page.get_text("text")):
            continue
        # Evita falsos positivos em petições que apenas mencionem o nome do
        # documento. Uma página do relatório também precisa conter ao menos um
        # identificador de lançamento na camada de palavras.
        if any(
            INSTALLMENT_RE.match(word[4]) or ADMIN_RE.match(word[4])
            for word in page.get_text("words")
        ):
            pages.append(index)
    return pages


def _column_for_x(x0: float, page_width: float) -> str | None:
    reference_x = x0 * REFERENCE_WIDTH / page_width
    for name, lower, upper in COLUMN_BOUNDS:
        if lower <= reference_x < upper:
            return name
    return None


def _join_words(words: Iterable[tuple]) -> str:
    ordered = sorted(words, key=lambda word: (round(word[1], 1), word[0]))
    value = " ".join(word[4] for word in ordered).strip()
    # O gerador do relatório às vezes quebra uma palavra no fim da faixa sem
    # inserir hífen. Corrigimos apenas as duas descrições administrativas
    # conhecidas, sem alterar livremente o conteúdo extraído.
    value = re.sub(r"\bTRANSFERENCI\s+A\b", "TRANSFERENCIA", value, flags=re.IGNORECASE)
    value = re.sub(r"\bRENEGO\s+CIA[ÇC]AO\b", "RENEGOCIACAO", value, flags=re.IGNORECASE)
    return value


def _classify_admin(description: str) -> str:
    normalized = _normalize_text(description)
    if "TRANSFEREN" in normalized:
        return "taxa_transferencia"
    if "RENEGO" in normalized:
        return "renegociacao"
    return "administrativo"


def _extract_rows_from_page(page: fitz.Page, page_number: int) -> list[PaymentRow]:
    words = page.get_text("words", sort=True)
    anchors = sorted(
        (word for word in words if INSTALLMENT_RE.match(word[4]) or ADMIN_RE.match(word[4])),
        key=lambda word: word[1],
    )
    rows: list[PaymentRow] = []

    for index, anchor in enumerate(anchors):
        baseline = anchor[1]
        next_y = anchors[index + 1][1] if index + 1 < len(anchors) else float("inf")
        installment = anchor[4]
        is_installment = bool(INSTALLMENT_RE.match(installment))
        baseline_words = [word for word in words if abs(word[1] - baseline) <= 1.25]
        if is_installment:
            description_words = [
                word
                for word in baseline_words
                if _column_for_x(word[0], page.rect.width) == "descricao"
            ]
        else:
            description_words = [
                word
                for word in words
                if baseline - 1.25 <= word[1] < min(next_y - 1.25, baseline + 40.0)
                and _column_for_x(word[0], page.rect.width) == "descricao"
            ]

        values: dict[str, str] = {}
        for word in baseline_words:
            column = _column_for_x(word[0], page.rect.width)
            if column and column != "descricao":
                values[column] = f"{values.get(column, '')} {word[4]}".strip()

        description = _join_words(description_words) or None
        row_type = "parcela" if is_installment else _classify_admin(description or "")

        rows.append(
            PaymentRow(
                pagina=page_number,
                parcela=installment,
                tipo_lancamento=row_type,
                elegivel_restituicao=is_installment,
                descricao=description,
                vencimento=parse_brazilian_date(values.get("vencimento")),
                atraso_dias=int(values["atraso_dias"]) if values.get("atraso_dias", "").isdigit() else None,
                valor_pago=parse_brazilian_money(values.get("valor_pago")),
                data_recebimento=parse_brazilian_date(values.get("data_recebimento")),
                valor_da_parcela=parse_brazilian_money(values.get("valor_da_parcela")),
                principal=parse_brazilian_money(values.get("principal")),
                juros=parse_brazilian_money(values.get("juros")),
                correcao=parse_brazilian_money(values.get("correcao")),
                multa=parse_brazilian_money(values.get("multa")),
                juros_atraso=parse_brazilian_money(values.get("juros_atraso")),
                desconto_antecipacao=parse_brazilian_money(values.get("desconto_antecipacao")),
                parcela_mais=parse_brazilian_money(values.get("parcela_mais")),
            )
        )
    return rows


def _extract_received_total(pages_text: str) -> Decimal | None:
    match = re.search(r"(?mi)^RECEBIDO\s*:\s*\n?\s*([\d.]+,\d{2})", pages_text)
    return parse_brazilian_money(match.group(1)) if match else None


def _default_output_dir(pdf_path: Path) -> Path:
    return pdf_path.parent / f"{pdf_path.stem}_demonstrativo"


def _write_outputs(
    source: fitz.Document,
    page_indexes: list[int],
    rows: list[PaymentRow],
    result: dict[str, Any],
    output_dir: Path,
    retention_percent: float,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(source.name).stem
    pdf_output = output_dir / f"{stem}_demonstrativo_pagamentos.pdf"
    json_output = output_dir / f"{stem}_demonstrativo_pagamentos.json"
    csv_output = output_dir / f"{stem}_demonstrativo_pagamentos.csv"
    excel_output = output_dir / f"{stem}_atualizacao_inpc.xlsx"

    split_document = fitz.open()
    for page_index in page_indexes:
        split_document.insert_pdf(source, from_page=page_index, to_page=page_index)
    split_document.save(pdf_output)
    split_document.close()

    json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    dictionaries = [row.to_dict() for row in rows]
    with csv_output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dictionaries[0]) if dictionaries else ["pagina"] , delimiter=";")
        writer.writeheader()
        writer.writerows(dictionaries)

    write_payment_workbook(
        rows,
        excel_output,
        Path(__file__).with_name("data") / "sgs_188.json",
        retention_percent=retention_percent,
    )

    return {
        "pdf_paginas_separadas": str(pdf_output.resolve()),
        "json": str(json_output.resolve()),
        "csv": str(csv_output.resolve()),
        "excel": str(excel_output.resolve()),
    }


def analyze_payment_statement(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    export_files: bool = True,
    retention_percent: float = 0.0,
) -> dict[str, Any]:
    """Extrai e valida o demonstrativo, sem OCR, usando palavras e coordenadas."""
    source_path = Path(pdf_path).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"PDF não encontrado: {source_path}")
    if source_path.suffix.lower() != ".pdf":
        raise ValueError(f"O arquivo precisa ter extensão .pdf: {source_path}")
    if not 0 <= retention_percent <= 100:
        raise ValueError("retencao_percentual deve estar entre 0 e 100")

    with fitz.open(source_path) as document:
        page_indexes = find_statement_pages(document)
        if not page_indexes:
            raise ValueError(f"Nenhuma página com o título '{TITLE}' foi encontrada.")

        rows = [
            row
            for page_index in page_indexes
            for row in _extract_rows_from_page(document[page_index], page_index + 1)
        ]
        pages_text = "\n".join(document[index].get_text("text") for index in page_indexes)
        document_total = _extract_received_total(pages_text)
        extracted_total = sum((row.valor_pago or Decimal("0") for row in rows), Decimal("0"))
        difference = extracted_total - document_total if document_total is not None else None

        result: dict[str, Any] = {
            "arquivo_origem": str(source_path),
            "metodo": "PyMuPDF get_text(\"words\"), sem OCR",
            "paginas_pdf": [index + 1 for index in page_indexes],
            "quantidade_paginas": len(page_indexes),
            "quantidade_lancamentos": len(rows),
            "quantidade_parcelas": sum(row.elegivel_restituicao for row in rows),
            "quantidade_administrativos": sum(not row.elegivel_restituicao for row in rows),
            "total_extraido": float(extracted_total),
            "total_recebido_documento": float(document_total) if document_total is not None else None,
            "diferenca_validacao": float(difference) if difference is not None else None,
            "validacao_ok": difference == Decimal("0") if difference is not None else False,
            "retencao_percentual_planilha": retention_percent,
            "lancamentos": [row.to_dict() for row in rows],
        }

        if export_files:
            destination = Path(output_dir).expanduser().resolve() if output_dir else _default_output_dir(source_path)
            result["arquivos_gerados"] = _write_outputs(
                document, page_indexes, rows, result, destination, retention_percent
            )

    return result
