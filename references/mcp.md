# Planjud — Integração via MCP (plugável em qualquer agente)

> O motor do cálculo é exposto como **ferramentas MCP** (Model Context Protocol),
> o padrão aberto que clientes de IA — Claude Desktop, Cursor, VS Code, Hermes,
> Zed, Continue… — descobrem e chamam automaticamente. Não há *glue code*: o
> agente lê o *schema* (gerado dos type hints e docstrings) e decide quando chamar.

## Ferramentas expostas

| Ferramenta | Para que serve | Rede? | Entrada principal |
|---|---|---|---|
| `listar_criterios` | Descobrir os critérios de correção/juros (alias, GUID, início, data-base) | ❌ offline | `tipo` = `correcao`\|`juros`\|`todos` |
| `indice_disponivel` | Último índice publicado (data-base) e início de vigência de um critério | ❌ offline | `correcao` |
| `atualizar_catalogo` | Re-scrapeia o catálogo do site (nomes, ids **e datas-base**) e salva em cache | ✅ site TJTO | `base_url` |
| `calcular_correcao` | Corrigir 1+ parcelas (juros opcionais, EC 136, SELIC) | ✅ | `parcelas`, `correcao`, `juros`, `data_base`, `motor`, … |

`calcular_correcao` aceita `motor` = **`planjud`** (oficial, padrão) · **`local`**
(INPC/IPCA/IGP-DI via BACEN, offline após cache) · **`auto`** (local quando aplicável).
E `usar_cache` (padrão `true`) reaproveita resultados; a resposta traz `motor` e `de_cache`.

`calcular_correcao` aceita parcelas como dict ou string:
```json
{"parcelas": [
  {"valor": 645.36, "data": "2011-04-01", "nome": "Aluguel"},
  {"valor": 1000,    "data": "2015-06-01", "juros_mora": "2015-06-01"}
]}
```

## Rodar o servidor (stdio)

```bash
uv run --with "mcp<2" --with requests python scripts/planjud_mcp.py
```

⚠️ **Fixe `mcp<2`.** No SDK 2.x o `FastMCP` foi renomeado para `MCPServer`
(`mcp.server.mcpserver`) e a API mudou. O script tolera ambas as versões no
import, mas a pinagem evita surpresas.

## Registrar no Hermes Agent

`~/.hermes/config.yaml`:

```yaml
mcp_servers:
  planjud:
    command: "uv"
    args: ["run", "--with", "mcp<2", "--with", "requests", "python",
           "/root/.hermes/skills/productivity/planjud-calculo/scripts/planjud_mcp.py"]
    timeout: 120
```

Reiniciar o Hermes. As ferramentas aparecem como `mcp_planjud_calcular_correcao`,
`mcp_planjud_listar_criterios`, `mcp_planjud_indice_disponivel`.

## Registrar no Claude Desktop / Cursor / VS Code

`claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`;
Windows: `%APPDATA%\Claude\`) — mesma forma `mcpServers`:

```json
{
  "mcpServers": {
    "planjud": {
      "command": "uv",
      "args": ["run", "--with", "mcp<2", "--with", "requests", "python",
               "/caminho/para/planjud_mcp.py"]
    }
  }
}
```

Cursor: `~/.cursor/mcp.json`. VS Code (Copilot): `.vscode/mcp.json` com a mesma
estrutura. Qualquer cliente que fale MCP usa o mesmo bloco.

## Teste rápido (cliente MCP)

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    p = StdioServerParameters(command="uv",
        args=["run","--with","mcp<2","--with","requests","python","planjud_mcp.py"])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            print([t.name for t in (await s.list_tools()).tools])
            res = await s.call_tool("calcular_correcao", {
                "parcelas": [{"valor": 645.36, "data": "2011-04-01"}],
                "correcao": "INPC", "data_base": "2026-08"})
            print(res.content[0].text)

asyncio.run(main())
```

## Sem MCP? Use o schema portátil

Frameworks que usam *function calling* próprio (OpenAI, Anthropic, LangChain,
Ollama, Mistral…) consomem `references/tool_schema.json` — um array de funções no
formato OpenAI (`{"type":"function","function":{...}}`) com os mesmos 3 nomes e
JSON Schema. Basta apontar o handler para o CLI (`planjud_calc.py`) ou importar as
funções do `planjud_mcp.py`.

## Cache e modo offline

- **Cache de resultados** por chave determinística (critério + parcelas + data-base + EC 136),
  TTL 30 dias, em `~/.cache/planjud-calculo/resultados.json`. Uma segunda chamada idêntica
  devolve `de_cache: true` e **não** gera novo registro no Planjud.
- **Catálogo** e **séries de índices** também ficam em cache. `atualizar_catalogo` reescreve o catálogo.
- **Motor local** (`motor=local`) calcula INPC/IPCA/IGP-DI sem o Planjud (BACEN SGS, cache de 1 dia).
- Tudo respeita `PLANJUD_CACHE_DIR` (diretório base do cache) — útil no `env:` do `mcp_servers`.

## Pitfalls

- **stdio:** não escreva logs no *stdout* (corrompe o protocolo JSON-RPC);
  mensagens de diagnóstico vão para *stderr*. O servidor não imprime nada.
- **Env filtrado:** o Hermes não repassa o ambiente do shell ao subprocesso —
  o servidor não depende de variáveis de ambiente (só de rede para o TJTO).
- **Rede:** o cálculo exige acesso de saída a `app.tjto.jus.br` (TLS válido).
- **Cada chamada cria um cálculo público** no Planjud e retorna o `codigo_calculo`.
