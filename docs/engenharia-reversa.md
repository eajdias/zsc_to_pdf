# Engenharia reversa — como chegamos aqui

> Registro do processo de RE do `LaudoView.exe` e do formato `.ZSC`, com os
> caminhos que funcionaram e os que travaram. Consulte antes de qualquer
> nova investigação do binário ou de variantes do formato.

## Alvo

- `LaudoView.exe` 5.0.0.106, Delphi + FastReport VCL embutido
  (`frxExportPDF`/`TfrxPDFFile` no binário).
- Corpus: 13 `.ZSC` em `Zscan7\Reports` (pacientes de teste:
  "Adelson Santiago dos Santos", "Italo Vale Viana").

## Caminho que funcionou

1. **UPX unpack** (UPX 5.2.1): `LaudoView.exe` → `LaudoView_unpacked.exe`.
2. **Ghidra headless + script PyGhidra** via shell: análise completa do
   binário Delphi com strings dos serializadores XML em minutos (~84s).
   Os serializadores decompilados ficaram em `C:\temp\opencode\laudoview\decomp_out\`
   (`fn_00505418.c`, `fn_00507848.c` — save/load do relatório preparado).
3. **Análise do corpus**: os `.ZSC` comprovaram a estrutura real
   (`<report>` sem objetos; template em `sourcepages`; dicionário
   `PageN.ObjName`; `picturecache` 1-based).
4. **Ground truth visual**: execução real do LaudoView com um `.ZSC`, janela
   movida ao monitor primário, captura via `PrintWindow` e comparação
   pixel-métrica contra os PDFs gerados (produziu as 2 correções de fidelidade
   maiores: margem esquerda ausente e `haBlock`→esquerda).

## Caminhos que TRAVARAM (não perder tempo de novo)

- **REA MCP para análise Ghidra pesada**: "Request timed out" determinístico.
  Ghidra headless é o caminho.
- **Exportar PDF do LaudoView via automação de janelas**: o diálogo "Salvar
  como" fecha sem gravar, silencioso (5 tentativas: `BM_CLICK` no botão,
  `WM_COMMAND IDOK`, mouse sintético no botão, monitoramento de janelas
  novas). Suspeita: caminho do exportador antigo incompatível com o SO atual.
  Um dia pode valer rodar o app em compatibilidade XP/7 — não era o escopo.
- **PIL.ImageGrab para capturar janela**: pega a TELA inteira (exponha a
  mesa do usuário) e depende de z-order/foco. `PrintWindow` captura só a
  janela alvo mesmo oculta — sempre preferir.
- Ordem fatal no ctypes: **ler o buffer do DIB antes do `DeleteObject`** —
  invertido dá 0xC0000005 silenciosa.

## Descobertas-chave na sequência

- `TfrxReport` de `<report>` não é filho direto da raiz e não contém objetos
  (bug inicial: toda saída nasceu em x=1,5).
- `striprtf` expõe `rtf_to_text` só em `striprtf.striprtf.rtf_to_text`
  (o `__init__.py` tem apenas `__version__`); importar com alias.
- Preview carrega attrs template-style nos objetos rich (`Left/Top/Width`,
  `PropData` próprio) e vence o template nos conflitos de geometria.
- Nas fotos com 3 colunas (Italo/Adelson), o offset da coluna vem do atributo
  `l` da PRÓPRIA banda do preview (0/237/474), não de ColWidth do template.
- Nos templates do Abelardo o `Align=baRight`/`baCenter` precisa ser
  recalculado com a largura final do preview (a diferença entre `w` do
  preview e `W` do template transforma a âncora) + clamp por banda
  (embalava foto+legenda quando o conjunto ultrapassa `PRINTABLE_W`).

## Semântica completa do formato

Documentada em [`formato-zsc.md`](formato-zsc.md) — fonte única de verdade do
conversor; atualizar junto com o código quando descobrir nova quirk.

## Ferramentas usadas

UPX 5.2.1 (winget) · Ghidra headless + PyGhidra · Python 3.14 global
(`pymupdf`, `reportlab`, `pillow`, `striprtf`, `numpy` para medições) ·
ctypes/user32 para automação e captura de janelas.
