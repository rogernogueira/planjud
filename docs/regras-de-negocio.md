# Regras de Negócio — Planjud / Cálculo Geral (TJTO)

**Fonte:** `https://app.tjto.jus.br/planjud/PublicoCalculoGeral/Create`
**Extraído de:** HTML da view Razor, bundle `app.js` (desminificado), endpoint `Permissao/Menu`, manual oficial em PDF e planilhas-modelo `.xlsx`.
**Versão do sistema (rodapé):** 5.0.19.7 · © 2026 TJTO
**Fabricante:** CRP Tecnologia · Sistema Planjud Web · OS 03: Cálculo Geral
**Stack:** ASP.NET Core (Razor) + Vue 2/Buefy no front · cálculo executado no back-end (o front só coleta e valida; `POST Create/Edit` devolve o id e o cálculo é processado no servidor).

---

## 1. Atores e permissões

| Ator | Pode |
|---|---|
| **Público** (sem login) | Gerar cálculos; consultar cálculo por código; gerar/baixar PDF **somente após confirmar** o cálculo |
| **Contador** | Criar, editar e excluir cálculos; campo **Data Juros de Mora** liberado; editar cálculo mesmo sem confirmar |
| **Administrador (Gestor)** | Todas as funcionalidades |

- No ambiente público, `:usuario-logado=false`. Consequências diretas: o campo **Data Juros de Mora** fica oculto/desabilitado e há regras de EC 136 que **forçam** a SELIC.
- Cálculos não confirmados são considerados **descartados** e uma rotina diária os **desativa** (desativados não são listáveis).

## 2. Módulos / menus (via `GET /planjud/Permissao/Menu`)

- **Gerar Cálculo** → *Cálculo Geral* (`/PublicoCalculoGeral/Create`); *Pensão Alimentícia* (`/PensaoAlimenticia/Create`) — módulo separado
- **Visualizar Cálculo Geral** (`/PublicoCalculoGeral`) — lista/consulta
- **Login** (`/CalculoGeral/Create`)
- **Ajuda** → Manual do Usuário (PDF) + Tutoriais 01–04

## 3. Ciclo de vida do cálculo (workflow de informação)

1. **Criar** (`POST /planjud/PublicoCalculoGeral/Create`) → gera **código do cálculo** e redireciona para `VisualizarCalculo/{id}`.
2. **Confirmar** → torna o cálculo consultável/baixável (público só vê após isso).
3. **Editar** (`POST /PublicoCalculoGeral/Edit`) → **cada alteração gera uma nova versão** (mantém histórico desde o início).
4. **Excluir** → bloqueado se o cálculo estiver vinculado a processo no **e-Proc** (integração prevista mas fora de escopo).

**Status possíveis:** `Não gerado` (criado, não confirmado) · `Gerado` (confirmado) · `Vinculado` (confirmado e ligado ao e-Proc — fora de escopo) · `Todos`.

**Regras de lista/filtro (logado):** por Código do Cálculo, Status, Responsável (usuário logado), Nº Processo, Data de Geração. Ordenação por data de geração decrescente. Consulta sem resultado → "Nenhum registro encontrado". É permitido gerar **vários cálculos distintos para o mesmo nº de processo**.

---

## 4. Estrutura do formulário (abas e obrigatoriedade)

### 4.1 Informação do Processo — *opcional*
- **Nº do processo**: máscara `#######-##.####.###.####` (24 caracteres em tela), **20 dígitos em banco**; não obrigatório. Se preenchido e ≠ 20 dígitos → erro *"O Número Processo deve conter pelo menos 24 caracteres."*
- **Órgão julgador**: texto, máx. 240/250 · não obrigatório
- **Requerente** / **Requerido**: texto, máx. 240/250

### 4.2 Critérios de Correção Monetária e Juros de Mora — **obrigatório**
- **Critério de Correção Monetária** (seleção, obrigatório)
- **Critério de Juros de Mora** (seleção, obrigatório)
- **Atualização Até / Data-base (mês/ano)** (obrigatório)
- **SELIC a partir de 12/2021 (EC 113/21)** — checkbox "cálculo cumulado com SELIC"
- **Aplicar EC nº 136/2025** + **Início de aplicação** + **critério pós-corte** (`EC136` = Provimento 207/CNJ, ou `CODIGO_CIVIL` = Regras do Código Civil)
- **Permitir deflação** · **Decisão SELIC Fazenda** (Decisão 388/2022 ou 434/2023)

