# Planjud — Cálculo Geral (TJTO) · ferramenta de correção

> **Ferramenta não oficial** para calcular **correção monetária + juros de mora** pelo
> sistema **Planjud / Cálculo Geral** do **Tribunal de Justiça do Tocantins (TJTO)**,
> replicando a requisição que o formulário público do sistema envia.
> CLI em Python + **servidor MCP** (plugável em qualquer agente de IA).

- **Sistema-alvo:** `https://app.tjto.jus.br/planjud` — módulo Cálculo Geral (v5.0.19.7)
- **Índices suportados:** INPC, IPCA, IPCA-E, IGP-M, IGP-DI, INCC, TR, SELIC (EC 113/21),
  Débitos Gerais, Fazenda Pública, Previdenciário, Débitos Gerais + IPCA (Lei 14.905/2024)…
- **Regimes especiais:** EC 113/2021 (SELIC), EC 136/2025 (Prov. 207/CNJ), Lei 14.905/2024, Taxa Legal (art. 406, §1º, CC)
- **Múltiplas parcelas** por linha de comando ou CSV.
- **Motor local (padrão)** — INPC/IPCA/IGP-DI calculados **offline** via séries do BACEN, sem criar registro público; o motor oficial do Planjud fica a um `--motor planjud`. Inclui **cache** de resultados e **refresh** do catálogo a partir do site.

> ⚠️ **Aviso:** este projeto **não é** um produto do TJTO nem da CRP Tecnologia. Ele usa a
> API pública do módulo. Ao usar o **motor Planjud** (`--motor planjud`/`auto`), **cada
> execução cria um registro de cálculo público** no sistema do tribunal (retorna um código).
> Os valores são informativos — **não substituem** o cálculo oficial nem a conferência por
> um(a) contador(a) judicial.

---

## Requisitos

