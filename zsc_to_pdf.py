#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ZSC -> PDF converter for Zscan (.ZSC FastReport VCL prepared-report XML).

Reverse-engineered format (LaudoView.exe 5.0.0.106 + ZSC corpus analysis):
  .ZSC = FastReport prepared report saved by Zscan as XML, structure:
    <preparedreport>
      <previewpages>            pages as rendered: bands bN + objects
                                mN (text) / pN (picture) / lN (line) / rN (rich)
      <outline/> <logicalpagenumbers/>
      <report><TfrxReport/></report>
      <sourcepages>             design pages: TfrxReportPage with bands and
                                object definitions (positions, fonts)
      <dictionary>              short key (b1,m2,p3...) -> "PageN.ObjectName"
      <picturecache>            binary pictures, hex-encoded (JPEG/BMP)
    </preparedreport>

  Rendering model recovered from binary + data:
    - Coordinates: FastReport units = screen pixels @ 96 DPI relative to the
      printable area (paper minus margins). 1 PDF pt = 0.75 units.
    - Preview values describe what the engine RENDERED (u = final text,
      h = rendered height, t = band-relative top, l = column offset,
      ImageIndex = 1-based picture index). Preview overrides template.
    - Object defecto geometry comes from the template in <sourcepages>;
      dictionary "PageN.Name" -> sourcepages[N] object with that Name.
    - Band Align semantics: baWidth (x=0, w=band), baCenter/baRight recenter,
      baLeft keeps Left.
    - picturecache indexes are 1-based via the preview ImageIndex.

Usage:
    py zsc_to_pdf.py <file.ZSC> [out.pdf]
    py zsc_to_pdf.py <folder-with-ZSC> [outFolder]