### 4.3 Multa por Descumprimento de Acordo / Obrigação — *facultativo*
- Checkbox "Aplicar…" + **Percentual da Multa** (obrigatório se marcado; máx. 6 caracteres: 3 inteiros + vírgula + 2 decimais)

### 4.4 Honorários Advocatícios — **Conhecimento** (obrigatório) e **Cumprimento de Sentença** (facultativo)

### 4.5 Multa — Art. 523, § 1º, CPC/2015 — *facultativo*
- Checkbox **Multa 10%** e checkbox **Honorários Advocatícios 10%** (independentes)

### 4.6 Partes / Parcelas — *facultativo* — 4 modos de entrada
`Individual` · `Múltiplas` · `Sal. mínimo` · `Tabela` (upload). Existe ainda a variante **Base de Cálculo** (parcelas com `% Cálculo`).

### 4.7 Outras Verbas — *facultativo* — mesmos 4 modos + base de cálculo

### 4.8 Astreintes — *facultativo*
- **Valor Unitário da Multa**, **Periodicidade**, **Data Inicial/Final da Ocorrência** (dd/mm/aaaa), **Termo Inicial de Correção Monetária** (mês/ano), **Data Juros de Mora** (só Contador)
- **Periodicidade:** Dia=1 · Semana=2 · Quinzena=3 · Mês=4 · Ano=5
- ⚠️ **Astreintes não integra a base de cálculo de Honorários e Multas**

### 4.9 Observações — *facultativo* (texto, máx. 1000)

---

## 5. Dados de referência (vocabulário controlado)

### 5.1 Critérios de Correção Monetária (16 opções)

| Descrição | Tipo | Início | Nota normativa |
|---|---|---|---|
| DÉBITOS GERAIS | 1 | 10/1964 | IN 01/2018/TJTO — ORTN→OTN→IPC/STJ→BTN→IPC/IBGE→INPC→IPC-r→INPC (a partir 07/1995) |
| FAZENDA PÚBLICA | 2 | 10/1964 | IN 05/2020/TJTO — mesmos até 29/06/2009, depois IPCA-E/IBGE |
| DÉBITOS GERAIS + IPCA (LEI 14.905/2024) | 62 | 10/1964 | INPC até 08/2024 e IPCA a partir de 09/2024 |
| BENEFÍCIOS PREVIDENCIÁRIOS | 14 | 10/1964 | índices da Justiça Federal (…IGP-DI 05/1996–08/2006, INPC após) |
| CONDENATÓRIAS EM GERAL – JUSTIÇA FEDERAL | 13 | 10/1964 | UFIR 01/1992–12/2000 e IPCA-E a partir 01/2001 |
| IGP-DI/FGV | 3 | 10/1964 | — |
| IGP-M/FGV | 4 | 06/1989 | — |
| INCC/FGV | 5 | 10/1964 | — |
| INPC/IBGE | 6 | 04/1979 | — |
| IPCA/IBGE | 7 | 01/1980 | — |
| IPCA-E/IBGE | 8 | 01/1992 | — |
| **SELIC FAZENDA – A PARTIR DE 12/2021 – EC 113/21** | 15 | 12/2021 | EC 113/2021 |
| **SELIC TRIBUTÁRIO** | 9 | 01/1995 | SELIC (BACEN) em todo o período |
| TR + IPCA-E | 10 | 07/1994 | TR até 25/03/2015, IPCA-E após |
| IGP-M + IPCA | 11 | 07/1994 | IGP-M até 29/06/2009, IPCA após |
| TR | 12 | 07/1994 | — |

> **Alerta de qualidade (nota do sistema):** "TR + IPCA-E" traz a nota *"TR até 25/03/2015 e IPCA-E a partir de **26/03/2025**"* — data provavelmente inconsistente (deveria ser 26/03/2015). Possível erro de cadastro de dados de referência.

### 5.2 Critérios de Juros de Mora (12 opções)

