# Planjud MCP offline — PDF, cálculos e Excel

Servidor MCP local que reúne, em uma única integração:

1. localização das páginas **DEMONSTRATIVO DE PAGAMENTOS** em um PDF;
2. extração tabular diretamente da camada textual do documento;
3. normalização, tipagem, classificação e validação dos lançamentos;
4. cálculo local de correção monetária por INPC, IPCA ou IGP-DI;
5. geração de PDF recortado, JSON, CSV e planilha Excel com fórmulas.

O fluxo de execução é **offline**: o servidor não consulta o Planjud/TJTO, não
envia dados do processo a serviços externos e não cria código nem registro
público de cálculo. As séries mensais necessárias estão incluídas no pacote.

> O único PDF de processo versionado é
> `examples/processo1_anonimizado.pdf`, preparado exclusivamente com dados
> fictícios para demonstrar e testar o MCP. Outros `*.pdf`, arquivos `*.xlsx`,
> `outputs/` e pastas de extração continuam ignorados pelo Git.

## Como funciona

### 1. Extração nativa do PDF

Não é usado OCR. O extrator abre o arquivo com
[PyMuPDF](https://pymupdf.readthedocs.io/) (`pymupdf`, também conhecido como
`fitz`) e usa `page.get_text("words")`. Cada palavra fornece texto e coordenadas
`x/y`.

As páginas são selecionadas quando contêm o título `DEMONSTRATIVO DE PAGAMENTOS`
e ao menos um identificador real de lançamento. As linhas são ancoradas por
expressões como:

- `P.1/180`, `P.2/180`, `P.1/136` para parcelas;
- códigos numéricos compostos para lançamentos administrativos.

Os campos são reconstruídos pelas faixas horizontais da tabela: parcela,
descrição, vencimento, atraso, valor pago, data do recebimento, valor da parcela,
principal, juros, correção, multa, juros de atraso, desconto e parcela acrescida.
As coordenadas são normalizadas pela largura da página.

### 2. Normalização e validação

- números brasileiros são convertidos para valores computáveis, por exemplo
  `1.169,63` → `1169.63`;
- datas `dd/mm/aaaa` são validadas e convertidas para objetos de data;
- parcelas com prefixo `P.` são diferenciadas de taxa de transferência,
  renegociação e outros lançamentos administrativos;
- apenas parcelas recebem `elegivel_restituicao = true`;
- a soma de `valor_pago` é comparada ao total `RECEBIDO` do documento.

Na amostra usada durante o desenvolvimento, mantida apenas localmente por conter
dados de processo, foram identificados 66 lançamentos e a soma extraída foi
**R$ 56.358,12**, exatamente igual ao total `RECEBIDO` do demonstrativo.

### 3. Cálculo monetário offline

O motor local reaproveita a lógica matemática do projeto Planjud e substitui toda
obtenção de índices por snapshots empacotados das séries SGS do Banco Central:

| Critério | Série SGS | Intervalo incluído |
|---|---:|---|
| INPC | 188 | 01/1995 a 08/2026 |
| IGP-DI | 190 | 01/1995 a 09/2026 |
| IPCA | 433 | 01/1995 a 08/2026 |

O mês inicial e o mês da data-base participam do produto acumulado:

```text
fator = produto(1 + índice_mensal / 100)
valor atualizado = valor original × fator
```

O escopo local aceita esses três índices, datas a partir de 01/1995 e ausência de
juros de mora. Critérios compostos do TJTO, SELIC, EC 136/2025 e regras de juros
não são simulados. Pedidos fora desse escopo retornam erro; não existe fallback
para a internet.

## Planilha Excel

A exportação cria um arquivo `<nome>_atualizacao_inpc.xlsx` com duas abas.

### Aba `Pagamentos`

Contém as colunas:

