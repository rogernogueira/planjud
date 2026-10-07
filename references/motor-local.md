# Motor local — INPC / IPCA / IGP-DI sem depender do Planjud

> Cálculo **offline** da correção monetária para os índices "simples", usando as séries
> mensais oficiais do **BACEN (SGS)**, guardadas em cache local. Elimina a dependência do
> Planjud para esses casos — e não cria registro público no sistema do tribunal.

## Escopo (o que o motor local faz e não faz)

| Faz | Não faz |
|---|---|
| Correção por **INPC**, **IPCA** e **IGP-DI** | Critérios compostos do TJTO (Débitos Gerais, Fazenda Pública, Previdenciário, TR+IPCA-E…) |
| Termos a partir de **07/1995** (pós-Plano Real) | Termos anteriores a 07/1995 |
| Juros de mora = **SEM_JUROS** | Juros de mora (qualquer regra) |
| — | **EC 136/2025**, **SELIC (EC 113/2021)** |

Se o caso sai do escopo, use `--motor planjud` (oficial — cria registro público no TJTO)
— ou `--motor auto`, que escolhe o local **quando aplicável** e cai no Planjud caso contrário.

## Convenção (validada contra o Planjud)

```
fator(termo, data_base) = Π (1 + v_m/100)   para m = MÊS DO TERMO .. MÊS DA DATA-BASE, inclusive
valor_corrigido         = valor × fator
```

O mês do termo **e** o mês da data-base entram no produto. Confirmado por reproduzir
exatamente os fatores que o Planjud devolve.

## Fonte dos índices (BACEN SGS)

| Índice | Série SGS | Endpoint |
|---|---|---|
| INPC | **188** | `https://api.bcb.gov.br/dados/serie/bcdata.sgs.188/dados?formato=json` |
| IPCA | **433** | `…/bcdata.sgs.433/dados` |
| IGP-DI | **190** | `…/bcdata.sgs.190/dados` |

A série é baixada uma vez e guardada em `~/.cache/planjud-calculo/sgs_<serie>.json`
(TTL padrão **1 dia**, ajustável com `--ttl-indice`). Depois disso, o cálculo roda **offline**.

## Validação contra o Planjud (2026-10-07)

Caso de controle: R$ 645,36 em **04/2011** → data-base **08/2026**.

| Critério | Fator local | Fator Planjud | Corrigido | |
|---|---|---|---|---|
| INPC | 2,3183389 | 2,3183389 | R$ 1.496,16 | ✔ |
| IPCA | 2,3315703 | 2,3315703 | R$ 1.504,70 | ✔ |
| IGP-DI | 2,6212235 | 2,6212235 | R$ 1.691,63 | ✔ |
| IGP-M | 2,6183396 | 2,6165830 | — | ✗ **excluído** |

**IGP-M foi excluído**: a série do BACEN (SGS 189) divergiu do que o TJTO usa (~0,07%),
mesmo sem meses faltantes — provavelmente revisão/versão distinta do FGV. Como o objetivo
é bater com o sistema oficial, o motor local **não** oferece IGP-M.

## Uso

```bash
# padrão: motor local (erro se o caso não for suportado)
uv run --with requests scripts/planjud_calc.py --correcao INPC \
    --data-base 2026-08 --parcela 645.36:2011-04-01

# forçar o motor oficial (usa a API do TJTO; cria registro público)
... --motor planjud

# deixar a ferramenta escolher (local quando possível, senão Planjud)
... --motor auto

# no MCP: parâmetro "motor" em calcular_correcao (padrão "local")
{"tool": "calcular_correcao", "args": {"parcelas": [...], "correcao": "IPCA",
                                       "data_base": "2026-08", "motor": "planjud"}}
```

## Por que o motor local é o padrão

O motor local é o **padrão** (`--motor local`): os casos que ele cobre são calculados
**offline**, sem rede e **sem criar registro público** no Planjud. Os resultados são
**idênticos** ao sistema oficial nos casos validados (tabela acima), mas a validação
cobre um recorte — por isso o motor local **recusa** (erro explícito) qualquer caso que
não saiba calcular, em vez de "adivinhar". Use:

- `--motor planjud` — força o motor **oficial** (usa a API do TJTO; cria registro público).
  Obrigatório para juros de mora, EC 136/2025, SELIC (EC 113/2021), critérios compostos
  ou termos anteriores a 07/1995.
- `--motor auto` — local quando aplicável, **senão** Planjud automaticamente.

Encare o motor local como o caminho **rápido e offline**, e o Planjud como a
**referência oficial** para tudo o que o local não cobre.

## Cache de resultados (item relacionado)

Toda chamada ao Planjud passa por um cache local por chave determinística
(`critério + parcelas + data-base + honorários/multas + EC136`), em
`~/.cache/planjud-calculo/resultados.json`, TTL padrão **30 dias**. Controlado por
`--no-cache` e `--cache-ttl`; limpe tudo com `--clear-cache`.

> Ambos os caches respeitam `PLANJUD_CACHE_DIR` (diretório base) — útil para isolar por
> projeto ou rodar em contêiner.