| Nome | Tipo | Início | Regra |
|---|---|---|---|
| SEM JUROS | 50 | — | sem juros |
| 6% a.a. até 12/2002 e 12% a.a. em diante | 51 | — | — |
| 6% ao ano em todo o período | 52 | — | — |
| 12% ao ano em todo o período | 53 | — | — |
| 12% a.a. até 06/2009 e 6% a.a. em diante | 54 | — | — |
| 12% a.a. até 06/2009 e juros da poupança (dia 1º) em diante | 59 | 01/1964 | — |
| REGRA GERAL – FAZENDA PÚBLICA | 55 | 10/1964 | 0,5% a.m. até 01/2003; 1% a.m. até 06/2009; depois poupança (art. 1º-F Lei 9.494/97; Lei 12.703/2012) |
| REGRA SERVIDORES E EMPREGADOS – FAZENDA PÚBLICA | 56 | 03/1987 | 1% a.m. até 07/2001 (Lei 8.177/91); 0,5% a.m. 08/2001–06/2009; depois poupança |
| REGRA BENEFÍCIOS PREVIDENCIÁRIOS – FAZENDA PÚBLICA | 57 | 01/1988 | 1% até 06/2009 (DL 2.322/87); depois poupança |
| REGRA EXCLUSIVAMENTE POUPANÇA – FAZENDA PÚBLICA | 58 | 02/1991 | 0,5% a.m. 08/2001–06/2009; depois poupança |
| **TL – TAXA LEGAL (ART. 406, §1º, CC)** | 60 | 08/2024 | taxa legal |
| 6% até 12/2002; 12% até 07/2024 e TL a partir de 08/2024 | 61 | 02/1964 | — |

### 5.3 Decisões SELIC Fazenda
`1 = Decisão nº 388/2022` · `2 = Decisão nº 434/2023` (**default = 2**)

### 5.4 Honorários — Conhecimento (fase 1)
1. Sem Honorários
2. Sobre o Valor da Condenação
3. Sobre o Valor da Causa
4. Sobre o Valor do Proveito Econômico
5. Valor Certo

### 5.5 Honorários — Cumprimento de Sentença (fase 2)
1. Sem honorários
4. Sobre o Valor Proveito Econômico
5. Valor Certo
6. Valor da Execução (condenação + sucumbência)
7. Valor da Condenação (sem sucumbência)

### 5.6 Honorários escalonados (art. 85, §3º, CPC — incisos)
| Inciso | Faixa (salários mínimos) | % mínimo–máximo |
|---|---|---|
| I | até 200 | 10%–20% |
| II | > 200 até 2.000 | 8%–10% |
| III | > 2.000 até 20.000 | 5%–8% |
| IV | > 20.000 até 100.000 | 3%–5% |
| V | > 100.000 | 1%–3% |

---

## 6. Regras de validação (front-end)

### 6.1 Validação geral (botão *Gerar Cálculo*)
Ordem: informação do processo → correção/juros → multa descumprimento → honorários (fase 1) → honorários (fase 2) → preview.

### 6.2 Critérios de correção/juros
- Se **não** marcado "cálculo cumulado com SELIC": **correção monetária** e **juros de mora** são obrigatórios.
- **Data-base** sempre obrigatória.
- **Data-base** deve ser `≤ teto` (data-base do critério) e `≥ data mínima` (início de vigência do critério).
- Ao escolher **SELIC Fazenda (tipo 15)** ou **SELIC Tributário (tipo 9):** juros de mora é **forçado para "SEM JUROS"**, o campo de juros fica **desabilitado** e a seleção cumulada com SELIC é controlada.
- Marcar **Aplicar EC 136/2025**:
  - força **SELIC (12/2021) = verdadeiro**; no perfil público mostra aviso *"A Selic a partir de 12/2021 (EC 113/21) é obrigatória quando Aplicar EC nº 136/2025 estiver ativa"*;
  - define **início de aplicação** default = **08/2025**;
  - busca `dataLimiteEC136` (via `POST /CalculoGeral/BuscarDataLimiteEC136`) e **limita a data-base** a esse teto.
- **Selic adequação:** `POST {urlDatabasesSelicAdequacao}?codigoCalculo=…`; se houver mais de uma data-base retornada, abre modal para escolha.

### 6.3 Multa por Descumprimento
- Se "Aplicar" marcado e **percentual = 0** → bloqueia. Desmarcar limpa o percentual.