"""
import argparse
import io
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

from striprtf.striprtf import rtf_to_text as _rtf_to_text
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

PT_PER_PX = 0.75  # FastReport pixel unit -> PDF point
PRINTABLE_W = 703.46124172  # A4 printable width in FastReport px (LeftMargin 15.875mm)


def px2pt(v):
    return v * PT_PER_PX


FONT_DIR = r"C:\Windows\Fonts"

FONT_FILES = {
    ("arial", False, False): "arial.ttf",
    ("arial", True, False): "arialbd.ttf",
    ("arial", False, True): "ariali.ttf",
    ("arial", True, True): "arialbi.ttf",
    ("ms sans serif", False, False): "arial.ttf",
    ("ms sans serif", True, False): "arialbd.ttf",
    ("tahoma", False, False): "tahoma.ttf",
    ("tahoma", True, False): "tahomabd.ttf",
    ("times new roman", False, False): "times.ttf",
    ("times new roman", True, False): "timesbd.ttf",
    ("times new roman", False, True): "timesi.ttf",
    ("courier new", False, False): "cour.ttf",
}
_font_cache = {}


def register_font(name, bold, italic):
    key = (str(name).lower(), bool(bold), bool(italic))
    if key in _font_cache:
        return _font_cache[key]
    fname = FONT_FILES.get(key)
    if fname is None:
        fname = FONT_FILES.get((key[0], False, False)) or FONT_FILES.get(("arial", bool(bold), bool(italic))) or "arial.ttf"
    alias = "%s%s%s" % (key[0].replace(" ", ""), "-bd" if bold else "", "-it" if italic else "")
    if alias not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(alias, os.path.join(FONT_DIR, fname)))
    _font_cache[key] = alias
    return alias


def fnum(s, default=0.0):
    if s is None:
        return default
    return float(str(s).replace(",", "."))


def parse_zsc(path):
    data = open(path, encoding="utf-8", errors="replace").read()
    data = re.sub(r"<\?xml[^>]*\?>\s*", "", data)
    return ET.fromstring(data)


class Report:
    """Model of one prepared .ZSC report."""

    def __init__(self, path):
        root = parse_zsc(path)
        self.previewpages = root.find("previewpages")
        self.cache = []
        pc = root.find("picturecache")
        if pc is not None:
            for item in pc.iter("item"):
                self.cache.append(bytes.fromhex(item.get("stream")))
        self.dic = {}
        dic = root.find("dictionary")
        if dic is not None:
            for ch in dic:
                nm = ch.get("name")
                if nm:
                    self.dic[ch.tag] = nm
        # Template: <report><TfrxReport/> + <sourcepages><TfrxReportPage/>...
        self.page_objs = []
        self.sourcepages = list(root.findall("sourcepages/TfrxReportPage")) or [
            p for p in root.iter("TfrxReportPage")
        ]
        for pg in self.sourcepages:
            objs = {}
            for el in pg.iter():
                nm = el.get("Name")
                if nm:
                    objs.setdefault(nm, el)
            self.page_objs.append(objs)
        sp0 = self.sourcepages[0] if self.sourcepages else None
        self.paper_w_mm = fnum(sp0.get("PaperWidth"), 210) if sp0 is not None else 210
        self.paper_h_mm = fnum(sp0.get("PaperHeight"), 297) if sp0 is not None else 297
        self.m_left_mm = fnum(sp0.get("LeftMargin"), 15.875) if sp0 is not None else 15.875
        self.m_top_mm = fnum(sp0.get("TopMargin"), 6.00075) if sp0 is not None else 6.00075

    def delement(self, short):
        """Resolve a short preview key (e.g. 'm3', 'b7') to its template element."""
        nm = self.dic.get(short)
        if not nm:
            return None
        parts = nm.split(".", 1)
        if len(parts) == 2 and parts[0].lower().startswith("page"):
            try:
                idx = int(parts[0][4:])
            except ValueError:
                return self.page_objs[0].get(parts[1]) if self.page_objs else None
            if idx < len(self.page_objs):
                return self.page_objs[idx].get(parts[1])
        for objs in self.page_objs:
            if nm in objs:
                return objs[nm]
        return None


class PageRenderer:
    def __init__(self, rep, cv, page_w_pt, page_h_pt):
        self.rep = rep
        self.cv = cv
        self.page_w_pt, self.page_h_pt = page_w_pt, page_h_pt
        self.ml_pt = rep.m_left_mm / 25.4 * 72
        self.mt_pt = rep.m_top_mm / 25.4 * 72

    # ---------------- font ----------------
    def font_of(self, el, de):
        """(font_alias, size_pt, bold, italic, underline)."""
        fname, st_size, st_bold = None, None, False
        if de is not None:
            fname = de.get("Font.Name")
            if de.get("Font.Style") is not None:
                st = int(fnum(de.get("Font.Style"), "0"))
                st_bold, italic = bool(st & 1), bool(st & 2)
            else:
                italic = False
            underline = bool(st & 4) if de.get("Font.Style") is not None else False
        else:
            italic = underline = False
        bold = st_bold
        # preview-level font overrides
        if el.get("Font.Name") is not None:
            fname = el.get("Font.Name")
        if el.get("Font.Style") is not None:
            st = int(fnum(el.get("Font.Style"), "0"))
            bold, italic, underline = bool(st & 1), bool(st & 2), bool(st & 4)
        size = None
        if el.get("Font.Size") is not None:
            size = fnum(el.get("Font.Size"), 10)
        elif el.get("Font.Height") is not None:
            size = abs(fnum(el.get("Font.Height"), -16)) * PT_PER_PX
        elif de is not None and de.get("Font.Height") is not None:
            size = abs(fnum(de.get("Font.Height"), -16)) * PT_PER_PX
        if fname is None:
            fname = "Arial"  # FastReport default when ParentFont
        if size is None:
            size = 10.0  # FastReport default report font size
        return register_font(fname, bold, italic), size, bold, italic, underline

    def halign_of(self, de, el):
        v = el.get("HAlign") if el is not None else None
        if v is None and de is not None:
            v = de.get("HAlign")
        if v == "haCenter":
            return "CENTER"
        if v == "haRight":
            return "RIGHT"
        return "LEFT"

    # ---------------- geometry ----------------
    def object_geometry(self, el, de, band_w):
        """(x, y, w, h) px, band-relative. Preview overrides template."""
        if de is not None:
            tw = fnum(de.get("Width"), 100)
            th = fnum(de.get("Height"), 24)
            al = de.get("Align")
            if al == "baWidth":
                x, w = 0.0, band_w
            elif al == "baCenter":
                x, w = max((band_w - tw) / 2.0, 0.0), tw
            elif al == "baRight":
                x, w = band_w - tw, tw
            else:
                x, w = fnum(de.get("Left"), 0), tw
            y = fnum(de.get("Top"), 0)
            h = th
        else:
            x, y, w, h = 0.0, 0.0, 100.0, 24.0
        # preview overrides (both short-key and template-style attribute names)
        for pshort, plong in (("l", "Left"), ("t", "Top"), ("w", "Width"), ("h", "Height")):
            v = el.get(pshort)
            if v is None:
                v = el.get(plong)
            if v is not None:
                if pshort == "l":
                    x = fnum(v, x)
                elif pshort == "t":
                    y = fnum(v, y)
                elif pshort == "w":
                    w = fnum(v, w)
                else:
                    h = fnum(v, h)
        # Align semantics depend on the FINAL width (FastReport recalculates the
        # anchor when size changes at print time). Only when the preview does not
        # carry an explicit left position: baRight keeps right edge on band edge,
        # baCenter re-centers.
        has_preview_x = el.get("l") is not None or el.get("Left") is not None
        if de is not None and not has_preview_x:
            al = de.get("Align")
            if abs(w - tw) > 0.01:
                if al == "baRight":
                    x = band_w - w
                elif al == "baCenter":
                    x = max((band_w - w) / 2.0, 0.0)
        return x, y, w, h

    # ---------------- text ----------------
    def wrap_and_draw(self, txt, x_px, y_px, w_px, font, size, halign="LEFT",
                      underline=False, nowrap=False):
        gapx = 2.0  # FastReport default memo inner gap, px
        gapy_px = 1.0 * PT_PER_PX
        box_w = max(w_px - 2.0 * gapx, 8.0) * PT_PER_PX
        space_w = pdfmetrics.stringWidth(" ", font, size)
        asc = pdfmetrics.getAscent(font) / 1000.0 * size
        desc = abs(pdfmetrics.getDescent(font)) / 1000.0 * size
        line_h = asc + desc + gapy_px
        cv = self.cv
        cv.saveState()
        base_y0 = self.page_h_pt - self.mt_pt - px2pt(y_px) - asc
        # split in paragraphs; wrap + justify each
        li = 0
        cv.setFont(font, size)
        for para in txt.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            lines, cur, cur_w, last = [], [], 0.0, None
            if nowrap:
                words = [w for w in para.split(" ") if w]
                if words:
                    lines.append((words, sum(pdfmetrics.stringWidth(w, font, size) for w in words) + space_w * (len(words) - 1), None))
            else:
                for word in para.split(" "):
                    if not word:
                        continue
                    ww = pdfmetrics.stringWidth(word, font, size)
                    if cur and cur_w + space_w + ww > box_w + 0.01:
                        lines.append((cur, cur_w, last))
                        cur, cur_w = [], 0.0
                    cur.append(word)
                    cur_w += (space_w if cur_w else 0.0) + ww
                    last = ww
                if cur or not para:
                    if cur:
                        lines.append((cur, cur_w, last))
                    if not lines and not para:
                        continue
            n_lines = len(lines) or 1
            for pidx, (ln, lw, llast) in enumerate(lines):
                if not ln:
                    continue
                lx = self.ml_pt + x_px * PT_PER_PX + gapx * PT_PER_PX
                gaps = len(ln) - 1
                extra = 0.0
                if halign == "CENTER":
                    lx += (box_w - lw) / 2.0
                elif halign == "RIGHT":
                    lx += box_w - lw
                elif halign == "BLOCK" and gaps > 0 and pidx < n_lines - 1:
                    extra = (box_w - lw) / gaps
                y = base_y0 - li * line_h
                cur_x = lx
                for j, word in enumerate(ln):
                    cv.drawString(cur_x, y, word)
                    cur_x += pdfmetrics.stringWidth(word, font, size) + space_w + (
                        extra if j < len(ln) - 1 else 0.0
                    )
                if underline:
                    ux, ulw = lx, lw + extra
                    cv.setLineWidth(max(size * 0.06, 0.6))
                    cv.line(ux, y - max(size * 0.13, 1.2), ux + ulw, y - max(size * 0.13, 1.2))
                    cv.setLineWidth(1)
                li += 1
        cv.restoreState()

    # ---------------- rich (RTF) ----------------
    def strip_rtf(self, rtf):
        """Extract (text, size, align, fontname, bold) from simple RTF."""
        mfs = re.search(r"\\fs(\d+)", rtf)
        size = (int(mfs.group(1)) / 2.0) if mfs else 12.0
        align = "LEFT"
        if re.search(r"\\qc", rtf):
            align = "CENTER"
        elif re.search(r"\\qr", rtf):
            align = "RIGHT"
        bold = bool(re.search(r"\\b(?![a-zA-Z0-9])", rtf))
        fname = None
        mft = re.search(r"\{\\f0\s*((?:\\[a-z0-9]+)*)\s*([^;{}]+)\s*;", rtf)
        if mft:
            fname = mft.group(2).strip()
        text = _rtf_to_text(rtf).strip("\r\n").strip()
        return text, size, align, fname, bold

    # ---------------- drawing ----------------
    def draw_image(self, img, x_px, y_px, box_w, box_h, stretch=False):
        if box_w <= 0 or box_h <= 0:
            return
        bw, bh = box_w * PT_PER_PX, box_h * PT_PER_PX
        iw, ih = img.size
        if stretch:
            w, h = bw, bh
            x = self.ml_pt + x_px * PT_PER_PX
        else:
            scale = min(bw / iw, bh / ih)
            w, h = iw * scale, ih * scale
            x = self.ml_pt + x_px * PT_PER_PX + (bw - w) / 2.0
        y_pdf = self.page_h_pt - self.mt_pt - px2pt(y_px) - bh + (bh - h) / 2.0
        self.cv.drawImage(ImageReader(img), x, y_pdf, w, h)

    def draw_line(self, x_px, y_px, w_px, thickness=0.6):
        y_pdf = self.page_h_pt - self.mt_pt - px2pt(y_px)
        self.cv.setLineWidth(thickness)
        self.cv.line(self.ml_pt + x_px * PT_PER_PX, y_pdf,
                     self.ml_pt + (x_px + w_px) * PT_PER_PX, y_pdf)

    # ---------------- bands ----------------
    def render(self, page_prev):
        for el in page_prev:
            tag = el.tag
            if tag == "TfrxNullBand":
                continue
            if tag.startswith("b"):
                self.render_band(el)
            elif tag.startswith("m"):
                self.render_standalone(el)
            elif tag.startswith("p"):
                self.render_picture(el)
            elif tag.startswith("l"):
                self.render_line(el)
            elif tag.startswith("r"):
                self.render_rich(el)

    def render_band(self, band_prev):
        band_def = self.rep.delement(band_prev.tag)
        band_top = fnum(band_prev.get("t"), 0)
        band_left = fnum(band_prev.get("l"), 0)  # column offset (3-column layouts)
        band_w = fnum(band_def.get("Width"), 703.46) if band_def is not None else 703.46
        # Shift the whole band left when its content extends past the printable
        # right edge (helps templates whose objects are wider than a column).
        max_r = 0.0
        for ch in band_prev:
            if ch.tag == "TfrxNullBand":
                continue
            ge = self.object_geometry(ch, self.rep.delement(ch.tag), band_w)
            max_r = max(max_r, band_left + ge[0] + ge[2])
        if max_r > PRINTABLE_W + 0.5:
            band_left -= max_r - PRINTABLE_W
        for ch in band_prev:
            if ch.tag == "TfrxNullBand":
                continue
            if ch.tag.startswith("m"):
                self.render_memo(ch, band_def, band_top, band_left, band_w)
            elif ch.tag.startswith("p"):
                self.render_picture(ch, band_def, band_top, band_left, band_w)
            elif ch.tag.startswith("l"):
                self.render_line(ch, band_def, band_top, band_left, band_w)
            elif ch.tag.startswith("r"):
                self.render_rich(ch, band_def, band_top, band_left, band_w)

    def render_standalone(self, el):
        """Object at preview-page level (outside a band)."""
        self.render_memo(el, None, 0.0, 0.0, 703.46)

    def render_memo(self, el, band_def, band_top, band_left=0.0, band_w=703.46):
        name = self.rep.dic.get(el.tag)
        de = self.rep.delement(el.tag)
        x, y, w, h = self.object_geometry(el, de, band_w)
        u = el.get("u")
        if not u:
            return
        font, size, bold, italic, underline = self.font_of(el, de)
        nowrap = de is not None and de.get("AutoWidth") == "True"
        self.wrap_and_draw(u, band_left + x, band_top + y, w, font, size,
                           self.halign_of(de, el), underline, nowrap)

    def render_picture(self, el, band_def, band_top, band_left=0.0, band_w=703.46):
        de = self.rep.delement(el.tag)
        ii = int(fnum(el.get("ImageIndex"), "0"))
        if not (0 < ii <= len(self.rep.cache)):
            return
        x, y, w, h = self.object_geometry(el, de, band_w)
        al = (de.get("Align") if de is not None else None) or el.get("Align")
        blob = self.rep.cache[ii - 1]
        try:
            img = Image.open(io.BytesIO(blob))
        except Exception:
            return
        stretch = al == "baWidth" or (de is not None and de.get("Stretched") == "True")
        self.draw_image(img, band_left + x, band_top + y, w, h, stretch)

    def render_line(self, el, band_def, band_top, band_left=0.0, band_w=703.46):
        de = self.rep.delement(el.tag)
        x, y, w, h = self.object_geometry(el, de, band_w)
        self.draw_line(band_left + x, band_top + y, w)

    def render_rich(self, el, band_def, band_top, band_left=0.0, band_w=703.46):
        """TfrxRichView rendered as text: RTF lives in the template PropData (hex)."""
        de = self.rep.delement(el.tag)
        if de is None:
            return
        if not de.get("PropData") and not el.get("PropData"):
            return
        blob_hex = el.get("PropData") or de.get("PropData")
        blob = bytes.fromhex(blob_hex)
        idx = blob.find(b"{\\rtf")
        if idx < 0:
            return
        rtf = blob[idx:].decode("latin-1", errors="replace")
        text, size, align, fname, bold = self.strip_rtf(rtf)
        if not text.strip():
            return
        x, y, w, h = self.object_geometry(el, de, band_w)
        if fname:
            try:
                font = register_font(fname, bold, False)
            except Exception:
                font = register_font("Arial", bold, False)
        else:
            font = register_font("Arial", bold, False)
        self.wrap_and_draw(text, band_left + x, band_top + y, w, font, size, align,
                           bold and bool(re.search(r"\\ul", rtf)))


def convert(path, outpdf=None):
    rep = Report(path)
    if rep.previewpages is None:
        raise ValueError("previewpages ausente — arquivo não é laudo preparado do FastReport")
    if outpdf is None:
        outpdf = str(Path(path).with_suffix(".pdf"))
    page_w_pt = rep.paper_w_mm / 25.4 * 72
    page_h_pt = rep.paper_h_mm / 25.4 * 72
    cv = canvas.Canvas(outpdf, pagesize=(page_w_pt, page_h_pt))
    pages = list(rep.previewpages)
    for pe in pages:
        PageRenderer(rep, cv, page_w_pt, page_h_pt).render(pe)
        cv.showPage()
    if not pages:
        cv.showPage()
    cv.setAuthor("zsc_to_pdf (LaudoView format RE)")
    cv.setTitle(Path(path).stem)
    cv.save()
    return outpdf


def main():
    ap = argparse.ArgumentParser(description="Convert Zscan .ZSC to PDF")
    ap.add_argument("input", help=".ZSC file or folder")
    ap.add_argument("output", nargs="?", default=None, help="output .pdf file or folder")
    args = ap.parse_args()
    p = Path(args.input)
    if p.is_dir():
        out = Path(args.output) if args.output else None
        if out is not None:
            out.mkdir(parents=True, exist_ok=True)
        for f in sorted(set(p.glob("*.ZSC")) | set(p.glob("*.zsc"))):
            o = str(out / (f.stem + ".pdf")) if out else None
            try:
                got = convert(str(f), o)
                print("OK  %s -> %s" % (f.name, got))
            except Exception as e:
                print("FAIL %s -> %s" % (f.name, e))
        return
    print(convert(str(p), args.output))


if __name__ == "__main__":
    main()
