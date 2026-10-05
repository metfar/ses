#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#pylint:disable=W0301
#  
#  Copyright 2018- William Martinez Bas <metfar@gmail.com>
#  
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#  
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#  
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#  
#
#import warnings;
#warnings.filterwarnings("ignore", category=UserWarning);
import html;
import os;
import platform;
import subprocess;
import tempfile;
from pathlib import Path;

from .engine import cellref, colname, display_value;


DOS_COLORS={
    0:"#000000", 1:"#aa0000", 2:"#00aa00", 3:"#aa5500",
    4:"#0000aa", 5:"#aa00aa", 6:"#00aaaa", 7:"#aaaaaa",
};


def used_extent(book, sheet=None):
    sheet=sheet or book.active; cells=book.sheets[sheet].cells;
    if not cells: return 1,1;
    coords=[];
    for address in cells:
        try: coords.append(cellref(address)[:2]);
        except Exception: pass;
    return max((x for x,_ in coords),default=1),max((y for _,y in coords),default=1);


def _border_css(cell):
    weights={"none":"0","single":"0.35mm solid #555","thick":"0.7mm solid #222"};
    return [
        f"border-top:{weights.get(cell.border_top,'0')}",
        f"border-right:{weights.get(cell.border_right,'0')}",
        f"border-bottom:{weights.get(cell.border_bottom,'0')}",
        f"border-left:{weights.get(cell.border_left,'0')}",
    ];


def _font_size(book,cols):
    """Choose a printable monospace size that fits the used columns on A4 landscape."""
    total=sum(book.column_width(col) for col in range(1,cols+1));
    # Roughly 125-130 monospace characters fit comfortably at 10pt on A4 landscape.
    return max(5.5,min(10.0,10.0*126.0/max(1,total)));


def workbook_html(book,title="SES preview",*,gridlines=False,column_headers=False,row_headers=False):
    """Render the active sheet for printing.

    Editing aids are off by default. Explicit cell borders and explicit cell
    foreground/background colors are document formatting and are always emitted.
    Plain numbers use the same canonical display conversion as the TUI.
    """
    cols,rows=used_extent(book); grid_border="0.2mm solid #bbb" if gridlines else "0";
    widths=[book.column_width(col) for col in range(1,cols+1)]; total=max(1,sum(widths)); fontpt=_font_size(book,cols);
    lines=["<!doctype html><meta charset='utf-8'>",f"<title>{html.escape(title)}</title>",
           "<style>@page{size:A4 landscape;margin:10mm}html,body{margin:0;padding:0}"
           f"body{{font-family:monospace;font-size:{fontpt:.2f}pt;color:#000;background:#fff}}"
           "table{border-collapse:collapse;width:100%;table-layout:fixed;break-inside:auto}"
           "tr{break-inside:avoid}td,th{padding:1px 3px;white-space:pre;overflow:hidden;vertical-align:top}"
           f"td{{border:{grid_border}}}th{{border:{grid_border};background:#eee;color:#000}} .n{{text-align:right}}</style>",
           "<table><colgroup>"];
    if row_headers: lines.append("<col style='width:4%'>");
    usable=96.0 if row_headers else 100.0;
    for width in widths: lines.append(f"<col style='width:{usable*width/total:.6f}%'>");
    lines.append("</colgroup>");
    if column_headers:
        lines.append("<thead><tr>");
        if row_headers: lines.append("<th></th>");
        for col in range(1,cols+1): lines.append(f"<th>{colname(col)}</th>");
        lines.append("</tr></thead>");
    lines.append("<tbody>");
    for row in range(1,rows+1):
        lines.append(f"<tr style=\"height:{book.row_height(row)*1.35:.2f}em\">");
        if row_headers: lines.append(f"<th>{row}</th>");
        for col in range(1,cols+1):
            addr=f"{colname(col)}{row}"; cell=book.get(addr); value=book.evaluate(addr); text=display_value(value,cell.picture);
            cls=" class='n'" if isinstance(value,(int,float)) and not isinstance(value,bool) else "";
            style=_border_css(cell);
            if cell.bold: style.append("font-weight:bold");
            if cell.underline: style.append("text-decoration:underline");
            if cell.align in ("left","center","right"): style.append("text-align:"+cell.align);
            if cell.fg_explicit: style.append("color:"+DOS_COLORS.get(int(cell.fg),"#000000"));
            if cell.bg_explicit: style.append("background-color:"+DOS_COLORS.get(int(cell.bg),"#ffffff"));
            style_attr=(" style='"+";".join(style)+"'") if style else "";
            lines.append(f"<td{cls}{style_attr}>{html.escape(text)}</td>");
        lines.append("</tr>");
    lines.append("</tbody></table>");
    return "".join(lines);


def make_pdf(book,path=None,*,gridlines=False,column_headers=False,row_headers=False):
    try:
        from weasyprint import HTML;
    except ImportError as exc:
        raise RuntimeError("PDF preview requires WeasyPrint (available with sumdoc)") from exc;
    if path is None:
        fd,name=tempfile.mkstemp(prefix="ses-preview-",suffix=".pdf"); os.close(fd); path=name;
    target=Path(path);
    HTML(string=workbook_html(book,gridlines=gridlines,column_headers=column_headers,row_headers=row_headers)).write_pdf(str(target));
    return target;


def make_png(book,path=None,*,gridlines=False,column_headers=False,row_headers=False,scale=1.6):
    """Render all PDF preview pages to one vertically stacked PNG."""
    try:
        import pypdfium2 as pdfium;
        from PIL import Image;
    except ImportError as exc:
        raise RuntimeError("PNG preview requires pypdfium2 and Pillow") from exc;
    if path is None:
        fd,name=tempfile.mkstemp(prefix="ses-preview-",suffix=".png"); os.close(fd); path=name;
    target=Path(path);
    fd,tmp=tempfile.mkstemp(prefix="ses-preview-render-",suffix=".pdf"); os.close(fd);
    try:
        make_pdf(book,tmp,gridlines=gridlines,column_headers=column_headers,row_headers=row_headers);
        pdf=pdfium.PdfDocument(tmp); pages=[];
        for page in pdf:
            bitmap=page.render(scale=float(scale)); pages.append(bitmap.to_pil().convert("RGB"));
        if not pages: raise RuntimeError("Preview produced no pages");
        gap=12 if len(pages)>1 else 0; width=max(im.width for im in pages); height=sum(im.height for im in pages)+gap*(len(pages)-1);
        canvas=Image.new("RGB",(width,height),"white"); y=0;
        for im in pages:
            canvas.paste(im,(0,y)); y+=im.height+gap;
        canvas.save(target,"PNG");
    finally:
        try: os.unlink(tmp);
        except OSError: pass;
    return target;


def open_file(path):
    target=str(Path(path).resolve()); system=platform.system().lower();
    if system=="windows": os.startfile(target);  # pylint:disable=no-member
    elif system=="darwin": subprocess.Popen(["open",target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);
    else: subprocess.Popen(["xdg-open",target],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);
    return target;
