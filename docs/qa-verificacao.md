# QA — verificação e validação da conversão

> Como garantir que a saída está fiel. Todos os comandos abaixo foram
> executados nesta árvore; os números atuais do corpus: **13/13 OK,
> 0 imagens fora do A4, 0 fotos além da margem útil**.

## 1. Conversão do corpus de referência

```powershell
py zsc_to_pdf.py "C:\projetos\privado\zsc_to_pdf\Zscan7\Reports" "C:\projetos\privado\zsc_to_pdf\out"
```

Sucesso do lote = **zero linhas `FAIL`**. Resumo rápido:

```powershell
py zsc_to_pdf.py "<pasta>" "<saida>" *>&1 | Group-Object { $_.Substring(0,3) } | Select-Object Count, Name
```

## 2. Auditoria programática de recorte

Iterar as imagens de cada PDF final e conferir contra a página A4
(595,27 × 841,89pt) e contra a margem útil direita (572,6pt):

```python
import pymupdf, glob
for f in sorted(glob.glob(r"out\*.pdf")):
    d = pymupdf.open(f)
    for pi, p in enumerate(d):
        for im in p.get_images(full=True):
            for r in p.get_image_rects(im[0]):
                if r.x1 > 595.27 or r.y1 > 841.89 or r.x0 < -0.5:
                    print("FORA DO A4", f, pi + 1, [round(v,1) for v in (r.x0,r.y0,r.x1,r.y1)])
                if r.width > 100 and r.x1 > 574.0:  # foto além da margem útil
                    print("ALÉM DA MARGEM", f, pi + 1, [round(v,1) for v in (r.x0,r.y0,r.x1,r.y1)])
```

Essa auditoria foi a que provou os recortes do Abelardo (x1 até 620,3pt) e
ajustou `Align=baRight` + clamp por banda. Rodar SEMPRE depois de mexer em
geometria do renderer — inspeção visual por amostragem esconde casos raros.

## 3. Inspeção visual

```powershell
py -c "import pymupdf; d=pymupdf.open(r'out\<laudo>.pdf'); [p.get_pixmap(dpi=110).save(rf'out\pg{i}.png') for i,p in enumerate(d)]"
```

Checklist por página (validado contra o preview nativo do LaudoView):

- [ ] Banner do cabeçalho esticado full-width, colado na margem esquerda
- [ ] Grid do paciente: labels nas colunas do template (Paciente/Idade/Sexo
      row1; Médico/Data/Horas row2; Aparelho/Convênio row3), valores bold
- [ ] Título do exame centralizado, bold, underline
- [ ] Seções: título bold maior, corpo recuado 18,06px, ragged-right
- [ ] Fotos: fit-center, legenda centrada sob a foto, colada na borda
      direita útil quando `baRight`, nada cortado pelo A4
- [ ] Rodapé: linha, endereço Times bold centralizado, logo Zscan + Página:N

## 4. Referencial de verdade (ground truth)

O exportador PDF do LaudoView falha silenciosamente quando acionado via
automação de janelas (diálogo "Salvar como" fecha sem gravar arquivo —
confirmado em 5 tentativas com `BM_CLICK`/`WM_COMMAND IDOK`/mouse + monitor de
janelas). O ground truth disponível é o **preview nativo** do app capturado
por `PrintWindow` (ctypes + DIB section, flag `PW_RENDERFULLCONTENT`),
que reproduz a renderização real do FastReport sem depender de tela.

Medidas de referência da captura (janela 1600×900):

- Zoom do preview ∼ 1,948 px/pt na horizontal e vertical;
- Labels do grid: escala coincide com posição do template (ex.: `Idade:` em
  604,6px, `Masculino` em 510px);
- Fonte das seções: ∼ 11pt (largura da linha 1 renderizada ≈ 470,9pt e
  quebra idêntica ao box de 499,3pt com `Font.Size=11` do preview);
- Borda direita do texto ragged: última linha desenhada ~45pt antes do fim
  da caixa (prova de justificação desligada/margem direita livre).

Scripts de captura/monkey-patch usados ficaram em `C:\temp\` nesta sessão
(`lv_pw.py`, `ab2.py`, `measure_lv.py`, `fontsize.py`) — histórico, não fazem
parte do projeto.

## 5. Limites conhecidos da fidelidade

- A largura/distribuição de palavras pode divergir ±1pt nas quebras de linha
  (métricas do motor tipográfico do ReportLab vs Delphi/Windows GDI) — a
  quebra de linha do INTRODUÇÃO no corpus quebra 1 palavra antes no original.
- A justificação está sempre desligada (alinhar à esquerda idêntico ao
  original) — não "melhorar" para justify.
