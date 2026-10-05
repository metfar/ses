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

from .engine import colname, format_picture;


def used_extent(book, sheet=None):
    sheet = sheet or book.active;
    cells = book.sheets[sheet].cells;
    if not cells: return 1, 1;
    coords=[];
    from .engine import cellref;
    for address in cells:
        try: coords.append(cellref(address)[:2]);
        except Exception: pass;
    return (max((x for x,_ in coords), default=1), max((y for _,y in coords), default=1));


def _border_css(cell):
    weights={"none":"0","single":"1px solid #555","thick":"2px solid #222"};
    return [
        f"border-top:{weights.get(cell.border_top,'0')}",
        f"border-right:{weights.get(cell.border_right,'0')}",
        f"border-bottom:{weights.get(cell.border_bottom,'0')}",
        f"border-left:{weights.get(cell.border_left,'0')}",
    ];


def workbook_html(book, title="SES preview", *, gridlines=False, column_headers=False, row_headers=False):
    """Render the active sheet for printing.

    Editing aids are off by default. Explicit cell borders are document
    formatting and are always emitted independently from gridlines.
    """
    cols, rows = used_extent(book);
    grid_border="1px solid #bbb" if gridlines else "0";
    lines=["<!doctype html><meta charset='utf-8'>", f"<title>{html.escape(title)}</title>",
           "<style>@page{size:A4 landscape;margin:12mm}body{font-family:monospace;font-size:10pt}"
           "table{border-collapse:collapse}td,th{padding:2px 6px;white-space:pre}"
           f"td{{border:{grid_border}}}th{{border:{grid_border};background:#eee}} .n{{text-align:right}}</style>",
           "<table>"];
    if column_headers:
        lines.append("<thead><tr>");
        if row_headers: lines.append("<th></th>");
        for col in range(1,cols+1): lines.append(f"<th>{colname(col)}</th>");
        lines.append("</tr></thead>");
    lines.append("<tbody>");
    for row in range(1,rows+1):
        lines.append(f"<tr style=\"height:{book.row_height(row)*1.4:.1f}em\">");
        if row_headers: lines.append(f"<th>{row}</th>");
        for col in range(1,cols+1):
            addr=f"{colname(col)}{row}"; cell=book.get(addr); value=book.evaluate(addr);
            shown=format_picture(value,cell.picture); text="" if shown is None else str(shown);
            cls=" class='n'" if isinstance(value,(int,float)) else "";
            style=_border_css(cell); style.append(f"min-width:{book.column_width(col)}ch");
            if cell.bold: style.append("font-weight:bold");
            if cell.underline: style.append("text-decoration:underline");
            if cell.align in ("left","center","right"): style.append("text-align:"+cell.align);
            style_attr=(" style='"+";".join(style)+"'") if style else "";
            lines.append(f"<td{cls}{style_attr}>{html.escape(text)}</td>");
        lines.append("</tr>");
    lines.append("</tbody></table>");
    return "".join(lines);


def make_pdf(book, path=None, *, gridlines=False, column_headers=False, row_headers=False):
    try:
        from weasyprint import HTML;
    except ImportError as exc:
        raise RuntimeError("PDF preview requires WeasyPrint (available with sumdoc)") from exc;
    if path is None:
        fd, name = tempfile.mkstemp(prefix="ses-preview-", suffix=".pdf"); os.close(fd); path=name;
    target=Path(path);
    HTML(string=workbook_html(book,gridlines=gridlines,column_headers=column_headers,row_headers=row_headers)).write_pdf(str(target));
    return target;


def open_file(path):
    target=str(Path(path).resolve()); system=platform.system().lower();
    if system == "windows":
        os.startfile(target);  # pylint:disable=no-member
    elif system == "darwin":
        subprocess.Popen(["open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL);
    else:
        subprocess.Popen(["xdg-open", target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL);
    return target;
