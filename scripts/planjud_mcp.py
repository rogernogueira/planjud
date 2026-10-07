#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
planjud_mcp.py — Servidor MCP (Model Context Protocol) do Planjud / Cálculo Geral (TJTO).

Expõe o cálculo de correção monetária + juros de mora como *ferramentas* que
qualquer cliente MCP (Claude Desktop, Cursor, VS Code, Hermes, etc.) descobre e
chama automaticamente.

Ferramentas:
  - listar_criterios     (offline — catálogo local/cache)
  - indice_disponivel    (offline — catálogo local/cache)
  - atualizar_catalogo   (rede: site do Planjud)
  - calcular_correcao    (rede: Planjud; ou LOCAL via BACEN p/ INPC/IPCA/IGP-DI)

Transporte: stdio. Rodar:
    uv run --with "mcp<2" --with requests python planjud_mcp.py

Registro no Hermes (~/.hermes/config.yaml):
    mcp_servers:
      planjud:
        command: "uv"
        args: ["run","--with","mcp<2","--with","requests","python",
               "/root/.hermes/skills/productivity/planjud-calculo/scripts/planjud_mcp.py"]

NOTA: fixe `mcp<2` — no mcp 2.x o `FastMCP` foi renomeado para `MCPServer`
(`mcp.server.mcpserver`). O import abaixo já tolera as duas versões.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from typing import Any, Dict, List, Optional, Union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import planjud_calc as pc  # núcleo reutilizado (catálogo, resolução, HTTP, motores)

try:                                                          # mcp 1.x
    from mcp.server.fastmcp import FastMCP
except ImportError:                                           # pragma: no cover
    try:                                                      # mcp 2.x
        from mcp.server.mcpserver import MCPServer as FastMCP
    except ImportError as _e:
        raise SystemExit(
            "SDK MCP não encontrado. Rode com 'uv run --with \"mcp<2\" --with requests "
            "python planjud_mcp.py' (ou fixe 'mcp<2' no mcp_servers do config). Detalhe: " + str(_e))

mcp = FastMCP("planjud-calculo")

Parcela = Union[str, Dict[str, Any]]


def _err(e: BaseException) -> Dict[str, Any]:
    return {"erro": str(e)}


def _parse_parcelas(parcelas: List[Parcela]) -> List[dict]:
    out = []
    for p in parcelas:
        if isinstance(p, str):                       # "VALOR:DATA[:NOME[:juros_mora]]"
            parts = p.split(":", 3)
            d = pc.parse_parcela(":".join(parts[:3]) if len(parts) >= 3 else p)
            if len(parts) == 4 and parts[3]:
                d["juros_mora"] = pc.parse_date(parts[3])
            out.append(d)
        elif isinstance(p, dict):
            jm = p.get("juros_mora")
            v = p["valor"]
            out.append({
                "valor": float(str(v).replace(".", "").replace(",", ".")) if "," in str(v) else float(v),
                "data": pc.parse_date(str(p["data"])),
                "nome": p.get("nome") or "Parcela",
                "juros_mora": pc.parse_date(str(jm)) if jm else None,
            })
        else:
            raise ValueError(f"parcela inválida: {p!r} (use dict ou string 'VALOR:DATA[:NOME]')")
    return out


@mcp.tool()
def listar_criterios(tipo: str = "todos") -> Dict[str, Any]:
    """Lista os critérios de correção monetária e/ou juros de mora disponíveis.

    Lê o catálogo LOCAL (snapshot embutido + cache atualizado por `atualizar_catalogo`).
    Não acessa a rede.

    Args:
        tipo: "correcao", "juros" ou "todos" (padrão).

    Returns:
        Alias, id (GUID), início de vigência e data-base (último índice) de cada critério.
    """
    tipo = (tipo or "todos").lower()
    cat = pc.carregar_catalogo()
    out: Dict[str, Any] = {}
    if tipo in ("todos", "correcao", "correção"):
        out["correcao_monetaria"] = [
            {"alias": k, "id": v[0], "inicio": v[1], "data_base": v[2]}
            for k, v in cat["correcao"].items()
        ]
        out["motor_local"] = sorted(pc.SGS_SERIES)
    if tipo in ("todos", "juros"):
        out["juros_mora"] = [{"alias": k, "id": v} for k, v in cat["juros"].items()]
    return out


@mcp.tool()
def indice_disponivel(correcao: str = "INPC") -> Dict[str, Any]:
    """Retorna o início de vigência e a data-base (último índice publicado) de um critério.

    A correção NÃO avança além da data-base mesmo que se informe um mês maior.
    Use para escolher o `data_base` de `calcular_correcao`. (Offline; pode defasar —
    rode `atualizar_catalogo` para atualizar as datas-base.)

    Args:
        correcao: alias/nome/GUID do critério de correção (ex.: "INPC", "IPCA").
    """
    try:
        cat = pc.carregar_catalogo()
        ckey, cid = pc.resolve(cat["correcao"], correcao)
        if ckey in cat["correcao"]:
            _, inicio, db = cat["correcao"][ckey]
            return {"correcao": ckey, "id": cid, "inicio": inicio, "data_base": db,
                    "motor_local_disponivel": ckey in pc.SGS_SERIES,
                    "nota": "a correção não avança além da data_base (último índice publicado)"}
        return {"correcao": ckey, "id": cid, "nota": "id informado diretamente; data-base não catalogada"}
    except BaseException as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def atualizar_catalogo(base_url: str = pc.DEFAULT_BASE_URL) -> Dict[str, Any]:
    """Atualiza o catálogo de critérios (nomes, ids e datas-base) a partir do site do Planjud.

    Re-scrapeia as opções vivas da tela `Create` e mescla ao snapshot local, salvando
    em cache. Use quando `listar_criterios`/`indice_disponivel` parecerem defasados.

    Args:
        base_url: URL base do Planjud (padrão: produção TJTO).

    Returns:
        Contagem de critérios e a lista de mudanças detectadas.
    """
    try:
        live_c, live_j = pc.buscar_catalogo_live(base_url)
        if not live_c:
            return {"erro": "o site não retornou o catálogo esperado"}
        antigo = pc.carregar_catalogo()
        novo = pc.mesclar_catalogo(live_c, live_j)
        mud = pc.diferenciar_catalogo(antigo, novo)
        caminho = pc.salvar_catalogo(novo)
        return {"atualizado": True, "caminho": caminho,
                "criterios_correcao": len(novo["correcao"]),
                "criterios_juros": len(novo["juros"]),
                "mudancas": mud or ["nenhuma"]}
    except BaseException as e:  # noqa: BLE001
        return _err(e)