| Ordem | Parcela | Descrição | Vencimento | Pagamento | Valor pago (R$) | Principal (R$) | Correção contratual (R$) | Multa (R$) | Juros mora (R$) | Base restituível (R$) | Competência INPC | Índice anterior | Fator INPC | Valor atualizado (R$) | Retenção (R$) | Líquido a restituir (R$) |  |  | Observação |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|---:|---:|---:|---:|---|---|---|

A célula `B2` guarda a retenção percentual e permanece editável. Os campos
calculados são fórmulas, não valores fixos:

| Campo | Regra |
|---|---|
| Base restituível | `Principal + Correção contratual`, somente para `P.` |
| Competência INPC | primeiro dia do mês do pagamento |
| Índice anterior | procura a competência na aba `INPC` |
| Fator INPC | índice acumulado final ÷ índice anterior |
| Valor atualizado | base restituível × fator |
| Retenção | valor atualizado × `$B$2` |
| Líquido a restituir | valor atualizado − retenção |

Exemplo na interface em português do Excel:

```excel
=SE(ESQUERDA($B4;2)="P.";PROCV(L4;INPC!$A$6:$D$385;3;FALSO);0)
```

O arquivo XLSX armazena internamente a mesma fórmula com nomes em inglês e
separadores por vírgula, como exige o formato Office Open XML. O Excel traduz a
exibição conforme o idioma instalado.

### Aba `INPC`

Registra a fonte, a observação da Série 188 e a memória mensal:

| Competência | INPC mensal | Índice anterior | Índice acumulado |
|---|---:|---:|---:|

`Índice anterior` referencia o acumulado da linha anterior, e `Índice acumulado`
usa `Índice anterior × (1 + INPC mensal)`. As fórmulas da aba `Pagamentos`
referenciam essa memória diretamente.

## Arquivos gerados

Por padrão, a saída fica em `<pasta-do-pdf>/<nome>_demonstrativo/`:

| Arquivo | Conteúdo |
|---|---|
| `<nome>_demonstrativo_pagamentos.pdf` | somente as páginas localizadas |
| `<nome>_demonstrativo_pagamentos.json` | resultado estruturado e validação |
| `<nome>_demonstrativo_pagamentos.csv` | lançamentos normalizados, UTF-8 e `;` |
| `<nome>_atualizacao_inpc.xlsx` | abas `Pagamentos` e `INPC` com fórmulas |

## Requisitos e instalação

- Python 3.10 ou superior;
- nenhuma credencial;
- nenhuma conexão de rede durante a execução.

No Windows PowerShell:

```powershell
git clone https://github.com/rogernogueira/planjud.git
cd planjud
py -m venv .venv
.venv\Scripts\python -m pip install -e .
```

No Linux ou macOS:

```bash
git clone https://github.com/rogernogueira/planjud.git
cd planjud
python3 -m venv .venv
.venv/bin/python -m pip install -e .
```

Depois da instalação, o servidor pode ser iniciado por `planjud-mcp` ou
`demonstrativo-pagamentos-mcp`.

## Configuração do cliente MCP

O servidor usa transporte stdio e implementa diretamente o protocolo MCP, sem
depender do SDK Python do MCP.

Exemplo para Windows, ajustando o caminho do repositório:

```json
{
  "mcpServers": {
    "distrato-planjud": {
      "command": "D:\\caminho\\planjud\\.venv\\Scripts\\python.exe",
      "args": ["-m", "demonstrativo_mcp.server"]
    }
  }
}
```

Exemplo para Linux ou macOS:

```json
{
  "mcpServers": {
    "distrato-planjud": {
      "command": "/caminho/planjud/.venv/bin/python",
      "args": ["-m", "demonstrativo_mcp.server"]
    }
  }
}
```

## Ferramentas MCP

### `localizar_paginas_demonstrativo`

Localiza páginas elegíveis sem exportar arquivos.

```json
{
  "pdf_path": "D:\\Processos\\processo.pdf"
}
```

### `extrair_demonstrativo_pagamentos`

