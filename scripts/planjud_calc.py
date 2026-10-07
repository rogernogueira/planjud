#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
planjud_calc.py — Atualização/correção monteária de valores no sistema
Planjud / Cálculo Geral (TJTO), via replay da API pública.

Suporta MÚLTIPLAS PARCELAS (por linha de comando ou arquivo CSV).

Exemplos
--------
# Uma parcela (valor pago em 01/04/2011, corrigido pelo INPC)
python planjud_calc.py --correcao INPC --juros SEM_JUROS --data-base 2026-08 \
    --parcela 645.36:2011-04-01

# Várias parcelas
python planjud_calc.py --correcao INPC \
    --parcela 645.36:2011-04-01:Aluguel \
    --parcela 1000:2015-06-01:Danos \
    --parcela 250.50:03/2018

# Várias parcelas via CSV (colunas: valor,data,nome)
python planjud_calc.py --correcao IPCA --csv parcelas.csv --json

# Listar critérios disponíveis
python planjud_calc.py --list
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
import uuid
from datetime import date, datetime

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("É necessário o pacote 'requests'. Instale com: uv pip install requests  (ou pip install requests)")

DEFAULT_BASE_URL = "https://app.tjto.edu.br"  # placeholder (sobrescrito abaixo)
DEFAULT_BASE_URL = "https://app.tjto.jus.br/planjud"

# ---------------------------------------------------------------------------
# Catálogo de dados de referência (extraído do sistema em 2026-10)
# ---------------------------------------------------------------------------
# troca/alias -> (id, inicio_correcao "YYYY-MM-DD", data_base "YYYY-MM-DD")
CORRECAO = {
    "DEBITOS_GERAIS":        ("6e05166d-8733-4b73-b0eb-0589fcfc88a8", "1964-10-01", "2026-08-01"),
    "FAZENDA_PUBLICA":       ("80760894-3d39-4344-8792-2a2c7a27e926", "1964-10-01", "2026-09-01"),
    "DEBITOS_GERAIS_IPCA":   ("55fb653f-954c-4c42-95c2-ac8578f71b19", "1964-10-01", "2026-08-01"),
    "PREVIDENCIARIO":        ("546edcd7-ea0f-4c05-9272-84f422c7217b", "1964-10-01", "2026-08-01"),
    "CONDENATORIAS_JF":      ("cea51753-4dcc-424b-b8af-c5a20bf4d599", "1964-10-01", "2026-09-01"),
    "IGP_DI":                ("8a20e64b-5cc4-43fe-80d1-f025e8ba15e7", "1964-10-01", "2026-09-01"),
    "IGP_M":                 ("06fc9bab-70c4-4286-80fc-1d560f4e39a6", "1989-06-01", "2026-09-01"),
    "INCC":                  ("6afc9ce7-3997-4a35-ab94-108ef301d110", "1964-10-01", "2026-09-01"),
    "INPC":                  ("b17bff33-e054-48b4-bc47-759885db09e7", "1979-04-01", "2026-08-01"),
    "IPCA":                  ("a4b46250-810a-4c58-8078-b721f9ca82c3", "1980-01-01", "2026-08-01"),
    "IPCA_E":                ("eac4cc31-c420-49c3-b474-cf1284c61770", "1992-01-01", "2026-09-01"),
    "SELIC_FAZENDA":         ("e2b28c79-3671-427b-a4a5-e83be9ac7ea7", "2021-12-01", "2026-09-01"),
    "SELIC_TRIBUTARIO":      ("f88f3e52-6b91-47ed-9a8b-102cf5e2ad10", "1995-01-01", "2026-10-01"),
    "TR_IPCA_E":             ("de424b12-8b1d-4c07-9014-4ac419dc3463", "1994-07-01", "2026-09-01"),
    "IGPM_IPCA":             ("a2a688c6-8511-4f78-a642-6ca00eccac46", "1994-07-01", "2026-08-01"),
    "TR":                    ("7de9d3d7-912f-42b0-81d7-9b38ae83332f", "1994-07-01", "2026-10-01"),
}