- Python 3.9+
- [`uv`](https://docs.astral.sh/uv/) (recomendado) ou `pip`
- Acesso de rede a `app.tjto.jus.br` (TLS válido)

## Instalação

```bash
# via uv (sem instalar nada globalmente)
uv run --with requests scripts/planjud_calc.py --help

# ou instalando o pacote
pip install .            # CLI
pip install ".[mcp]"     # CLI + servidor MCP
```

## Uso — CLI

```bash
# parcela única — R$ 645,36 pago em 01/04/2011 corrigido pelo INPC
uv run --with requests scripts/planjud_calc.py \
    --correcao INPC --data-base 2026-08 --parcela 645.36:2011-04-01

# VÁRIAS parcelas (VALOR:DATA[:NOME])
uv run --with requests scripts/planjud_calc.py --correcao INPC --data-base 2026-08 \
    --parcela 645.36:2011-04-01:Aluguel \
    --parcela 1000:2015-06-01:Danos \
    --parcela 250.50:03/2018

# CSV (colunas: valor,data[,nome][,juros_mora])
uv run --with requests scripts/planjud_calc.py --correcao IPCA --csv examples/parcelas.csv

# juros de mora (termo inicial por parcela; sem termo => R$ 0,00)
#   juros não é coberto pelo motor local (padrão) -> use --motor planjud
uv run --with requests scripts/planjud_calc.py --correcao FAZENDA_PUBLICA \
    --juros FAZENDA_GERAL --juros-mora 2011-04 --parcela 645.36:2011-04-01 --motor planjud

# auxiliares
... --list      # lista todos os critérios (nome → GUID)
... --dry-run   # mostra o payload JSON sem enviar
... --json      # imprime o JSON bruto do resultado
```

Formatos de data aceitos: `YYYY-MM-DD`, `YYYY-MM`, `MM/YYYY`, `DD/MM/YYYY`.
Valor aceita `645.36` ou `645,36`.

### Dois detalhes que mudam o resultado

1. **Data-base** (`--data-base`): o sistema aceita o mês informado, mas o índice só existe
   até o **último publicado** — passar um mês maior **não altera o fator**. Para "até hoje",
   informe o **mês atual**.
2. **Juros de mora exige termo inicial por parcela** (`--juros-mora` ou coluna `juros_mora`).
   Sem termo, os juros resultam em **R$ 0,00**.

## Motor local, cache e refresh do catálogo

**Motor local (padrão)** calcula a correção **sem depender do Planjud** para
**INPC, IPCA e IGP-DI** (termos ≥ 07/1995), usando as séries mensais do **BACEN (SGS)** —
baixadas uma vez e cacheadas localmente. Resultados **idênticos ao Planjud** para os casos
validados (ver [`references/motor-local.md`](references/motor-local.md)).

```bash
# padrão: motor local (offline depois do primeiro fetch; erro se o caso não for suportado)
... --correcao INPC --data-base 2026-08 --parcela 645.36:2011-04-01

# forçar o motor oficial do Planjud (usa a API do TJTO; cria registro público)
... --correcao FAZENDA_PUBLICA --juros FAZENDA_GERAL --juros-mora 2011-04 \
    --parcela 645.36:2011-04-01 --motor planjud

# deixar a ferramenta escolher (local quando aplicável, senão Planjud)
... --correcao IPCA --data-base 2026-08 --parcela 645.36:2011-04-01 --motor auto
```

O motor local **recusa** (erro explícito, sem cair no Planjud silenciosamente) os casos
fora do escopo: **juros de mora** (≠ `SEM_JUROS`), **EC 136/2025**, **SELIC (EC 113/2021)**,
termos **< 07/1995** ou **critério composto**. Para esses (ou para o resultado oficial),
use `--motor planjud` (oficial) ou `--motor auto`.

**Cache** — resultados por chave determinística (critério + parcelas + data-base + EC 136),
TTL 30 dias; catálogo e séries também ficam em cache. Limpe com `--clear-cache`.

```bash
... --no-cache            # ignora o cache nesta execução
... --cache-ttl 7         # validade do cache de resultados (dias)
... --clear-cache         # apaga todo o cache
```

**Refresh do catálogo** — atualiza nomes/ids/**datas-base** dos critérios a partir da
página `Create` do sistema (as datas-base sobem a cada mês):

```bash
... --refresh             # mostra e salva as mudanças do catálogo
```

Tudo respeita `PLANJUD_CACHE_DIR` (diretório base do cache) e `PLANJUD_CATALOG` (arquivo de catálogo).

## Uso — MCP (qualquer agente de IA)

O cálculo é exposto como **ferramentas MCP** (`scripts/planjud_mcp.py`), descobertas
automaticamente por **Claude Desktop, Cursor, VS Code, Hermes, Zed** … O schema é gerado dos
*type hints* e *docstrings* — sem *glue code*.

Ferramentas: `listar_criterios`, `indice_disponivel`, `atualizar_catalogo`, `calcular_correcao`.

```bash
# rodar o servidor (stdio)
uv run --with "mcp<2" --with requests python scripts/planjud_mcp.py
```

Registro (mesma forma em todos os clientes):

```yaml
# Hermes — ~/.hermes/config.yaml
mcp_servers:
  planjud:
    command: "uv"
    args: ["run", "--with", "mcp<2", "--with", "requests", "python",
           "/caminho/para/scripts/planjud_mcp.py"]
```
```json
// Claude Desktop / Cursor / VS Code (.vscode/mcp.json)
{ "mcpServers": { "planjud": {
  "command": "uv",
  "args": ["run","--with","mcp<2","--with","requests","python","/caminho/para/scripts/planjud_mcp.py"] } } }
```

> ⚠️ **Fixe `mcp<2`.** No SDK 2.x o `FastMCP` virou `MCPServer` (`mcp.server.mcpserver`).
> O script tolera ambas as versões no import, mas a pinagem evita surpresas.

Para frameworks **sem** MCP (OpenAI, Anthropic, LangChain, Ollama, Mistral…), use
[`references/tool_schema.json`](references/tool_schema.json) — as mesmas 3 funções em formato
de *function calling*.

## Estrutura

```
.
├── scripts/
│   ├── planjud_calc.py     # CLI (núcleo: catálogo, resolução, HTTP, extração de resultado)
│   └── planjud_mcp.py      # servidor MCP (stdio) com as 4 ferramentas
├── references/
│   ├── criterios.md        # 16 critérios de correção + 12 de juros (com notas normativas)
│   ├── mcp.md              # integração MCP por cliente, teste e pitfalls
│   ├── motor-local.md      # motor offline (INPC/IPCA/IGP-DI via BACEN): escopo e validação
│   └── tool_schema.json    # schema portátil de function calling
├── docs/
│   ├── regras-de-negocio.md        # regras de negócio do módulo (extração completa)
│   └── extracao-e-proveniencia.md  # como as regras foram extraídas (fontes e método)
├── examples/
│   └── parcelas.csv
└── tests/
    └── test_offline.py     # testes sem rede
```

## Verificação (valor de controle)

`645,36` de `04/2011` pelo **INPC**, data-base `08/2026` → **R$ 1.496,16** (fator `2,3183389`).
Termo inicial `05/2011` → **R$ 1.485,47** (fator `2,3017662`).

```bash
pytest -q
```

## Proveniência e manutenção

- Extraído em **2026-10-07** contra a **v5.0.19.7** (HTML da view, bundle Vue, manual oficial
  em PDF e planilhas-modelo do próprio sistema). Detalhes em
  [`docs/extracao-e-proveniencia.md`](docs/extracao-e-proveniencia.md).
- O **catálogo de critérios e datas-base** em `scripts/planjud_calc.py` é um **snapshot**.
  Índices e datas-base sobem a cada mês — confira com `--list` e atualize se necessário.
- O motor de cálculo **oficial** é *server-side* no Planjud (usado com `--motor planjud|auto`);
  o **motor local** (padrão) reproduz INPC/IPCA/IGP-DI a partir das séries do BACEN e foi
  validado contra o Planjud (ver [`references/motor-local.md`](references/motor-local.md)).

## Licença

MIT — ver [LICENSE](LICENSE).