### 6.4 Honorários (por fase)
- Tipo nulo → obrigatório informar.
- **Tipo 1** → nada exigido.
- **Tipos 2 e 6** → percentual ≠ 0 (dispensado se escalonado).
- **Tipo 3** → percentual ≠ 0 + **Valor da Causa** + **Data Limite/Ajuizamento**.
- **Tipo 4** → percentual ≠ 0 + valor + data de fixação/proveito.
- **Tipo 5** → **Valor Fixado** ≠ 0 + data de fixação.
- **Escalonamento** disponível apenas para os tipos 2, 3 e 4.
- **Data de fixação/ajuizamento**: `≤ data-base` e `≥ data mínima`; invalidá-la **zera a Data de Juros de Mora**.
- **Data de Juros de Mora**: `≤ data máxima de juros` e `≥ data mínima de juros`. Campo desabilitado quando `data mínima juros ≥ data máxima juros`.

### 6.5 Partes/Parcelas e Outras Verbas
- **Valor da parcela ≠ R$ 0,00** (senão: *"O valor da parcela não deve ser R$ 0,00"*).
- **Sem duplicidade de competência**: não pode haver duas parcelas com **mesma Data de Correção (mês/ano)** → *"Não Pode Adicionar Parcela com a Mesma Data de Correção."*
- Não pode haver parcela **dentro de intervalo já cadastrado** (período e faixa de salário).
- **Data Correção** `≤ data-base` e `≥ data mínima`; **Data Inicial/Final** idem.
- **Data Juros de Mora** entre mínima e máxima de juros.
- Com **EC 136**: Data de Juros de Mora `≤ Data Final`.
- Modo **Salário Mínimo**: data inicial permitida a partir de **01/01/1965**; valor = `fatorAcumulado × porcentagem` (porcentagem normalizada: se >1 divide por 100; precisão 6).
- **Upload Excel**:
  - datas de correção `≤ data-base` (senão erro);
  - datas de juros `≥ data mínima de juros` (senão erro);
  - **incompatibilidade SELIC (EC 113/21):** parcelas com `data_correcao` a partir de **12/2021** só recebem `data_juros_mora` se o cálculo **não** estiver cumulado com SELIC; caso contrário o sistema avisa e **não carrega** as datas de juros.
- Ao excluir/renumerar, o **seq** das parcelas é recalculado sequencialmente (1..n).

### 6.6 Astreintes
- Valor unitário ≠ 0.
- Data Inicial/Final da ocorrência e Termo Inicial de Correção: `≤ data atual` e `≥ data mínima`; **Data Final ≥ Data Inicial**.
- Data Juros de Mora entre mínima e máxima.

---

## 7. Regras de cálculo (composição e ordem)

Fonte: `VisualizarCalculoResumoCalculo` + colunas de `VisualizarCalculoDetalhadoPartesParcelas`.

**Ordem de composição do TOTAL (subtotais encadeados):**

1. **Partes / Parcelas** → *Subtotal 1*
2. **Multa por Descumprimento de Acordo/Obrigação** → *Subtotal 2*
3. **Honorários Advocatícios – Conhecimento** → *Subtotal 3*
4. **Multa 10% Art. 523** + **Honorários 10% Art. 523** → *Subtotal 4*
5. **Honorários Advocatícios – Cumprimento de Sentença** → *Subtotal 5*
6. **Outras Verbas**
7. **Astreintes**
8. **= TOTAL**

> Parcelas de **Base de Cálculo** (aquelas com `% Cálculo`) **não** entram no principal; servem de base para honorários/multas. As de "Geral" (sem percentual) entram no principal.

**Colunas do detalhamento (regime EC 136/2025):**

| Col. | Significado | Fórmula |
|---|---|---|
| A | Valor (principal) | — |
| B | Juros de Mora (R$) | — |
| C | Selic (R$) | — |
| D | Total Parcial Selic | A + B + C (base) |
| E | Coeficiente de Correção Monetária (IPCA) | — |
| F | Correção Monetária do Principal (IPCA) | `A × E − A` |
| G | Correção Monetária dos Juros de Mora | `B × E − B` |
| H | Correção Monetária da Selic | `C × E − C` |
| I | % Juros de Mora 2% a.a. *(ou Taxa Legal)* | — |
| J | Juros de Mora 2% a.a. | `I × (A + F)` |
| K | Selic (%) quando < IPCA + 2% a.a. | limitação (teto) |
| L | Selic (R$) | `K × (A + F)` |

