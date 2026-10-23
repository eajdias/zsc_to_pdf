# Agent Memory — zsc_to_pdf

> Consulte antes de cada tarefa; atualize a cada correção/aprendizado.
> Formato: ❌ <não faça> → ✅ <faça> (porque). Entradas curtas e acionáveis.

## Erros / Lições (não repetir)
- 2026-10-23 ❌ Resolver o template FastReport com `root.find("TfrxReport")` → ✅ O template vive em `<report><TfrxReport/>` + `<sourcepages><TfrxReportPage/>`; o `<dictionary>` usa `PageN.ObjName` onde N = índice em `sourcepages` (porque `TfrxReport` não é filho direto da raiz nem contém objetos — as posições/fontes dos objetos estão nas páginas de design de `sourcepages`; bug que deixou toda a saída em x=1.5).
- 2026-10-23 ❌ Desenhar memos com largura fixa do template quando `AutoWidth='True'` → ✅ Setar `nowrap` para esses (porque labels "Data :" / "Médico Solicitante:" quebravam em 2 linhas com largura mínima do design).
- 2026-10-23 ❌ Fallback de fonte registrando sempre a variante regular → ✅ Fallback deve preservar bold/italic (ex.: `ms sans serif` → arial) (porque o RichView cabeçalho declare `f0\fnil\fcharset0 MS Sans Serif` com `\b` — cair para Arial regular distorce o rodapé).

- 2026-10-23 ❌ Desenhar texto/imagem apenas com coordenada "printable" (x=1.5pt na página) → ✅ Página-absoluta = `margin_left + printable_x` (aplicar `ml_pt` em `wrap_and_draw` e `draw_image`, não só em `draw_line`) — a margem esquerda de 15,9mm estava faltando em TODO o conteúdo textual; descoberto comparing A/B com o preview nativo renderizado pelo LaudoView (PrintWindow).
- 2026-10-23 ❌ Renderizar `haBlock` como justify (estica word-spacing até a borda) → ✅ `haBlock` e `\qj` devem renderizar como LEFT (porque a medição pixel do preview original mostrou a linha terminando ~45pt antes da borda direita = ragged-right; o FR original não justifica).
- 2026-10-23 ✅ Ground truth visual do LaudoView: o PDF export não pôde ser obtido (o exportador falha silenciosamente ao clicar Salvar via automação de mensagens); usar o **preview nativo** (TfrxPreview) capturado com `PrintWindow` como referência — layout/fontes/posições conferidos: escala do preview ~1.948 px/pt, seções 11pt, grid bate 1:1. Banner do cabeçalho no preview aparece roxo (peculiaridade do LaudoView/db), mas o fiel ao .ZSC é o JPEG do `picturecache` (rosa/laranja item0) — usar o do arquivo.

- 2026-10-23 ❌ Substituir só `w` quando o preview diverge do template com `Align=baRight` (x ficava do template e a foto atravessava a borda do A4 até 27pt fora) → ✅ Recalcular o `x` do Align com a largura FINAL (`baRight`: x=band_w−w; `baCenter`: recentra) quando o preview NÃO traz `l`/`Left` explícito — semântica do FR, que ancora na borda no momento da impressão (porque templates Abelardo carregam preview `w=196` sobre template `W=160` e a foto saía do A4; com o recompute, fotos+legendas colam na borda direita útil).
- 2026-10-23 ❌ Confiar que o clamp do objeto basta → ✅ Clamp por BANDA em `render_band` (max x+w dos filhos; se > PRINTABLE_W, shift em `band_left`): foto e legenda deslocam JUNTAS e o alinhamento não quebra (porque a banda `l=2,63` empurrava o conteúdo ancorado 2pt para fora mesmo após o recompute do Align).
- 2026-10-23 ✅ Auditoria de recorte: iterar `p.get_images(full=True)` + `get_image_rects` no PDF final e comparar bbox com a página (X4=595,27 / Y1=841,89) e com a margem útil (572,6) — o corpus inteiro fecha com 0 imagens fora; auditoria programática pega corte que inspeção visual por amostragem esconde.

## Padrões / Preferências (o que funciona)
- 2026-10-23 ✅ Sempre que resolver objeto do preview, aplicar overrides nesta ordem: preview `l/t/w/h` → preview `Left/Top/Width/Height` (alguns objetos rich/ картины carregam attrs template-style no próprio preview, inclusive `PropData` com o RTF real, que vence o do template).
- 2026-10-23 ✅ Bandas MasterData de 3 colunas: coluna vem do atributo `l` da própria banda (0/237/474); largura da banda para Align baCenter/baRight/baWidth vem do `Width` da def da banda.
- 2026-10-23 ✅ saída fiel validada nos 13 .ZSC de `Zscan7\Reports` (conferência visual inclui legenda de fotos m18 com `u=''` sendo ausência real de dado).
