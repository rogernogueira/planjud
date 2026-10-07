# Planjud / Cálculo Geral — Referência técnica

Snapshot extraído em **2026-10** da instância `https://app.tjto.jus.br/planjud` (v5.0.19.7).
Os **GUIDs não mudam**, mas as **datas-base** sobem mensalmente (refletem o último índice publicado).

---

## 1. Critérios de Correção Monetária (16)

| Alias no script | id (GUID) | Início | dataBase* | Nota normativa |
|---|---|---|---|---|
| `DEBITOS_GERAIS` | `6e05166d-8733-4b73-b0eb-0589fcfc88a8` | 1964-10 | 2026-08 | IN 01/2018/TJTO — ORTN, OTN, IPC/STJ, BTN, IPC/IBGE, INPC, IPC-r, INPC (a partir 07/1995) |
| `FAZENDA_PUBLICA` | `80760894-3d39-4344-8792-2a2c7a27e926` | 1964-10 | 2026-09 | IN 05/2020/TJTO — mesmos até 29/06/2009, depois IPCA-E/IBGE |
| `DEBITOS_GERAIS_IPCA` | `55fb653f-954c-4c42-95c2-ac8578f71b19` | 1964-10 | 2026-08 | INPC até 08/2024 e IPCA a partir de 09/2024 (Lei 14.905/2024) |
| `PREVIDENCIARIO` | `546edcd7-ea0f-4c05-9272-84f422c7217b` | 1964-10 | 2026-08 | índices da JF p/ benefícios previdenciários (IRSM, URV, IGP-DI 05/1996–08/2006, INPC após) |
| `CONDENATORIAS_JF` | `cea51753-4dcc-424b-b8af-c5a20bf4d599` | 1964-10 | 2026-09 | índices da JF p/ condenações: UFIR 01/1992–12/2000, IPCA-E a partir 01/2001 |
| `IGP_DI` | `8a20e64b-5cc4-43fe-80d1-f025e8ba15e7` | 1964-10 | 2026-09 | IGP-DI (FGV) em todo o período |
| `IGP_M` | `06fc9bab-70c4-4286-80fc-1d560f4e39a6` | 1989-06 | 2026-09 | IGP-M (FGV) |
| `INCC` | `6afc9ce7-3997-4a35-ab94-108ef301d110` | 1964-10 | 2026-09 | INCC (FGV) |
| `INPC` | `b17bff33-e054-48b4-bc47-759885db09e7` | 1979-04 | 2026-08 | INPC (IBGE) |
| `IPCA` | `a4b46250-810a-4c58-8078-b721f9ca82c3` | 1980-01 | 2026-08 | IPCA (IBGE) |
| `IPCA_E` | `eac4cc31-c420-49c3-b474-cf1284c61770` | 1992-01 | 2026-09 | IPCA-E (IBGE) |
| `SELIC_FAZENDA` | `e2b28c79-3671-427b-a4a5-e83be9ac7ea7` | 2021-12 | 2026-09 | SELIC a partir de 12/2021 (EC 113/2021) |
| `SELIC_TRIBUTARIO` | `f88f3e52-6b91-47ed-9a8b-102cf5e2ad10` | 1995-01 | 2026-10 | SELIC Tributário (BACEN) |
| `TR_IPCA_E` | `de424b12-8b1d-4c07-9014-4ac419dc3463` | 1994-07 | 2026-09 | TR até 25/03/2015 e IPCA-E depois ⚠ (nota do sistema cita "26/03/2025" — provável erro cadastral) |
| `IGPM_IPCA` | `a2a688c6-8511-4f78-a642-6ca00eccac46` | 1994-07 | 2026-08 | IGP-M até 29/06/2009 e IPCA depois |
| `TR` | `7de9d3d7-912f-42b0-81d7-9b38ae83332f` | 1994-07 | 2026-10 | TR (BACEN) |

\* dataBase = último mês com índice disponível naquele critério; o sistema aceita data-base maior, mas o fator **não avança** além disso.

## 2. Critérios de Juros de Mora (12)