- Sob EC 136 o principal é corrigido pelo **IPCA**; os **juros de mora = 2% a.a.** sobre o principal corrigido *(A+F)*, e a **SELIC só incide se for menor que IPCA + 2% a.a.** (mecanismo de teto).
- Se o **critério pós-corte = Código Civil**, usa-se a **Taxa Legal** em lugar dos 2% a.a.
- Os juros também são **corrigidos** (G) e a SELIC também (H) antes do total.

**Regimes especiais identificados:**
- **EC 113/2021** → SELIC unificada a partir de **12/2021** (correção + juros); incompatível com parcelas de juros após 12/2021 quando cumulado.
- **EC 136/2025 (Provimento 207/CNJ)** → novo regime com IPCA + juros 2% a.a. / teto SELIC (fórmulas acima).
- **Lei 14.905/2024** → IPCA a partir de **09/2024** (critério "Débitos Gerais + IPCA").
- **Taxa Legal (art. 406, §1º, CC)** → critério de juros e pós-corte.

---

## 8. Estrutura das planilhas de upload (`.xlsx`)

**Partes/Parcelas — `planilha.xlsx`:** colunas `data_correcao`, `data_juros_mora`, `valor`, `descricao`
**Base de cálculo — `planilha-base-de-calculo.xlsx`:** idem **+ `percentual`**
**Outras Verbas — `planilha-outras-verbas.xlsx`:** `data_correcao`, `data_juros_mora`, `valor`
> Nota do modelo: *"O nome da parcela é inserida no sistema. O campo Descrição serve apenas para melhor especificar a natureza da verba."*

---

## 9. Endpoints do módulo (superfície da API)

| Método | Endpoint | Uso |
|---|---|---|
| POST | `/planjud/PublicoCalculoGeral/Create` | criar cálculo (retorna id) |
| POST | `/planjud/PublicoCalculoGeral/Edit` | editar (nova versão) |
| POST | `/planjud/PublicoCalculoGeral/IntervaloDatas` | gerar datas mensais do modo "Múltiplas" |
| POST | `/planjud/PublicoCalculoGeral/BuscarIntervaloSalarioMinimo` | fator acumulado por competência (modo Salário Mínimo) |
| POST | `/planjud/PublicoCalculoGeral/LerPlanilhaExcel` | ler upload xlsx |
| GET | `/planjud/PublicoCalculoGeral/VisualizarCalculo/{id}` | detalhamento do cálculo |
| POST | `/CalculoGeral/BuscarDataLimiteEC136` | teto de data-base sob EC 136 |
| POST | `{urlDatabasesSelicAdequacao}?codigoCalculo=` | data-base da SELIC / modal de adequação |
| GET | `/planjud/Permissao/Menu` | menu por perfil |
| GET | `/planjud/planilha/*.xlsx` | modelos de planilha |

**Erros de negócio (HTTP 400)** mapeados por `key`: `informacaoProcesso`, `criteriosCorrecaoMonetariaJurosMora`, `multaDescumprimetoAcordoObrigacao`, `honorarioAdvocaticios`, `honorarioSentenca`, `PartesParcela`, `outrasVerbas`, `astreintes`, `observacoes`.

---

## 10. Observações de curadoria / lacunas

- O **motor de cálculo é server-side**; as fórmulas acima foram derivadas dos cabeçalhos de detalhamento e das notas normativas exibidas. Os arredondamentos, fatores de correção efetivos e regras de juros por competência residem no back-end (não observáveis pelo front).
- **Data-base dos critérios** é dinâmica (ex.: "Débitos Gerais" = 08/2026, "Fazenda Pública" = 09/2026) — vem de base de índices atualizada periodicamente; deve ser conferida contra a tabela de índices do TJTO.
- Inconsistência cadastral provável na nota do critério **TR + IPCA-E** (ver §5.1).
- O manual público disponível (`/planjud/manual/…v1.0.pdf`) é de **25/06/2021** (v1.0), **desatualizado** frente à v5.0.19.7: não cobre SELIC/EC 113, EC 136, IPCA/Lei 14.905, Taxa Legal, nem o modo "Base de Cálculo".
- Módulo **Pensão Alimentícia** (`/PensaoAlimenticia/Create`) é separado e não foi objeto desta extração.
