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
import hashlib
import json
import os
import re
import sys
import unicodedata
from datetime import date, datetime

# O pacote unificado não importa cliente HTTP. As rotinas legadas de rede abaixo
# permanecem apenas para reaproveitar o motor matemático original e falham de
# forma fechada caso sejam chamadas diretamente.
requests = None

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


# ---------------------------------------------------------------------------
# Catálogo: snapshot embutido + cache/refresh a partir da página do sistema
# ---------------------------------------------------------------------------
def cache_dir():
    """Diretório de cache (catálogo, séries e resultados). Sobrescreva com PLANJUD_CACHE_DIR."""
    return os.environ.get("PLANJUD_CACHE_DIR") or os.path.expanduser("~/.cache/planjud-calculo")


def _catalogo_path(caminho=None):
    if caminho:
        return caminho
    return os.environ.get("PLANJUD_CATALOG") or os.path.join(cache_dir(), "catalogo.json")


def _resultados_path():
    return os.path.join(cache_dir(), "resultados.json")


def _slug(s):
    return re.sub(r"[^A-Z0-9]+", "_",
                  unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper()).strip("_")


def _extract_json_array(text, key):
    """Extrai o array JSON associado a `key`, respeitando strings (colchetes dentro de aspas)."""
    m = re.search(re.escape(key) + r"\s*:", text)
    if not m:
        return None
    j = text.find("[", m.end())
    if j < 0:
        return None
    depth, in_str, esc = 0, False, False
    for k in range(j, len(text)):
        c = text[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return json.loads(text[j:k + 1])
    return None


def extrair_opcoes_pagina(html):
    """Extrai (opcoes_correcao, opcoes_juros) do HTML da tela Create."""
    return (_extract_json_array(html, "opcoesCriterioCorrecaoMonetaria") or [],
            _extract_json_array(html, "opcoesCriterioJurosMora") or [])


def buscar_catalogo_live(base_url=DEFAULT_BASE_URL, verify=True, timeout=60):
    """Baixa a página Create e extrai as opções vivas (com datas-base atualizadas)."""
    s = requests.Session()
    s.verify = verify
    r = s.get(base_url.rstrip("/") + "/PublicoCalculoGeral/Create", timeout=timeout)
    r.raise_for_status()
    return extrair_opcoes_pagina(r.text)


def mesclar_catalogo(live_correcao, live_juros):
    """Mescla as opções vivas ao snapshot, preservando os aliases por id."""
    corr = dict(CORRECAO)
    by_id = {v[0]: k for k, v in CORRECAO.items()}
    for o in live_correcao:
        oid = o.get("id")
        if not oid:
            continue
        ini = (o.get("dataInicioCorrecao") or "")[:10] or None
        db = (o.get("dataBase") or "")[:10] or None
        if oid in by_id:
            alias = by_id[oid]
            _, oini, odb = corr[alias]
            corr[alias] = (oid, ini or oini, db or odb)
        else:
            alias = _slug(o.get("descricao") or oid)[:40] or ("ID_" + oid[:8])
            base_alias, n = alias, 2
            while alias in corr:
                alias = "%s_%d" % (base_alias, n)
                n += 1
            corr[alias] = (oid, ini, db)
    jur = dict(JUROS)
    ids_j = set(JUROS.values())
    for o in live_juros:
        oid = o.get("id")
        if not oid or oid in ids_j:
            continue
        alias = _slug(o.get("nome") or oid)[:40] or ("ID_" + oid[:8])
        base_alias, n = alias, 2
        while alias in jur:
            alias = "%s_%d" % (base_alias, n)
            n += 1
        jur[alias] = oid
        ids_j.add(oid)
    return {"correcao": corr, "juros": jur}


_CATALOGO = {"correcao": None, "juros": None}


def carregar_catalogo(caminho=None, usar_cache=True):
    """Catálogo efetivo: snapshot embutido, sobreposto pelo cache (se existir)."""
    global _CATALOGO
    if _CATALOGO["correcao"] is not None and caminho is None:
        return _CATALOGO
    corr, jur = dict(CORRECAO), dict(JUROS)
    if usar_cache:
        p = _catalogo_path(caminho)
        if os.path.exists(p):
            try:
                d = json.loads(open(p, encoding="utf-8").read())
                corr = {k: tuple(v) for k, v in d["correcao"].items()}
                jur = dict(d["juros"])
            except Exception:
                pass
    _CATALOGO = {"correcao": corr, "juros": jur}
    return _CATALOGO


def salvar_catalogo(cat, caminho=None):
    global _CATALOGO
    p = _catalogo_path(caminho)
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump({"salvo_em": datetime.now().isoformat(timespec="seconds"),
                   "correcao": {k: list(v) for k, v in cat["correcao"].items()},
                   "juros": cat["juros"]}, fh, ensure_ascii=False, indent=2)
    _CATALOGO = cat
    return p


def diferenciar_catalogo(antigo, novo):
    """Mudanças legíveis (novos critérios e datas-base alteradas)."""
    mud = []
    a, n = antigo["correcao"], novo["correcao"]
    for alias, (oid, _ini, db) in n.items():
        if alias not in a:
            mud.append("+ correção NOVO: %s (id %s)" % (alias, oid))
        elif a[alias][2] != db:
            mud.append("~ correção %s: data-base %s -> %s" % (alias, a[alias][2], db))
    aj, nj = antigo["juros"], novo["juros"]
    for alias, oid in nj.items():
        if alias not in aj:
            mud.append("+ juros NOVO: %s (id %s)" % (alias, oid))
    return mud


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
# Cache de resultados (por critério + parcelas + data-base)
# ---------------------------------------------------------------------------
def _cache_key(payload):
    rel = {
        "cj": payload["criterioCorrecaoMonetariaJurosMora"],
        "parcelas": sorted(
            (x["valor"], x["dataJurosCorrecao"], x.get("dataJurosMora"), x["nomeParcela"])
            for x in payload["listaPartesParcelas"]),
        "hon": payload.get("honorariosAdvocaticios", {}).get("tipoHonarioAdvocaticios"),
        "hons": payload.get("honorarioAdvocaticioSentenca", {}).get("tipoHonarioAdvocaticios"),
        "m523": payload.get("multaArt523"),
        "mdesc": payload.get("multaDescumprimentoObrigacao"),
        "ec": payload.get("aplicarEC136"),
    }
    s = json.dumps(rel, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _cache_ler():
    try:
        return json.loads(open(_resultados_path(), encoding="utf-8").read())
    except Exception:
        return {}


def _cache_gravar(d):
    os.makedirs(cache_dir(), exist_ok=True)
    tmp = _resultados_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False)
    os.replace(tmp, _resultados_path())


def executar_calculo(payload, base_url=DEFAULT_BASE_URL, verify=True, timeout=60,
                     use_cache=True, ttl_dias=30):
    """Executa o cálculo no Planjud, com cache local opcional por chave determinística."""
    key = _cache_key(payload) if use_cache else None
    if key:
        e = _cache_ler().get(key)
        if e:
            try:
                if (datetime.now() - datetime.fromisoformat(e["ts"])).days < ttl_dias:
                    r = dict(e["resultado"])
                    r["_cache"] = True
                    r["_cache_ts"] = e["ts"]
                    return r
            except Exception:
                pass
    res = Planjud(base_url=base_url, verify=verify, timeout=timeout).calcular(payload)
    res["_cache"] = False
    if key:
        d = _cache_ler()
        d[key] = {"ts": datetime.now().isoformat(timespec="seconds"),
                  "resultado": {k: v for k, v in res.items() if k != "_cache"}}
        _cache_gravar(d)
    return res


# ---------------------------------------------------------------------------
# Motor local — INPC/IPCA/IGP-DI via séries do BACEN (SGS) — offline após cache
# ---------------------------------------------------------------------------
SGS_SERIES = {"INPC": 188, "IPCA": 433, "IGP_DI": 190}   # validados idênticos ao Planjud
LOCAL_TERMO_MINIMO = (1995, 7)                            # restrito ao pós-Plano Real


def _sgs_path(serie):
    return os.path.join(cache_dir(), "sgs_%s.json" % serie)


def buscar_serie_sgs(serie, usar_cache=True, ttl_dias=1, timeout=60):
    """Séries mensais (%) do BACEN SGS. Guarda em cache local (padrão: 1 dia)."""
    p = _sgs_path(serie)
    if usar_cache and os.path.exists(p):
        try:
            j = json.loads(open(p, encoding="utf-8").read())
            if (datetime.now() - datetime.fromisoformat(j["salvo_em"])).days < ttl_dias:
                return {tuple(int(x) for x in k.split("-")): v for k, v in j["dados"].items()}
        except Exception:
            pass
    url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.%s/dados"
           "?formato=json&dataInicial=01/01/1995&dataFinal=31/12/2099" % serie)
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    dados = {}
    for x in r.json():
        dd, mm, yy = x["data"].split("/")
        dados[(int(yy), int(mm))] = float(x["valor"])
    if usar_cache and dados:
        os.makedirs(cache_dir(), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"salvo_em": datetime.now().isoformat(timespec="seconds"), "serie": serie,
                       "dados": {"%d-%02d" % k: v for k, v in dados.items()}}, fh, ensure_ascii=False)
        os.replace(tmp, p)
    return dados


