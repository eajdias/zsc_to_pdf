# Formato do arquivo `.ZSC` (relatório preparado FastReport VCL)

> Documentação da especificação decodificada por engenharia reversa do
> `LaudoView.exe` 5.0.0.106 + análise do corpus de laudos. O conversor
> (`zsc_to_pdf.py`) implementa exatamente estas regras.

## Estrutura XML

Um `.ZSC` é um relatório **preparado** do FastReport VCL salvo como XML,
tags sem espaços de nomes (UTF-8):

```
<preparedreport>
  <outline/> <logicalpagenumbers/>
  <previewpages>     páginas como o motor RENDERIZOU na hora da geração
  <report>           <TfrxReport/> apenas com atributos (sem objetos)
  <sourcepages>      páginas de DESIGN: <TfrxReportPage> com bandas e
                     definições dos objetos (posição, fonte, alinhamento)
  <dictionary>       chave curta -> "PageN.ObjectName"
  <picturecache>     imagens binárias em hex (JPEG/BMP)
</preparedreport>
```

### `<previewpages>`

Uma página ("prévia") por `<page>`:

- **Bandas**: `bN` com atributos `t` (top em px a partir da área útil),
  `l` (offset da coluna em layouts multicolumn), `h` (altura renderizada).
  Bandas fila de `TfrxNullBand` marcam fim de página.
- **Objetos**:
  - `mN` — texto final já renderizado no atributo `u`; opcionalmente `t/h/w`,
    `Font.Size` (o valor efetivo), `PropData` (RTF próprio), atributos de
    estilo de template (`Left/Top/Width/Height`).
  - `pN` — imagem: `ImageIndex` (índice **1-based** em `<picturecache>`),
    opcionalmente `l/t/w/h`.
  - `lN` — linha horizontal.
  - `rN` — rich text: sem texto no preview; o conteúdo real vive no
    `PropData` hex (RTF) — o do preview vence o do template.

### `<dictionary>`

Mapeia cada chave curta do preview para o objeto de template:
`<m3 name="Page0.Memo3"/>` ⇒ o elemento `m3` do preview herda a geometria de
`sourcepages[0]` → objeto `Memo3`. Resolver **sempre** por esse par
(página de design + Name) — o `TfrxReport` de `<report>` não contém objetos e
NÃO é filho direto da raiz.

### `<picturecache>`

Itens em ordem de documento; `<item stream="hexadecimal"/>`. JPEG (incl. os do
corpus: 720×109 banner, 572×466 fotos) e BMP (logo da rodapé 89×24).
`ImageIndex` do preview é **1-based** sobre essa lista.

## Semânticas validadas (regras do motor)

### Unidades e origem

- Toda coordenada do FastReport é **pixel de tela @ 96 DPI** relativa à
  **área imprimível** (papel menos margens). Conversão: `1 pt PDF = 0,75 px`.
- A4: 210×297mm ⇒ página 595,27×841,89pt; largura útil = 703,46124172px
  (constante `PRINTABLE_W`); margens do corpus: esquerda 15,875mm (45pt),
  topo 6,00075mm (17pt), direita 8,001mm (~22,7pt).
- Página-absoluta = `margem_esquerda + x`; o eixo y cresce para baixo no
  FastReport e é invertido para o PDF (`y_pdf = altura - margem_topo - t`).

### Resolução de geometria do objeto

Prioridade (cada atributo, individualmente, do mais forte para o mais fraco):

1. Atributo curto do preview (`l/t/w/h`);
2. Atributo template-style do preview (`Left/Top/Width/Height`);
3. Definição no template via `<dictionary>`.

A largura da BANDA para alinhamentos (`Align` da def) vem de
`TfrxMasterData/Width` (default 703,46). Nas bandas de fotos com 3 colunas o
offset por coluna vem do atributo `l` da própria banda no preview (0/237/474
no corpus Italo/Adelson).

### Alinhamentos (`Align` da definição)

| Valor | Semântica implementada |
| --- | --- |
| `baWidth` | `x=0, w=largura_da_banda` (banner do cabeçalho: esticado full-width) |
| `baCenter` | `x=(banda-w)/2` |
| `baRight` | `x=banda-w` (ancora na borda direita da banda) |
| `baLeft` / ausente | usa `Left` do template |

Detalhe importante (`w` final ≠ `w` template): o FastReport **recalcula a
âncora na hora da impressão** com a largura final. O conversor replica isso
quando o preview NÃO traz `l`/`Left` explícito (fotos do Abelardo: preview
`w=196` sobre template `W=160` — sem o recompute a foto saía até 27,7pt do A4).

### Texto (`mN`)

- `u` = texto final; sem `u` ⇒ nada impresso (ausência real de dado).
- `AutoWidth='True'` no template ⇒ **não quebra linha** (ex.: labels `Data :`,
  `Médico Solicitante:` desenhavam em 2 linhas com a largura mínima do design).
- `HAlign`: `haLeft` (default), `haCenter`, `haRight`, `haBlock` → o
  FastReport **não justifica** nesse contexto; renderiza como esquerda
  (validado: a linha do original termina ~45pt antes da borda direita).
- Gap interno do memo: 2px horizontal, 1px vertical (defaults FR).
- Fontes do template: `Font.Height` negativo em px (−13 ⇒ 9,75pt);
  o `Font.Size` do preview, quando presente, é o efetivo da renderização
  (validado por largura de linha ~11pt e ponto de quebra).
- `MS Sans Serif` → Arial preservando bold/italic; fallback de fonte
  preserva variantes (o rodapé do RichView declara
  `f0\fnil\fcharset0 MS Sans Serif` com `\b`).
- Bits de `Font.Style` no template: 1=bold, 2=italic, 4=underline.

### Rich text (`rN`)

RTF em `PropData` (hex) — do preview quando existir, senão do template
(rodapé "Av. Nagib Mutran" usa o do preview: Times bold fs24, 1 linha).
Parsing próprio mínimos: `\fcharset0` resolve a fonte da fonttbl, `\b`, `\i`,
`\ul`, `\qc/\qr/\qj/\ql`.

### Fotos

- Fotos de exame: **fit-center** na caixa da coluna (proporção preservada).
- Banner do cabeçalho (`piccab`/`piccab1`, `Align=baWidth`): esticado full-width.
- Clamp por BANDA: se o conteúdo da banda (foto+legenda) ultrapassa
  `PRINTABLE_W`, a banda inteira desloca à esquerda — os dois objetos
  deslocam juntos e o alinhamento legenda↔foto nunca quebra.

## Peculiaridades conhecidas (não são bugs)

- Legendas com `u=''` são ausência real de dado no preview (lote Adelson).
- Erros de digitação dos dados ("Ensdoscopia", "PODÉ") são reproduzidos como
  estão — fidelidade ao arquivo.
- O LaudoView na apresentação mostra o banner do cabeçalho em roxo/azul (logo
  próprio do app/db); o fiel ao `.ZSC` é o JPEG do `picturecache`
  (rosa/laranja) 720×109 — o conversor usa o do arquivo.
- `Página: N` no rodapé é dado do preview (`m18`/`m20`), não enumerado por nós.