JUROS = {
    "SEM_JUROS":             "19762eda-1aad-4b9f-9d57-f2ea46598b9f",
    "JUROS_6_12":            "3fbfea4d-079a-46e8-9f48-ec65d0fa9d27",
    "JUROS_6":               "bb6bbf4b-c2b9-4fc3-84b0-c3a9b7483437",
    "JUROS_12":              "6599f453-b9aa-4fa0-afea-65a502242837",
    "JUROS_12_6":            "c8b23932-54ad-41a6-8a79-d0501a746a1a",
    "JUROS_12_POUPANCA":     "e0f73128-f6df-4576-bfe2-4e2f52858996",
    "FAZENDA_GERAL":         "86de7d17-ba2f-4c07-a23a-fd9bcabce37b",
    "FAZENDA_SERVIDORES":    "56d7a4e7-91db-47f5-ba47-0caee92c9a30",
    "FAZENDA_PREVIDENCIARIO":"83512a76-57f9-4cf4-b8c8-f645f41434d9",
    "FAZENDA_POUPANCA":      "b84c22f4-5348-41c1-8e96-b7a2695e1cfb",
    "TAXA_LEGAL":            "7a7abf7c-fce1-46e4-aa36-1e5698008a91",
    "JUROS_6_12_TL":         "e32593ba-7d11-4b37-9554-31ed9cf66010",
}

SELIC_CORRECOES = {"SELIC_FAZENDA", "SELIC_TRIBUTARIO"}


