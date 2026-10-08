from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from . import _planjud_calc as pc


OFFLINE_SERIES_DIR = Path(__file__).with_name("data")


def _load_bundled_series(
    series: int, usar_cache: bool = True, ttl_dias: int = 1, timeout: int = 60
) -> dict[tuple[int, int], float]:
    """Lê o snapshot empacotado; nunca consulta BACEN ou qualquer outro serviço."""
    del usar_cache, ttl_dias, timeout
    path = OFFLINE_SERIES_DIR / f"sgs_{series}.json"
    if not path.is_file():
        raise ValueError(f"série offline SGS {series} não está incluída no pacote")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        tuple(int(part) for part in key.split("-")): float(value)
        for key, value in payload["dados"].items()
    }


# O motor original busca o BACEN quando o cache expira. No MCP unificado essa
# função é substituída pelo snapshot empacotado, garantindo operação sem rede.
pc.buscar_serie_sgs = _load_bundled_series


def _error(exc: BaseException) -> dict[str, Any]:
    return {"erro": str(exc)}


def _parse_installments(items: list[str | dict[str, Any]]) -> list[dict[str, Any]]:
    parsed = []
    for item in items:
        if isinstance(item, str):
            parts = item.split(":", 3)
            installment = pc.parse_parcela(":".join(parts[:3]) if len(parts) >= 3 else item)
            if len(parts) == 4 and parts[3]:
                installment["juros_mora"] = pc.parse_date(parts[3])
            parsed.append(installment)
        elif isinstance(item, dict):
            late_interest = item.get("juros_mora")
            value = item["valor"]
            parsed.append(
                {
                    "valor": (
                        float(str(value).replace(".", "").replace(",", "."))
                        if "," in str(value)
                        else float(value)
                    ),
                    "data": pc.parse_date(str(item["data"])),
                    "nome": item.get("nome") or "Parcela",
                    "juros_mora": pc.parse_date(str(late_interest)) if late_interest else None,
                }
            )
        else:
            raise ValueError(
                f"parcela inválida: {item!r} (use objeto ou string 'VALOR:DATA[:NOME]')"
            )
    return parsed


def listar_criterios(tipo: str = "todos") -> dict[str, Any]:
    """Lista critérios de correção e/ou juros usando o catálogo local."""
    selected = (tipo or "todos").lower()
    catalog = pc.carregar_catalogo()
    result: dict[str, Any] = {}
    if selected in ("todos", "correcao", "correção"):
        result["correcao_monetaria"] = [
            {"alias": key, "id": value[0], "inicio": value[1], "data_base": value[2]}
            for key, value in catalog["correcao"].items()
        ]
        result["motor_local"] = sorted(pc.SGS_SERIES)
    if selected in ("todos", "juros"):
        result["juros_mora"] = [
            {"alias": key, "id": value} for key, value in catalog["juros"].items()
        ]
    return result


def indice_disponivel(correcao: str = "INPC") -> dict[str, Any]:
    """Informa vigência, último índice catalogado e suporte pelo motor local."""
    try:
        catalog = pc.carregar_catalogo()
        key, identifier = pc.resolve(catalog["correcao"], correcao)
        if key in catalog["correcao"]:
            _, start, base_date = catalog["correcao"][key]
            series = pc.SGS_SERIES.get(key)
            if series is not None:
                last_year, last_month = max(_load_bundled_series(series))
                base_date = f"{last_year:04d}-{last_month:02d}-01"
            return {
                "correcao": key,
                "id": identifier,
                "inicio": start,
                "data_base": base_date,
                "motor_local_disponivel": key in pc.SGS_SERIES,
                "fonte": f"snapshot offline BACEN SGS {series}" if series else "catálogo local",
                "nota": "a correção não avança além da data_base (último índice publicado)",
            }
        return {
            "correcao": key,
            "id": identifier,
            "nota": "id informado diretamente; data-base não catalogada",
        }
    except BaseException as exc:
        return _error(exc)


def calcular_correcao(
    parcelas: list[str | dict[str, Any]],
    correcao: str = "INPC",
    data_base: str | None = None,
    usar_cache: bool = True,
) -> dict[str, Any]:
    """Calcula correção monetária exclusivamente com séries locais empacotadas."""
    try:
        if not parcelas:
            return {"erro": "informe ao menos uma parcela"}
        parsed = _parse_installments(parcelas)

        catalog = pc.carregar_catalogo()
        correction_key, _ = pc.resolve(catalog["correcao"], correcao)
        if data_base:
            base_date = pc.parse_date(data_base)
        else:
            series = pc.SGS_SERIES.get(correction_key)
            if series is None:
                raise ValueError(
                    f"critério '{correction_key}' não está disponível no motor offline"
                )
            last_year, last_month = max(_load_bundled_series(series))
            base_date = date(last_year, last_month, 1)
        pc.motor_efetivo("local", correction_key, "SEM_JUROS", parsed, False, False)
        raw = pc.calcular_local(parsed, correction_key, base_date, usar_cache=usar_cache)

        result = pc.extrair_resultado(raw)
        result["motor"] = raw.get("_motor", "local")
        result["de_cache"] = bool(raw.get("_cache"))
        if raw.get("_fonte"):
            result["fonte"] = raw["_fonte"]
        result["parametros"] = {
            "correcao": correction_key,
            "juros_mora": "SEM_JUROS",
            "data_base_solicitada": f"{base_date.year:04d}-{base_date.month:02d}",
        }
        result["modo_rede"] = "desativado"
        result["registro_publico"] = False
        return result
    except BaseException as exc:
        return _error(exc)