def _brl_str(v):
    neg = v < 0
    inteiro, dec = ("%.2f" % abs(v)).split(".")
    out = ""
    while len(inteiro) > 3:
        out = "." + inteiro[-3:] + out
        inteiro = inteiro[:-3]
    return ("-R$ " if neg else "R$ ") + inteiro + out + "," + dec


def calcular_local(parcelas, ckey, data_base, usar_cache=True, ttl_indice_dias=1):
    """Corrige parcelas localmente; devolve um dict no MESMO formato bruto do Planjud.

    Fator = produto de (1 + variação/100) do MÊS DO TERMO até o MÊS DA DATA-BASE, inclusive.
    """
    serie = SGS_SERIES.get(ckey)
    if serie is None:
        raise ValueError("critério '%s' não suportado pelo motor local (disponíveis: %s)"
                         % (ckey, ", ".join(SGS_SERIES)))
    base = (data_base.year, data_base.month)
    # valida ANTES de buscar a série (permite recusar sem rede)
    for p in parcelas:
        t = (p["data"].year, p["data"].month)
        if t < LOCAL_TERMO_MINIMO:
            raise ValueError("motor local cobre apenas termos a partir de 07/1995 (recebido %02d/%d)"
                             % (p["data"].month, p["data"].year))
        if t > base:
            raise ValueError("termo %02d/%d posterior à data-base" % (p["data"].month, p["data"].year))
    d = buscar_serie_sgs(serie, usar_cache=usar_cache, ttl_dias=ttl_indice_dias)
    itens, total = [], 0.0
    for p in parcelas:
        termo = p["data"]
        t = (termo.year, termo.month)
        f = 1.0
        y, m = t
        while (y, m) <= base:
            if (y, m) not in d:
                raise ValueError("índice %s indisponível para %02d/%d" % (ckey, m, y))
            f *= 1.0 + d[(y, m)] / 100.0
            m += 1
            if m == 13:
                y, m = y + 1, 1
        corrigido = p["valor"] * f
        total += corrigido
        itens.append({
            "nomeParcela": p["nome"],
            "termoInicioCorrecaoMonetariaString": "%02d/%d" % (termo.month, termo.year),
            "termoInicioJurosMoraString": "",
            "valorParcela": p["valor"],
            "fatorCorrecao": ("%.7f" % f).replace(".", ","),
            "valorCorrigido": corrigido,
            "valorJurosMora": 0.0,
            "valorSelic": 0.0,
            "total": corrigido,
        })
    return {
        "codigoCalculo": "LOCAL-%s" % ckey,
        "dataBase": "%04d-%02d-01T00:00:00" % (data_base.year, data_base.month),
        "criterioCorrecaoMonetario": "%s — cálculo local (BACEN SGS %s)" % (ckey, serie),
        "criterioJurosMora": "Sem inclusão de juros de mora.",
        "partesParcelas": {"parcelasDetalhadoDetalhado": [{"listaPartesParcelasDetalhados": itens}]},
        "subTotal1": {"valorCorrigido": total, "valorCorrigidoString": _brl_str(total)},
        "total": {"total": total, "valorCorrigidoString": _brl_str(total)},
        "aplicarEC136": False,
        "_motor": "local",
        "_fonte": "BACEN SGS %s" % serie,
    }