def _norm(s: str) -> str:
    """Normaliza para busca: maiúsculas, sem acento, separadores -> '_'."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").upper()
    return s


def resolve(catalog: dict, value: str) -> tuple[str, str]:
    """Resolve nome/alias/id -> (chave, id). Aceita id (GUID) direto."""
    if re.fullmatch(r"[0-9a-fA-F-]{36}", value):
        return ("(id informado)", value)
    key = _norm(value)
    if key in catalog:
        return key, catalog[key][0] if isinstance(catalog[key], tuple) else catalog[key]
    # match parcial único
    hits = [k for k in catalog if key in k or k in key]
    if len(hits) == 1:
        v = catalog[hits[0]]
        return hits[0], v[0] if isinstance(v, tuple) else v
    if not hits:
        raise SystemExit(f"Critério não encontrado: {value!r}. Use --list para ver as opções.")
    raise SystemExit(f"Critério ambíguo {value!r}: {sorted(hits)}. Use --list.")


def parse_date(s: str) -> date:
    """Aceita YYYY-MM-DD, YYYY-MM, MM/YYYY, DD/MM/YYYY."""
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m", "%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    raise SystemExit(f"Data inválida: {s!r} (use YYYY-MM-DD, YYYY-MM, MM/YYYY ou DD/MM/YYYY)")


def iso_month_first(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}-01T00:00:00"


def parse_parcela(spec: str) -> dict:
    """Formato: VALOR:DATA[:NOME]  (NOME opcional)."""
    parts = spec.split(":", 2)
    if len(parts) < 2:
        raise SystemExit(f"Parcela inválida: {spec!r} (esperado VALOR:DATA[:NOME])")
    val_s, dt_s = parts[0], parts[1]
    nome = parts[2] if len(parts) > 2 else "Parcela"
    try:
        valor = float(val_s.replace(".", "").replace(",", ".") if "," in val_s else val_s)
    except ValueError:
        raise SystemExit(f"Valor inválido em {spec!r}: {val_s!r}")
    return {"valor": valor, "data": parse_date(dt_s), "nome": nome, "juros_mora": None}


def _to_float(s: str) -> float:
    s = str(s).strip()
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def load_csv(path: str) -> list[dict]:
    """CSV com colunas valor,data[,nome][,juros_mora]. Cabeçalho opcional.

    Se a 1ª linha contiver 'valor'/'data', o mapeamento é feito pelos nomes das
    colunas (aceita acentos e variações); caso contrário assume-se posicional.
    """
    out = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = [r for r in csv.reader(fh) if r and any(c.strip() for c in r)]
    if not rows:
        return out
    header = [_norm(c) for c in rows[0]]
    has_header = "VALOR" in header and "DATA" in header
    if has_header:
        def col(name, default=None):
            return header.index(name) if name in header else default
        i_val, i_dt, i_nome, i_jm = col("VALOR"), col("DATA"), col("NOME", col("DESCRICAO")), col("JUROS_MORA", col("JUROS"))
        body = rows[1:]
    else:
        i_val, i_dt, i_nome, i_jm = 0, 1, (2 if len(rows[0]) > 2 else None), None
        body = rows
    for row in body:
        def get(i):
            return row[i].strip() if (i is not None and i < len(row) and row[i].strip()) else None
        if get(i_val) is None or get(i_dt) is None:
            continue
        out.append({
            "valor": _to_float(get(i_val)),
            "data": parse_date(get(i_dt)),
            "nome": get(i_nome) or "Parcela",
            "juros_mora": parse_date(get(i_jm)) if get(i_jm) else None,
        })
    return out


# ---------------------------------------------------------------------------
# Integração HTTP
# ---------------------------------------------------------------------------
class Planjud:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, verify: bool = True, timeout: int = 60):
        self.base = base_url.rstrip("/")
        self.timeout = timeout
        self.s = requests.Session()
        self.s.verify = verify
        self.s.headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "planjud-calc/1.0",
        })

    def _handshake(self) -> None:
        """Obtém cookies (antiforgery/sessão) da página Create."""
        self.s.get(f"{self.base}/PublicoCalculoGeral/Create", timeout=self.timeout)

    def calcular(self, payload: dict) -> dict:
        self._handshake()
        r = self.s.post(f"{self.base}/PublicoCalculoGeral/Create",
                        json=payload, timeout=self.timeout)
        if r.status_code == 400:
            try:
                errs = r.json()["error"]["Errors"]
                msgs = [e.get("errorMessage") or e.get("key") for e in errs]
            except Exception:
                msgs = [r.text[:500]]
            raise SystemExit("Erro de validação do Planjud:\n  - " + "\n  - ".join(map(str, msgs)))
        r.raise_for_status()
        calc_id = r.json()
        rr = self.s.get(
            f"{self.base}/PublicoCalculoGeral/VisualizarCalculoInformacaoCalculo/{calc_id}",
            timeout=self.timeout)
        rr.raise_for_status()
        return rr.json()

    @staticmethod
    def build_payload(parcelas, criterio_id, juros_id, data_base: date,
                      processo=None, orgao=None, requerente=None, requerido=None,
                      observacao="", ec136=False, ec136_inicio=None,
                      ec136_pos_corte=None, selic_cumulada=False) -> dict:
        lista = []
        for i, p in enumerate(parcelas, start=1):
            lista.append({
                "seq": i,
                "dataJurosCorrecao": iso_month_first(p["data"]),
                "dataJurosMora": (iso_month_first(p["juros_mora"]) if p.get("juros_mora") else None),
                "valor": round(float(p["valor"]), 2),
                "nomeParcela": p["nome"],
                "descricao": "",
                "percentual": "",
                "tipoParteParcela": 1,
                "id": "",
            })
        return {
            "id": None, "seq": 0, "codigoCalculo": "",
            "informacaoProcesso": {
                "numeroProcesso": processo, "orgaoJulgador": orgao,
                "requerente": requerente, "requerido": requerido,
            },
            "criterioCorrecaoMonetariaJurosMora": {
                "criterioCorrecaoMonetaria": criterio_id,
                "criterioJurosMora": juros_id,
                "atualizacaoAteDataBase": iso_month_first(data_base),
                "decisaoSelicFazenda": 2,
                "calculoCumuladoComSelic": bool(selic_cumulada),
                "permitirDeflacao": False,
                "aplicarEC136": bool(ec136),
                "inicioAplicacaoEC136": (iso_month_first(ec136_inicio) if ec136_inicio else None),
                "criterioPosCorteEC136": (ec136_pos_corte if ec136 else None),
            },
            "multaDescumprimentoObrigacao": {
                "AplicaMultaDescumprimentoAcordoObrigacao": False, "PercentualMulta": None},
            "honorariosAdvocaticios": {
                "id": None, "tipoHonarioAdvocaticios": 1, "percentual": 0, "valor": 0,
                "dataFixacaoAjuizamentoIncidencia": None, "dataJurosMora": None,
                "escalonado": False, "honorariosEscalonados": []},
            "honorarioAdvocaticioSentenca": {
                "percentual": 0, "valor": 0, "tipoHonarioAdvocaticios": 1,
                "dataFixacaoAjuizamentoIncidencia": None, "dataJurosMora": None,
                "honorariosEscalonados": [], "escalonado": False},
            "multaArt523": {"Multa10Porcento": False, "HonorariosAdvocaticios": False},
            "listaPartesParcelas": lista,
            "listaOutrasVerbas": [], "listaAstreintes": [],
            "observacao": observacao,
            "aplicarEC136": bool(ec136),
            "inicioAplicacaoEC136": (iso_month_first(ec136_inicio) if ec136_inicio else None),
            "criterioPosCorteEC136": (ec136_pos_corte if ec136 else None),
        }


# ---------------------------------------------------------------------------
# Apresentação
# ---------------------------------------------------------------------------
def extrair_resultado(res: dict) -> dict:
    """Normaliza o JSON bruto do Planjud num dicionário estável (para MCP/agentes)."""
    det = res.get("partesParcelas", {}).get("parcelasDetalhadoDetalhado", [])
    parcelas = []
    for grupo in det:
        for it in grupo.get("listaPartesParcelasDetalhados", []):
            parcelas.append({
                "nome": it.get("nomeParcela"),
                "termo_correcao": it.get("termoInicioCorrecaoMonetariaString"),
                "termo_juros_mora": it.get("termoInicioJurosMoraString") or None,
                "valor": it.get("valorParcela"),
                "fator_correcao": it.get("fatorCorrecao"),
                "valor_corrigido": it.get("valorCorrigido"),
                "valor_juros_mora": it.get("valorJurosMora"),
                "valor_selic": it.get("valorSelic"),
                "total": it.get("total"),
            })
    t = res.get("total", {}) or {}
    return {
        "codigo_calculo": res.get("codigoCalculo"),
        "data_base": str(res.get("dataBase"))[:7],
        "criterio_correcao": res.get("criterioCorrecaoMonetario"),
        "criterio_juros_mora": res.get("criterioJurosMora"),
        "parcelas": parcelas,
        "total_correcao": (res.get("subTotal1") or {}).get("valorCorrigido"),
        "total_geral": t.get("total"),
        "aplicar_ec136": bool(res.get("aplicarEC136")),
    }


def _num(x) -> float:
    return float(x) if x is not None else 0.0


def brl(x) -> str:
    s = f"{_num(x):,.2f}"
    return "R$ " + s.replace(",", "X").replace(".", ",").replace("X", ".")


def render(res: dict) -> None:
    det = res.get("partesParcelas", {}).get("parcelasDetalhadoDetalhado", [])
    print(f"Código do cálculo : {res.get('codigoCalculo')}")
    print(f"Data-base         : {str(res.get('dataBase'))[:7]}")
    print(f"Correção          : {res.get('criterioCorrecaoMonetario')}")
    print(f"Juros de mora     : {res.get('criterioJurosMora')}")
    print("-" * 96)
    print(f"{'Item':>4}  {'Nome':<22} {'Termo':<8} {'Juros':<8} {'Valor':>12} {'Fator':>11} {'Corrigido':>14} {'Juros R$':>11} {'Total':>14}")
    print("-" * 96)
    tot = 0.0
    idx = 0
    for grupo in det:
        for it in grupo.get("listaPartesParcelasDetalhados", []):
            idx += 1
            tot += _num(it.get("total"))
            print(f"{idx:>4}  {str(it.get('nomeParcela',''))[:22]:<22} "
                  f"{str(it.get('termoInicioCorrecaoMonetariaString','')):<8} "
                  f"{str(it.get('termoInicioJurosMoraString','') or '-'):<8} "
                  f"{brl(it.get('valorParcela')):>12} {str(it.get('fatorCorrecao','')):>11} "
                  f"{brl(it.get('valorCorrigido')):>14} {brl(it.get('valorJurosMora')):>11} "
                  f"{brl(it.get('total')):>14}")
    print("-" * 96)
    t = res.get("total", {})
    print(f"TOTAL GERAL: {ord_brl(t.get('total'))}   (subtotal partes/parcelas: {res.get('subTotal1',{}).get('valorCorrigidoString')})")
    if res.get("aplicarEC136"):
        print("⚠  Regime EC 136/2025 aplicado.")


def ord_brl(x) -> str:
    return brl(x)


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Correção/atualização monetária de valores via Planjud (TJTO) — múltiplas parcelas.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--correcao", default="INPC", help="critério de correção (nome/alias/id). Padrão: INPC")
    ap.add_argument("--juros", default="SEM_JUROS", help="critério de juros de mora (nome/alias/id). Padrão: SEM_JUROS")
    ap.add_argument("--data-base", default=None, help="data-base mês/ano (YYYY-MM, YYYY-MM-DD ou MM/YYYY). Padrão: mês atual")
    ap.add_argument("--parcela", action="append", default=[], metavar="VALOR:DATA[:NOME]",
                    help="parcela (repetível). Ex.: 645.36:2011-04-01:Aluguel")
    ap.add_argument("--csv", help="arquivo CSV com colunas valor,data[,nome][,juros_mora]")
    ap.add_argument("--juros-mora", default=None,
                    help="termo inicial dos juros de mora (mês/ano) aplicado a todas as parcelas")
    ap.add_argument("--processo", default=None)
    ap.add_argument("--orgao", default=None)
    ap.add_argument("--requerente", default=None)
    ap.add_argument("--requerido", default=None)
    ap.add_argument("--observacao", default="")
    ap.add_argument("--ec136", action="store_true", help="aplicar EC 136/2025 (Prov. 207/CNJ)")
    ap.add_argument("--ec136-inicio", default=None, help="início da aplicação da EC 136 (mês/ano)")
    ap.add_argument("--ec136-pos-corte", default="EC136", choices=["EC136", "CODIGO_CIVIL"])
    ap.add_argument("--selic-cumulada", action="store_true", help="cálculo cumulado com SELIC (EC 113/21)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--insecure", action="store_true", help="não validar o certificado TLS")
    ap.add_argument("--json", action="store_true", help="imprimir o JSON bruto do resultado")
    ap.add_argument("--dry-run", action="store_true", help="apenas montar e mostrar o payload")
    ap.add_argument("--list", action="store_true", help="listar critérios disponíveis e sair")
    args = ap.parse_args(argv)

    if args.list:
        print("CORREÇÃO MONETÁRIA (nome -> id | início | data-base):")
        for k, (i, ini, db) in CORRECAO.items():
            print(f"  {k:<22} {i}  inicio={ini}  dataBase={db}")
        print("\nJUROS DE MORA (nome -> id):")
        for k, i in JUROS.items():
            print(f"  {k:<22} {i}")
        return 0

    # parcelas
    parcelas = [parse_parcela(p) for p in args.parcela]
    if args.csv:
        parcelas += load_csv(args.csv)
    if not parcelas:
        ap.error("informe ao menos uma parcela (--parcela ou --csv)")
    if args.juros_mora:
        jm = parse_date(args.juros_mora)
        for p in parcelas:
            if not p.get("juros_mora"):
                p["juros_mora"] = jm

    # critérios
    ckey, cid = resolve(CORRECAO, args.correcao)
    # SELIC força juros = SEM JUROS
    if ckey in SELIC_CORRECOES and _norm(args.juros) != "SEM_JUROS":
        print(f"[aviso] critério {ckey} usa SELIC; juros forçado para SEM_JUROS.", file=sys.stderr)
        jkey, jid = "SEM_JUROS", JUROS["SEM_JUROS"]
    else:
        jkey, jid = resolve(JUROS, args.juros)

    # data-base
    if args.data_base:
        data_base = parse_date(args.data_base)
    else:
        data_base = date.today().replace(day=1)

    # valida faixa de datas
    if ckey in CORRECAO:
        ini = datetime.strptime(CORRECAO[ckey][1], "%Y-%m-%d").date()
        for p in parcelas:
            if p["data"] < ini:
                print(f"[aviso] parcela '{p['nome']}' ({p['data']}) é anterior ao início do critério {ckey} ({ini}).", file=sys.stderr)

    payload = Planjud.build_payload(
        parcelas, cid, jid, data_base, args.processo, args.orgao,
        args.requerente, args.requerido, args.observacao,
        ec136=args.ec136, ec136_inicio=(parse_date(args.ec136_inicio) if args.ec136_inicio else None),
        ec136_pos_corte=args.ec136_pos_corte, selic_cumulada=args.selic_cumulada)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    pj = Planjud(base_url=args.base_url, verify=not args.insecure)
    res = pj.calcular(payload)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        render(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