Extrai, valida e opcionalmente gera todos os arquivos.

```json
{
  "pdf_path": "D:\\Processos\\processo.pdf",
  "output_dir": "D:\\Processos\\resultado",
  "exportar_arquivos": true,
  "retencao_percentual": 10
}
```

`output_dir` é opcional. `retencao_percentual` aceita valores de 0 a 100 e inicia
em 0 quando omitido.

## Exemplo anonimizado incluído

O arquivo `examples/processo1_anonimizado.pdf` pode ser usado imediatamente após
clonar o repositório. Ele preserva a estrutura de um processo de teste, mas os
nomes, documentos, contatos, endereços, assinaturas e demais identificadores
pessoais foram removidos ou substituídos por dados fictícios. O arquivo original
não é versionado.

Execute a ferramenta `extrair_demonstrativo_pagamentos` a partir da raiz do
repositório com:

```json
{
  "pdf_path": "examples/processo1_anonimizado.pdf",
  "output_dir": "outputs/exemplo_anonimizado",
  "exportar_arquivos": true,
  "retencao_percentual": 10
}
```

O resultado esperado localiza o demonstrativo nas páginas 33 e 34, extrai 66
lançamentos e valida o total recebido de **R$ 56.358,12**, sem acessar a rede ou
criar registro público.

### `listar_criterios`

Lista o catálogo local. `tipo` pode ser `todos`, `correcao` ou `juros`.

```json
{"tipo": "correcao"}
```

### `indice_disponivel`

Informa vigência, última competência incluída e suporte local.

```json
{"correcao": "INPC"}
```

### `calcular_correcao`

Calcula uma ou mais parcelas exclusivamente com dados locais.

```json
{
  "parcelas": [
    {"valor": "1.169,63", "data": "10/11/2016", "nome": "Parcela 1"},
    {"valor": 645.36, "data": "2011-04-01", "nome": "Parcela 2"}
  ],
  "correcao": "INPC",
  "data_base": "2026-08"
}
```

A resposta registra explicitamente `modo_rede: "desativado"` e
`registro_publico: false`.

## Desenvolvimento e testes

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m pytest -q
```

Os testes criam um PDF sintético em diretório temporário, verificam a descoberta
das cinco ferramentas MCP, executam um cálculo com o snapshot empacotado e
inspecionam as abas e fórmulas do XLSX. Nenhum teste acessa a rede.

Estrutura principal:

```text
src/demonstrativo_mcp/
├── server.py          # protocolo MCP stdio e schemas das ferramentas
├── extractor.py       # extração posicional, tipagem e validação
├── excel_export.py    # planilha Pagamentos + INPC
├── planjud_tools.py   # interface segura do motor local
├── _planjud_calc.py   # lógica matemática reaproveitada do Planjud
└── data/              # snapshots SGS 188, 190 e 433
```

## Limitações conhecidas

- PDFs apenas digitalizados precisam de uma etapa externa de OCR e não são
  processados por este projeto.
- A reconstrução posicional foi calibrada para o layout do demonstrativo UAU;
  mudanças substanciais no modelo podem exigir ajuste das faixas horizontais.
- Os índices não são atualizados automaticamente, preservando a operação offline.
  Para novas competências, os snapshots devem ser revisados e versionados no
  repositório antes da instalação.
- A validação confirma a consistência entre a tabela extraída e o total do próprio
  documento; ela não substitui revisão contábil ou jurídica.

## Licença e fontes

Código sob licença MIT. A lógica reaproveitada do Planjud mantém a licença em
`src/demonstrativo_mcp/PLANJUD_LICENSE`.

As séries são identificadas como BACEN/SGS 188 (INPC/IBGE), 190 (IGP-DI/FGV) e
433 (IPCA/IBGE). Os endereços de origem ficam registrados como metadados para
rastreabilidade, mas o servidor não os consulta durante a execução.
