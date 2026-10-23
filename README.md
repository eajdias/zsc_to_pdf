# zsc_to_pdf — Conversor Zscan `.ZSC` → PDF

Conversor de laudos do sistema **Zscan** (arquivos `.ZSC`) para PDF, construído
por engenharia reversa do `LaudoView.exe` 5.0.0.106 (Delphi + FastReport VCL).
Roda 100% offline, sem o Zscan, Firebird ou LaudoView — o `.ZSC` traz tudo
(texto renderizado + imagens em cache), preservando layout, fontes, páginas
e fotos.

**Status atual: 13/13 laudos do corpus convertidos com layout fiel**
(0 imagens fora do A4 — ver [`docs/qa-verificacao.md`](docs/qa-verificacao.md)).

## Documentação

| Arquivo | Conteúdo |
| --- | --- |
| [`docs/formato-zsc.md`](docs/formato-zsc.md) | Especificação completa do formato `.ZSC` e semânticas do motor FastReport |
| [`docs/qa-verificacao.md`](docs/qa-verificacao.md) | QA: conversão do corpus, auditoria de recorte, checklist visual, ground truth |
| [`docs/engenharia-reversa.md`](docs/engenharia-reversa.md) | Processo de RE do binário, caminhos que funcionaram e que travaram |

## Requisitos

- Python 3.10+ (máquina padrão: 3.14 via launcher `py`)
- Fontes TrueType do Windows (`C:\Windows\Fonts`): Arial, Tahoma,
  Times New Roman, Courier New

```powershell
py -m pip install reportlab pillow striprtf
```

## Como usar

```
py zsc_to_pdf.py <entrada> [saída]
```

### Conversão individual

```powershell
py zsc_to_pdf.py "C:\laudos\LAUDO.ZSC"              # -> LAUDO.pdf ao lado
py zsc_to_pdf.py "C:\laudos\LAUDO.ZSC" "C:\pdfs\laudo_italo.pdf"
```

### Conversão em lote

```powershell
py zsc_to_pdf.py "C:\laudos"                        # .pdf ao lado de cada .ZSC
py zsc_to_pdf.py "C:\laudos" "C:\pdfs"              # pasta de saída dedicada
```

- Processa `*.ZSC`/`*.zsc` da pasta (não recursivo); saída = mesmo nome,
  extensão `.pdf`; a pasta de saída é criada se não existir.
- Arquivo com problema imprime `FAIL <arquivo> -> <erro>` e o lote segue;
  sucesso = **zero linhas FAIL**.

### Como biblioteca

```python
from zsc_to_pdf import convert
convert(r"C:\laudos\LAUDO.ZSC")        # ou convert(path, "saida.pdf")
```

## Corpus e validação

Os laudos de referência ficam em `Zscan7\Reports\` (**não versionados** —
dados de paciente; ver `.gitignore`). Validar qualquer mudança:

```powershell
py zsc_to_pdf.py "Zscan7\Reports" "out"   # 13/13 OK = verde
```

## Estrutura

```
zsc_to_pdf/
├── zsc_to_pdf.py     # conversor único (CLI + biblioteca)
├── docs/             # documentação técnica complementar
├── Zscan7/           # corpus local de validação (gitignored)
├── out/              # PDFs gerados (gitignored)
└── .opencode/memory/ # lições de RE e semânticas (versionado)
```

## Solução de problemas

Detalhes em [`docs/qa-verificacao.md`](docs/qa-verificacao.md) — resumo:

- `FAIL ... previewpages ausente`: o `.ZSC` não é um laudo preparado do
  FastReport (outro tipo de arquivo do Zscan).
- Fonte faltando: edite `FONT_FILES` no script (fallback preserva bold/italic).
- `striprtf`: a função fica em `striprtf.striprtf.rtf_to_text` (não na raiz).