@mcp.tool()
def calcular_correcao(
    parcelas: List[Parcela],
    correcao: str = "INPC",
    juros: str = "SEM_JUROS",
    data_base: Optional[str] = None,
    juros_mora: Optional[str] = None,
    motor: str = "planjud",
    processo: Optional[str] = None,
    orgao: Optional[str] = None,
    requerente: Optional[str] = None,
    requerido: Optional[str] = None,
    observacao: str = "",
    ec136: bool = False,
    ec136_inicio: Optional[str] = None,
    ec136_pos_corte: str = "EC136",
    selic_cumulada: bool = False,
    usar_cache: bool = True,
) -> Dict[str, Any]:
    """Calcula a correção monetária (e juros de mora) de uma ou mais parcelas pelo Planjud/TJTO.

    Args:
        parcelas: lista de parcelas. Cada item é um dict {"valor": 645.36,
            "data": "2011-04-01", "nome": "Aluguel", "juros_mora": "2011-04-01"}
            ou a string "VALOR:DATA[:NOME]". A `data` é o termo inicial da
            correção (mês do valor). Aceita YYYY-MM-DD, YYYY-MM, MM/YYYY, DD/MM/YYYY.
        correcao: critério de correção (alias, nome ou GUID). Padrão "INPC".
        juros: critério de juros de mora (padrão "SEM_JUROS").
        data_base: mês/ano da atualização (ex.: "2026-08"). Se omitido, usa o mês
            atual. A correção capa no último índice publicado.
        juros_mora: termo inicial dos juros aplicado a todas as parcelas sem o seu.
            Obrigatório para haver juros (senão = R$ 0,00).
        motor: "planjud" (oficial, padrão) | "local" (INPC/IPCA/IGP-DI via BACEN,
            offline após cache) | "auto" (local quando aplicável, senão Planjud).
        processo, orgao, requerente, requerido, observacao: metadados opcionais.
        ec136: aplica o regime da EC 136/2025 (Prov. 207/CNJ). Força o motor Planjud.
        ec136_inicio: início da EC 136 (mês/ano); padrão 08/2025.
        ec136_pos_corte: "EC136" ou "CODIGO_CIVIL".
        selic_cumulada: cálculo cumulado com SELIC (EC 113/2021).
        usar_cache: reaproveita resultados já calculados (padrão True).

    Returns:
        Dicionário com `codigo_calculo`, `data_base`, critérios, `motor`
        (planjud|local), `de_cache`, `parcelas` (valor, fator_correcao,
        valor_corrigido, valor_juros_mora, valor_selic, total), `total_correcao`
        e `total_geral` (em reais).
    """
    try:
        if not parcelas:
            return {"erro": "informe ao menos uma parcela"}
        ps = _parse_parcelas(parcelas)
        if juros_mora:
            jm = pc.parse_date(juros_mora)
            for p in ps:
                if not p.get("juros_mora"):
                    p["juros_mora"] = jm

        cat = pc.carregar_catalogo()
        ckey, cid = pc.resolve(cat["correcao"], correcao)
        if ckey in pc.SELIC_CORRECOES and pc._norm(juros) != "SEM_JUROS":
            jkey, jid = "SEM_JUROS", cat["juros"]["SEM_JUROS"]
        else:
            jkey, jid = pc.resolve(cat["juros"], juros)

        db = pc.parse_date(data_base) if data_base else date.today().replace(day=1)
        motor_ef = pc.motor_efetivo(motor, ckey, jkey, ps, ec136, selic_cumulada)

        if motor_ef == "local":
            res = pc.calcular_local(ps, ckey, db, usar_cache=usar_cache)
        else:
            payload = pc.Planjud.build_payload(
                ps, cid, jid, db, processo, orgao, requerente, requerido, observacao,
                ec136=ec136,
                ec136_inicio=(pc.parse_date(ec136_inicio) if ec136_inicio else None),
                ec136_pos_corte=ec136_pos_corte, selic_cumulada=selic_cumulada)
            res = pc.executar_calculo(payload, use_cache=usar_cache)

        out = pc.extrair_resultado(res)
        out["motor"] = res.get("_motor", "planjud")
        out["de_cache"] = bool(res.get("_cache"))
        if res.get("_fonte"):
            out["fonte"] = res["_fonte"]
        out["parametros"] = {
            "correcao": ckey, "juros_mora": jkey,
            "data_base_solicitada": f"{db.year:04d}-{db.month:02d}",
        }
        return out
    except BaseException as e:  # noqa: BLE001
        return _err(e)


def main() -> int:
    """Ponto de entrada (console script `planjud-mcp` ou execução direta)."""
    mcp.run()  # transporte stdio por padrão
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