def motor_efetivo(motor, ckey, jkey, parcelas, ec136, selic_cumulada):
    """Decide o motor: 'local' (padrão, offline) ou 'planjud' (oficial). 'auto' escolhe o possível."""
    if motor == "planjud":
        return "planjud"
    ok = (ckey in SGS_SERIES and jkey == "SEM_JUROS" and not ec136 and not selic_cumulada
          and all((p["data"].year, p["data"].month) >= LOCAL_TERMO_MINIMO for p in parcelas))
    if motor == "local":
        if not ok:
            raise ValueError(
                "motor local indisponível para este caso: exige critério em %s, juros SEM_JUROS, "
                "sem EC 136/SELIC e termos a partir de 07/1995. "
                "Use --motor planjud (oficial) ou --motor auto (local quando possível, senão Planjud)."
                % ", ".join(SGS_SERIES))
        return "local"
    return "local" if ok else "planjud"   # auto


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
    print(f"Motor             : {res.get('_motor', 'planjud')}"
          + ("  (do cache local)" if res.get("_cache") else ""))
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
def build_parser() -> argparse.ArgumentParser:
    """Constrói o parser da CLI (exposto para testes e integração)."""
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
    ap.add_argument("--motor", default="local", choices=["local", "planjud", "auto"],
                    help="motor de cálculo: local (padrão; INPC/IPCA/IGP-DI via BACEN, offline) ou "
                         "planjud (oficial, cria registro público) ou auto (local quando aplicável, senão Planjud)")
    ap.add_argument("--refresh", action="store_true",
                    help="atualiza o catálogo de critérios a partir do site (datas-base) e sai")
    ap.add_argument("--catalog", default=None, help="caminho de um arquivo de catálogo JSON a usar")
    ap.add_argument("--clear-cache", action="store_true", help="apaga todo o cache local e sai")
    ap.add_argument("--no-cache", action="store_true", help="não usar nem gravar o cache de resultados")
    ap.add_argument("--cache-ttl", type=int, default=30, help="validade do cache de resultados, em dias (padrão 30)")
    ap.add_argument("--ttl-indice", type=int, default=1, help="validade do cache das séries de índices, em dias (padrão 1)")
    ap.add_argument("--json", action="store_true", help="imprimir o JSON bruto do resultado")
    ap.add_argument("--dry-run", action="store_true", help="apenas montar e mostrar o payload")
    ap.add_argument("--list", action="store_true", help="listar critérios disponíveis e sair")
    return ap