| Alias | id (GUID) | Regra |
|---|---|---|
| `SEM_JUROS` | `19762eda-1aad-4b9f-9d57-f2ea46598b9f` | sem juros |
| `JUROS_6_12` | `3fbfea4d-079a-46e8-9f48-ec65d0fa9d27` | 6% a.a. até 12/2002 e 12% a.a. em diante |
| `JUROS_6` | `bb6bbf4b-c2b9-4fc3-84b0-c3a9b7483437` | 6% a.a. todo o período |
| `JUROS_12` | `6599f453-b9aa-4fa0-afea-65a502242837` | 12% a.a. todo o período |
| `JUROS_12_6` | `c8b23932-54ad-41a6-8a79-d0501a746a1a` | 12% a.a. até 06/2009 e 6% a.a. depois |
| `JUROS_12_POUPANCA` | `e0f73128-f6df-4576-bfe2-4e2f52858996` | 12% a.a. até 06/2009 e poupança (dia 1º) depois |
| `FAZENDA_GERAL` | `86de7d17-ba2f-4c07-a23a-fd9bcabce37b` | Fazenda Pública: 0,5% a.m. até 01/2003; 1% a.m. até 06/2009; depois poupança (art. 1º-F Lei 9.494/97) |
| `FAZENDA_SERVIDORES` | `56d7a4e7-91db-47f5-ba47-0caee92c9a30` | 1% a.m. até 07/2001; 0,5% a.m. 08/2001–06/2009; depois poupança |
| `FAZENDA_PREVIDENCIARIO` | `83512a76-57f9-4cf4-b8c8-f645f41434d9` | 1% até 06/2009 (DL 2.322/87); depois poupança |
| `FAZENDA_POUPANCA` | `b84c22f4-5348-41c1-8e96-b7a2695e1cfb` | exclusivamente poupança (0,5% a.m. 08/2001–06/2009; depois poupança) |
| `TAXA_LEGAL` | `7a7abf7c-fce1-46e4-aa36-1e5698008a91` | TL – Taxa Legal (art. 406, §1º, CC) — a partir 08/2024 |
| `JUROS_6_12_TL` | `e32593ba-7d11-4b37-9554-31ed9cf66010` | 6% até 12/2002; 12% até 07/2024; TL a partir 08/2024 |

---

## 3. Payload de `POST /planjud/PublicoCalculoGeral/Create`

```jsonc
{
  "id": null, "seq": 0, "codigoCalculo": "",
  "informacaoProcesso": { "numeroProcesso": null, "orgaoJulgador": null, "requerente": null, "requerido": null },
  "criterioCorrecaoMonetariaJurosMora": {
    "criterioCorrecaoMonetaria": "<GUID correção>",
    "criterioJurosMora": "<GUID juros>",
    "atualizacaoAteDataBase": "2026-08-01T00:00:00",   // data-base
    "decisaoSelicFazenda": 2,                           // 1=Decisão 388/2022, 2=Decisão 434/2023
    "calculoCumuladoComSelic": false,
    "permitirDeflacao": false,
    "aplicarEC136": false,
    "inicioAplicacaoEC136": null,
    "criterioPosCorteEC136": null                       // "EC136" | "CODIGO_CIVIL"
  },
  "multaDescumprimentoObrigacao": { "AplicaMultaDescumprimentoAcordoObrigacao": false, "PercentualMulta": null },
  "honorariosAdvocaticios":        { "id": null, "tipoHonarioAdvocaticios": 1, "percentual": 0, "valor": 0,
                                     "dataFixacaoAjuizamentoIncidencia": null, "dataJurosMora": null,
                                     "escalonado": false, "honorariosEscalonados": [] },
  "honorarioAdvocaticioSentenca":  { "percentual": 0, "valor": 0, "tipoHonarioAdvocaticios": 1,
                                     "dataFixacaoAjuizamentoIncidencia": null, "dataJurosMora": null,
                                     "honorariosEscalonados": [], "escalonado": false },
  "multaArt523": { "Multa10Porcento": false, "HonorariosAdvocaticios": false },
  "listaPartesParcelas": [
    { "seq": 1, "dataJurosCorrecao": "2011-04-01T00:00:00", "dataJurosMora": null,
      "valor": 645.36, "nomeParcela": "Aluguel", "descricao": "",
      "percentual": "", "tipoParteParcela": 1, "id": "" }
    // uma entrada por parcela; seq incrementa 1..n; tipoParteParcela=1 (individual)
  ],
  "listaOutrasVerbas": [],
  "listaAstreintes": [],
  "observacao": "",
  "aplicarEC136": false, "inicioAplicacaoEC136": null, "criterioPosCorteEC136": null
}
```

