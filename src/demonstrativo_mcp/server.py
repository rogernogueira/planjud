from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

import pymupdf as fitz

from .extractor import TITLE, analyze_payment_statement, find_statement_pages
from .planjud_tools import (
    calcular_correcao,
    indice_disponivel,
    listar_criterios,
)


SERVER_INFO = {"name": "distrato-planjud", "version": "2.0.0"}


def localizar_paginas_demonstrativo(pdf_path: str) -> dict[str, Any]:
    """Localiza as páginas que contêm o relatório e códigos de lançamento."""
    path = Path(pdf_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"PDF não encontrado: {path}")
    with fitz.open(path) as document:
        pages = [index + 1 for index in find_statement_pages(document)]
    return {
        "arquivo": str(path),
        "titulo_procurado": TITLE,
        "paginas": pages,
        "quantidade": len(pages),
    }


def extrair_demonstrativo_pagamentos(
    pdf_path: str,
    output_dir: str | None = None,
    exportar_arquivos: bool = True,
    retencao_percentual: float = 0.0,
) -> dict[str, Any]:
    """Extrai, tipa, classifica, exporta e valida o demonstrativo."""
    return analyze_payment_statement(
        pdf_path, output_dir, exportar_arquivos, retencao_percentual
    )


TOOLS: dict[str, tuple[dict[str, Any], Callable[..., dict[str, Any]]]] = {
    "localizar_paginas_demonstrativo": (
        {
            "name": "localizar_paginas_demonstrativo",
            "description": (
                "Localiza páginas que contêm o título DEMONSTRATIVO DE PAGAMENTOS "
                "e ao menos um identificador real de lançamento. Não usa OCR."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string", "description": "Caminho do PDF local."}
                },
                "required": ["pdf_path"],
                "additionalProperties": False,
            },
        },
        localizar_paginas_demonstrativo,
    ),
    "extrair_demonstrativo_pagamentos": (
        {
            "name": "extrair_demonstrativo_pagamentos",
            "description": (
                "Extrai a tabela pela posição das palavras, normaliza datas e valores, "
                "distingue parcelas de lançamentos administrativos, valida o total "
                "RECEBIDO e pode gerar PDF separado, JSON, CSV e Excel."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pdf_path": {"type": "string", "description": "Caminho do PDF local."},
                    "output_dir": {
                        "type": ["string", "null"],
                        "description": "Pasta de saída; se omitida, usa uma pasta ao lado do PDF.",
                    },
                    "exportar_arquivos": {
                        "type": "boolean",
                        "default": True,
                        "description": "Gera PDF separado, JSON, CSV e planilha Excel.",
                    },
                    "retencao_percentual": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100,
                        "default": 0,
                        "description": "Percentual inicial da retenção na planilha Excel.",
                    },
                },
                "required": ["pdf_path"],
                "additionalProperties": False,
            },
        },
        extrair_demonstrativo_pagamentos,
    ),
    "listar_criterios": (
        {
            "name": "listar_criterios",
            "description": (
                "Lista os critérios de correção monetária e/ou juros de mora do "
                "catálogo local do Planjud. Não acessa a rede."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["todos", "correcao", "correção", "juros"],
                        "default": "todos",
                    }
                },
                "additionalProperties": False,
            },
        },
        listar_criterios,
    ),
    "indice_disponivel": (
        {
            "name": "indice_disponivel",
            "description": (
                "Retorna início de vigência, último índice catalogado e disponibilidade "
                "do motor local para um critério de correção."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "correcao": {
                        "type": "string",
                        "default": "INPC",
                        "description": "Alias, nome ou GUID do critério.",
                    }
                },
                "additionalProperties": False,
            },
        },
        indice_disponivel,
    ),
    "calcular_correcao": (
        {
            "name": "calcular_correcao",
            "description": (
                "Calcula correção monetária de uma ou mais parcelas exclusivamente "
                "com séries locais empacotadas. Não acessa a rede e não cria registro público."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "parcelas": {
                        "type": "array",
                        "minItems": 1,
                        "items": {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "description": "VALOR:DATA[:NOME[:JUROS_MORA]]",
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "valor": {"type": ["number", "string"]},
                                        "data": {"type": "string"},
                                        "nome": {"type": "string"},
                                        "juros_mora": {"type": ["string", "null"]},
                                    },
                                    "required": ["valor", "data"],
                                    "additionalProperties": False,
                                },
                            ]
                        },
                    },
                    "correcao": {"type": "string", "default": "INPC"},
                    "data_base": {"type": ["string", "null"]},
                    "usar_cache": {"type": "boolean", "default": True},
                },
                "required": ["parcelas"],
                "additionalProperties": False,
            },
        },
        calcular_correcao,
    ),
}


def _success(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    """Processa o subconjunto do MCP necessário para descoberta e chamada de tools."""
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if request_id is None:
        return None
    if method == "initialize":
        protocol_version = params.get("protocolVersion", "2025-06-18")
        return _success(
            request_id,
            {
                "protocolVersion": protocol_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "Extrai demonstrativos pela camada textual nativa do PDF com PyMuPDF "
                    "e calcula correção monetária somente com séries locais. Não utiliza "
                    "OCR, não acessa a rede e não cria registros públicos."
                ),
            },
        )
    if method == "ping":
        return _success(request_id, {})
    if method == "tools/list":
        return _success(request_id, {"tools": [definition for definition, _ in TOOLS.values()]})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if name not in TOOLS:
            return _error(request_id, -32602, f"Ferramenta desconhecida: {name}")
        try:
            data = TOOLS[name][1](**arguments)
            text = json.dumps(data, ensure_ascii=False)
            return _success(
                request_id,
                {
                    "content": [{"type": "text", "text": text}],
                    "structuredContent": data,
                    "isError": False,
                },
            )
        except (FileNotFoundError, ValueError, TypeError) as exc:
            return _success(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        except Exception as exc:
            return _success(
                request_id,
                {
                    "content": [{"type": "text", "text": f"Falha ao processar PDF: {exc}"}],
                    "isError": True,
                },
            )
    return _error(request_id, -32601, f"Método não suportado: {method}")


def main() -> None:
    # No transporte stdio do MCP, cada mensagem JSON ocupa uma linha. Nada além
    # das respostas do protocolo é escrito em stdout.
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = handle_request(message)
        except json.JSONDecodeError as exc:
            response = _error(None, -32700, f"JSON inválido: {exc.msg}")
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