def main(argv=None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)

    if args.clear_cache:
        import shutil
        shutil.rmtree(cache_dir(), ignore_errors=True)
        print(f"Cache apagado: {cache_dir()}")
        return 0

    if args.refresh:
        try:
            live_c, live_j = buscar_catalogo_live(args.base_url, verify=not args.insecure)
        except Exception as e:
            print(f"Não foi possível ler o catálogo do site: {e}", file=sys.stderr)
            return 1
        if not live_c:
            print("O site não retornou o catálogo esperado.", file=sys.stderr)
            return 1
        antigo = carregar_catalogo(args.catalog, usar_cache=True)
        novo = mesclar_catalogo(live_c, live_j)
        mud = diferenciar_catalogo(antigo, novo)
        p = salvar_catalogo(novo, args.catalog)
        print(f"Catálogo atualizado: {len(novo['correcao'])} critérios de correção, "
              f"{len(novo['juros'])} de juros  ->  {p}")
        if mud:
            print("Mudanças:")
            for m in mud:
                print("  " + m)
        else:
            print("Nenhuma mudança em relação ao catálogo atual.")
        return 0

    if args.list:
        cat = carregar_catalogo(args.catalog, usar_cache=True)
        print("CORREÇÃO MONETÁRIA (nome -> id | início | data-base):")
        for k, (i, ini, db) in cat["correcao"].items():
            print(f"  {k:<24} {i}  inicio={ini}  dataBase={db}")
        print("\nJUROS DE MORA (nome -> id):")
        for k, i in cat["juros"].items():
            print(f"  {k:<24} {i}")
        print(f"\nMotor local disponível para: {', '.join(SGS_SERIES)} (termos >= 07/1995, juros SEM_JUROS).")
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

    # critérios (catálogo efetivo: snapshot embutido + cache/refresh)
    cat = carregar_catalogo(args.catalog, usar_cache=True)
    ckey, cid = resolve(cat["correcao"], args.correcao)
    # SELIC força juros = SEM JUROS
    if ckey in SELIC_CORRECOES and _norm(args.juros) != "SEM_JUROS":
        print(f"[aviso] critério {ckey} usa SELIC; juros forçado para SEM_JUROS.", file=sys.stderr)
        jkey, jid = "SEM_JUROS", cat["juros"]["SEM_JUROS"]
    else:
        jkey, jid = resolve(cat["juros"], args.juros)

    # data-base
    if args.data_base:
        data_base = parse_date(args.data_base)
    else:
        data_base = date.today().replace(day=1)

    # valida faixa de datas
    cinfo = cat["correcao"].get(ckey)
    if cinfo and cinfo[1]:
        ini = datetime.strptime(cinfo[1], "%Y-%m-%d").date()
        for p in parcelas:
            if p["data"] < ini:
                print(f"[aviso] parcela '{p['nome']}' ({p['data']}) é anterior ao início do critério {ckey} ({ini}).", file=sys.stderr)

    # motor (planjud | local | auto)
    try:
        motor = motor_efetivo(args.motor, ckey, jkey, parcelas, args.ec136, args.selic_cumulada)
    except ValueError as e:
        print(f"[erro] {e}", file=sys.stderr)
        return 2

    payload = Planjud.build_payload(
        parcelas, cid, jid, data_base, args.processo, args.orgao,
        args.requerente, args.requerido, args.observacao,
        ec136=args.ec136, ec136_inicio=(parse_date(args.ec136_inicio) if args.ec136_inicio else None),
        ec136_pos_corte=args.ec136_pos_corte, selic_cumulada=args.selic_cumulada)

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0

    try:
        if motor == "local":
            res = calcular_local(parcelas, ckey, data_base,
                                 usar_cache=not args.no_cache, ttl_indice_dias=args.ttl_indice)
        else:
            res = executar_calculo(payload, base_url=args.base_url, verify=not args.insecure,
                                   use_cache=not args.no_cache, ttl_dias=args.cache_ttl)
    except Exception as e:
        print(f"[erro] {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        render(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