- `valor` é **decimal em reais** (645.36), não centavos.
- `dataJurosMora` = termo inicial dos juros **daquela parcela**; `null` ⇒ sem juros.
- Honorários `tipoHonarioAdvocaticios: 1` = "Sem Honorários" (necessário para não gerar honorários).

## 4. Endpoints

| Método | Endpoint | Uso |
|---|---|---|
| GET | `/planjud/PublicoCalculoGeral/Create` | handshake (cookies de sessão/antiforgery) |
| POST | `/planjud/PublicoCalculoGeral/Create` | cria o cálculo → devolve o **id** (string GUID) |
| GET | `/planjud/PublicoCalculoGeral/VisualizarCalculoInformacaoCalculo/{id}` | **JSON do resultado** |
| POST | `/planjud/PublicoCalculoGeral/Edit` | edita (nova versão) |
| POST | `/planjud/PublicoCalculoGeral/IntervaloDatas` | datas mensais (modo "Múltiplas") |
| POST | `/planjud/PublicoCalculoGeral/BuscarIntervaloSalarioMinimo` | fator acumulado (modo salário mínimo) |
| POST | `/planjud/PublicoCalculoGeral/LerPlanilhaExcel` | ler upload `.xlsx` |
| POST | `/CalculoGeral/BuscarDataLimiteEC136` | teto da data-base sob EC 136 |
| GET | `/planjud/Permissao/Menu` | menu por perfil |

Cabeçalhos: `Content-Type: application/json` e `X-Requested-With: XMLHttpRequest`.
O servidor **não exige token antiforgery** nos endpoints de API (o cookie de sessão basta).

## 5. Estrutura do resultado (JSON)

Chaves principais:

- `codigoCalculo` (ex.: "2026 TMQ 338668"), `dataBase`, `criterioCorrecaoMonetario`, `criterioJurosMora`
- `partesParcelas.parteParcelasResumo[]` — resumo por parcela (`valorPrincipal`, `valorCorrigido`, `jurosMora`, `selic`, `total`)
- `partesParcelas.parcelasDetalhadoDetalhado[].listaPartesParcelasDetalhados[]` — detalhamento por item:
  - `valorParcela`, `termoInicioCorrecaoMonetariaString`, `fatorCorrecao` (pt-BR, ex. "2,3183389"),
    `valorCorrigido`, `termoInicioJurosMoraString`, `valorJurosMora`, `valorSelic`, `total`
  - colunas EC 136: `indiceIPCA`, `valorPrincipalCorrigidoEC136`, `juros2aa`, `valorJuros2aa`, `valorSelicEC136`, `valorTaxaLegal`
- `subTotal1..subTotal5`, `multaDescumprimentoObrigacao`, `multa10PorCentoArt523`, `multa10PorCentoHonorariosArt523`
- `outrasVerbasResumoDetalhado`, `astreintesResumoDetalhada`
- `total` (`descricao`, `valorCorrigidoString`, `total`) — **total geral**
- `status` (0 = Não Gerado / 1 = Gerado), `visualizarSelic`, `aplicarEC136`, `criterioPosCorteEC136`, `observacao`

> `subTotal1.valorCorrigidoString` = soma **só da correção** das parcelas; `total.total` = correção **+ juros + selic**.

## 6. Regimes especiais

- **EC 113/2021** — SELIC unificada a partir de 12/2021; incompatível com termo de juros em parcelas após 12/2021 quando cumulado.
- **EC 136/2025 (Provimento 207/CNJ)** — principal corrigido pelo **IPCA**; juros de mora **2% a.a.** sobre principal corrigido; **SELIC só incide se < IPCA + 2% a.a.** (teto). Alternativa "Código Civil" usa **Taxa Legal**. Campos: `aplicarEC136`, `inicioAplicacaoEC136`, `criterioPosCorteEC136`.
- **Lei 14.905/2024** — IPCA a partir de 09/2024 (critério `DEBITOS_GERAIS_IPCA`).
