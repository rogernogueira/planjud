# Extração e proveniência

> Como as regras de negócio e a interface HTTP deste projeto foram obtidas, para
> rastreabilidade e manutenção futura.

## Fontes (2026-10-07 · Planjud v5.0.19.7)

| # | Fonte | O que forneceu |
|---|---|---|
| 1 | HTML da view `GET /planjud/PublicoCalculoGeral/Create` | estrutura das abas/campos e os **arrays de opções** (critérios de correção/juros, honorários, escalonados) embutidos no `data()` do Vue |
| 2 | Bundle `/planjud/js/app.js` (~2,8 MB, minificado) | os 19 componentes Vue (PartesParcela, OutrasVerbas, Astreintes, HonorarioAdvocaticios, MultaArt523…) — `data/watch/methods/computed` contêm as **regras de validação** |
| 3 | Manual oficial `/planjud/manual/…v1.0.pdf` (46 pp., 25/06/2021) | descrição campo a campo, workflow e permissões — **desatualizado** (não cobre SELIC/EC 136/Lei 14.905/Taxa Legal) |
| 4 | Planilhas-modelo `.xlsx` (`/planjud/planilha/*.xlsx`) | colunas esperadas no upload |
| 5 | `GET /planjud/Permissao/Menu` | enumeração dos módulos do sistema |

## Método

1. **Coleta por `curl`** — a página é renderizada no servidor (Razor) com um app Vue
   montado por cima; o `curl` obtém o HTML completo e o bundle. (`browser_navigate`
   deu timeout; `curl` responde em ~1 s.)
2. **Desminificação do bundle** — quebra por `{`, `}` e `;` para tornar o arquivo
   navegável; em seguida, corte das **funções de render** (que começam em
   `var e=this,t=e._self._c`), isolando as seções de **lógica** de cada componente.
3. **Extração dos dados de referência** — as listas de critérios (16 de correção +
   12 de juros) com GUIDs e notas normativas foram parseadas do JSON embutido no HTML.
4. **Engenharia reversa da API** — o front usa `axios.post(url, data)` com
   `X-Requested-With: XMLHttpRequest` e `withCredentials`. Replicou-se o payload do
   `dataForm` com `curl` (cookie de antiforgery obtido num `GET` prévio). O `POST`
   devolve o **id** do cálculo; um `GET` em
   `VisualizarCalculoInformacaoCalculo/{id}` devolve o **JSON do resultado**.

## Endpoints

| Método | Endpoint | Uso |
|---|---|---|
| GET | `/planjud/PublicoCalculoGeral/Create` | handshake (cookies de sessão/antiforgery) |
| POST | `/planjud/PublicoCalculoGeral/Create` | cria o cálculo → devolve o **id** |
| GET | `/planjud/PublicoCalculoGeral/VisualizarCalculoInformacaoCalculo/{id}` | **JSON do resultado** |
| POST | `/planjud/PublicoCalculoGeral/Edit` | edita (nova versão) |
| POST | `/planjud/PublicoCalculoGeral/IntervaloDatas` | datas mensais (modo "Múltiplas") |
| POST | `/planjud/PublicoCalculoGeral/BuscarIntervaloSalarioMinimo` | fator acumulado (salário mínimo) |
| POST | `/planjud/PublicoCalculoGeral/LerPlanilhaExcel` | ler upload `.xlsx` |
| POST | `/CalculoGeral/BuscarDataLimiteEC136` | teto da data-base sob EC 136 |
| GET | `/planjud/Permissao/Menu` | menu por perfil |

O servidor **não exige token antiforgery** nos endpoints de API (o cookie de sessão basta).
Certificado TLS de produção é válido.

## Achados e decisões

- O **motor de cálculo é server-side**; a ferramenta não reimplementa a matemática —
  dirige o sistema oficial e lê o resultado.
- **Juros de mora exige termo inicial por parcela** (`dataJurosMora`); sem ele, R$ 0,00.
- **Data-base adiante não avança o fator**: o cálculo capa no último índice publicado.
- ⚠️ **Provável erro cadastral** no critério *"TR + IPCA-E"*: a nota diz
  *"IPCA-E a partir de 26/03/2025"* quando o corte de 2015 é que faz sentido.
- O **catálogo de ids/datas-base** é um snapshot; revalidar periodicamente com `--list`.

## Comparação com o Ex-Proc/CPC

O regime de **EC 136/2025 (Provimento 207/CNJ)** corrige o principal pelo **IPCA** e
aplica **juros de mora de 2% a.a.** sobre o principal corrigido, com **teto** — a SELIC
só incide se for **menor que IPCA + 2% a.a.**. O sistema expõe essas colunas no
detalhamento (A–L), conforme `docs/regras-de-negocio.md`.
