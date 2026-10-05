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
import argparse;
import copy;
import json;
import os;
import sys;
from pathlib import Path;

from rich.console import Group;
from rich.text import Text;
from sumtui import (
    Application, HBox, Key, KeyEvent, Label, Menu, MenuBar, MenuDesktop,
    MenuItem, MouseEvent, Separator, StatusBar, TextInput, VBox, Widget,
    ask_question, available_theme_names, choose_file, choose_list,
    read_entry, refresh_user_themes, show_message,
);

from .borders import border_names, glyphs;
from .engine import Book, Cell, SheetError, cellref, colname, transform_formula, display_value;
from .preview import make_pdf, make_png, open_file;
from .version import __version__;


HELP = [
    f"SES {__version__} - sumEditSpreadsheet",
    "F2/click formula: edit cell; typing replaces cell",
    "Ctrl+C/X/V copy/cut/paste   Ctrl+Z/Y undo/redo",
    "Ctrl+B bold   Ctrl+U underline   F5 goto   F6 next sheet",
    "Shift+arrows extends selection; mouse drag selects a rectangular range",
    "Click row/column header selects it; Shift extends; Ctrl adds disjoint selection",
    "View controls editing grid lines and row/column headings independently",
    "Style > Cell borders marks real document/table borders for preview/print",
    "File > Preview PDF/PNG builds the real output and opens it with the platform viewer",
];



def ensure_ses_extension(path):
    target=Path(path).expanduser();
    return target if target.suffix else target.with_suffix(".ses");

def preference_path():
    base=Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home()/".config")));
    return base/"sumtui"/"ses.json";


def load_preferences(path=None):
    target=Path(path) if path else preference_path();
    try:
        data=json.loads(target.read_text(encoding="utf-8"));
        if not isinstance(data,dict): return {};
        return {k:data[k] for k in ("theme","border","last_dir","show_gridlines","show_column_headers","show_row_headers","preview_gridlines","preview_column_headers","preview_row_headers") if k in data};
    except (FileNotFoundError,ValueError,OSError): return {};


def save_preferences(data,path=None):
    target=Path(path) if path else preference_path(); target.parent.mkdir(parents=True,exist_ok=True);
    tmp=target.with_suffix(target.suffix+".tmp");
    tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); os.replace(tmp,target);


def sample_book():
    book=Book();
    data={
        "A1":"'Code","B1":"'Item","C1":"'Price","D1":"'Stock",
        "A2":"'TEA","B2":"'Tea","C2":"120","D2":"8",
        "A3":"'COF","B3":"'Coffee","C3":"175","D3":"3",
        "A4":"'MIL","B4":"'Milk","C4":"95","D4":"15",
        "F1":"'Sale","G1":"'Code","H1":"'Qty","I1":"'Unit","J1":"'Total","K1":"'Status",
        "F2":"'1","G2":"'TEA","H2":"2","I2":"=VLOOKUP(G2;A2:C4;3;FALSE)","J2":"=H2*I2","K2":"=IF(J2>=250;\"BIG\";\"SMALL\")",
        "F3":"'2","G3":"'COF","H3":"1","I3":"=VLOOKUP(G3;A2:C4;3;FALSE)","J3":"=H3*I3","K3":"=IF(J3>=250;\"BIG\";\"SMALL\")",
        "F4":"'3","G4":"'MIL","H4":"4","I4":"=VLOOKUP(G4;A2:C4;3;FALSE)","J4":"=H4*I4","K4":"=IF(J4>=250;\"BIG\";\"SMALL\")",
        "F6":"'Sales total","J6":"=SUM(J2:J4)","F7":"'Big sales","J7":"=COUNTIF(K2:K4;\"BIG\")",
        "F8":"'Tea total","J8":"=SUMIF(G2:G4;\"TEA\";J2:J4)","F9":"'Low stock","J9":"=COUNTIF(D2:D4;\"<5\")",
    };
    for address,value in data.items(): book.put(address,value);
    book.style(["A1","B1","C1","D1","F1","G1","H1","I1","J1","K1"],"bold",True);
    book.style(["A1","B1","C1","D1"],"bg",4); book.style(["F1","G1","H1","I1","J1","K1"],"bg",1);
    book.style(["F6","F7","F8","F9","J6","J7","J8","J9"],"bold",True);
    book.style(["J6"],"bg",2); book.style(["J7"],"bg",3); book.style(["J8"],"bg",6); book.style(["J9"],"bg",4);
    book.style(["K2","K3"],"fg",4); book.style(["K4"],"fg",2); book.style(["K2","K3","K4"],"bold",True);
    book.border([f"{colname(c)}{r}" for r in range(1,5) for c in range(1,5)],"single",outline=False);
    book.border([f"{colname(c)}{r}" for r in range(1,5) for c in range(6,12)],"single",outline=False);
    book.border([f"{colname(c)}{r}" for r in range(6,10) for c in range(6,11)],"single",outline=True);
    return book;


class FormulaLabel(Widget):
    def __init__(self, host): super().__init__(); self.host=host;
    def preferred_width(self,height=None): return max(10,len(self.host.book.active)+10);
    def __rich_console__(self,console,options):
        yield Text(f"{self.host.book.active}  {self.host.addr()}: ",style=self.theme.style("input_border"));


class SpreadsheetGrid(Widget):
    focusable=True;
    ROWW=5;
    def __init__(self,host):
        super().__init__(); self.host=host; self.view_cols=1; self.view_rows=1; self.visible_cols=[]; self.visible_rows=[]; self.mouse_selecting=False;
    def _col_width(self,col): return self.host.book.column_width(col);
    def _row_height(self,row): return self.host.book.row_height(row);
    def _layout_map(self):
        h=self.layout_height or 20; w=self.layout_width or 80;
        roww=self.ROWW if self.host.show_row_headers else 0; y=1 if self.host.show_column_headers else 0;
        cols=[]; x=roww; col=self.host.scrollx;
        while x < w and len(cols)<256:
            cw=self._col_width(col);
            if x+cw>w and cols: break;
            cols.append((col,x,cw)); x+=cw + (1 if self.host.show_gridlines and x+cw<w else 0); col+=1;
        rows=[]; row=self.host.scrolly;
        if self.host.show_gridlines: y+=1;
        while y < h and len(rows)<8192:
            rh=self._row_height(row);
            if y+rh>h and rows: break;
            rows.append((row,y,rh)); y+=rh + (1 if self.host.show_gridlines and y+rh<h else 0); row+=1;
        self.visible_cols=cols or [(self.host.scrollx,roww,max(1,w-roww))]; self.visible_rows=rows or [(self.host.scrolly,y,max(1,h-y))];
        self.view_cols=len(self.visible_cols); self.view_rows=len(self.visible_rows);
    def _adjust(self):
        self._layout_map();
        if self.host.cx<self.host.scrollx: self.host.scrollx=self.host.cx;
        elif self.visible_cols and self.host.cx>self.visible_cols[-1][0]: self.host.scrollx=max(1,self.host.cx-max(0,len(self.visible_cols)-1));
        if self.host.cy<self.host.scrolly: self.host.scrolly=self.host.cy;
        elif self.visible_rows and self.host.cy>self.visible_rows[-1][0]: self.host.scrolly=max(1,self.host.cy-max(0,len(self.visible_rows)-1));
        self._layout_map();
    def _cell_style(self,cell,selected,current):
        style=self.theme.style("selection" if selected else "viewer");
        if cell.bold: style += " bold";
        if cell.underline: style += " underline";
        if current: style += " reverse";
        if cell.fg!=7 or cell.bg!=0:
            ansi=["black","red","green","yellow","blue","magenta","cyan","white"];
            style += f" {ansi[cell.fg%8]} on {ansi[cell.bg%8]}";
        return style;
    def _formatted(self,address,width,line_index=0):
        cell=self.host.book.get(address); value=self.host.book.evaluate(address);
        text=display_value(value,cell.picture);
        # Row height reserves real blank screen rows. For now content is on the first row.
        if line_index>0: text="";
        text=text[:width];
        if cell.align=="repeat" and text: text=(text*((width//len(text))+1))[:width];
        if cell.align=="center": return text.center(width);
        if cell.align=="right" or (cell.align=="general" and isinstance(value,(int,float))): return text.rjust(width);
        return text.ljust(width);
    def _coord_at(self,x,y):
        self._adjust();
        roww=self.ROWW if self.host.show_row_headers else 0;
        if self.host.show_column_headers and y==0:
            for col,cx,cw in self.visible_cols:
                if cx<=x<cx+cw: return ('col',col);
            return None;
        for row,ry,rh in self.visible_rows:
            if ry<=y<ry+rh:
                if self.host.show_row_headers and x<roww: return ('row',row);
                for col,cx,cw in self.visible_cols:
                    if cx<=x<cx+cw: return ('cell',col,row);
                return None;
        return None;
    def handle_event(self,event):
        if isinstance(event,MouseEvent):
            if event.button!="left": return False;
            hit=self._coord_at(event.x,event.y);
            if event.action=="press":
                if self._focus_manager is not None: self._focus_manager.set(self);
                if not hit: return True;
                if hit[0]=="col": self.host.select_header("col",hit[1],event.shift,event.ctrl); return True;
                if hit[0]=="row": self.host.select_header("row",hit[1],event.shift,event.ctrl); return True;
                self.mouse_selecting=True; self.host.select_cell(hit[1],hit[2],event.shift,event.ctrl); self.host.anchor=(hit[1],hit[2]); return True;
            if event.action in ("move","drag") and self.mouse_selecting:
                if hit and hit[0]=="cell": self.host.cx,self.host.cy=hit[1],hit[2]; self.host.mode="cell"; self.host.selection_changed();
                return True;
            if event.action=="release" and self.mouse_selecting:
                self.mouse_selecting=False; return True;
            return False;
        if not isinstance(event,KeyEvent): return False;
        if event.key in (Key.LEFT,Key.RIGHT,Key.UP,Key.DOWN):
            dx={Key.LEFT:-1,Key.RIGHT:1}.get(event.key,0); dy={Key.UP:-1,Key.DOWN:1}.get(event.key,0);
            self.host.move(dx,dy,event.shift); return True;
        if event.key==Key.PAGE_UP: self.host.move(0,-max(1,self.view_rows),event.shift); return True;
        if event.key==Key.PAGE_DOWN: self.host.move(0,max(1,self.view_rows),event.shift); return True;
        if event.key==Key.ENTER: self.host.start_edit(False); return True;
        if event.key==Key.F2: self.host.start_edit(False); return True;
        if event.text and not event.ctrl and not event.alt: self.host.start_edit(True,event.text); return True;
        return False;
    def __rich_console__(self,console,options):
        self.set_bounds(self.x,self.y,options.max_width,options.height or options.max_height or console.height); self._adjust();
        lines=[]; roww=self.ROWW if self.host.show_row_headers else 0;
        if self.host.show_column_headers:
            header=Text(" "*roww,style=self.theme.style("table_header"));
            for i,(col,_x,cw) in enumerate(self.visible_cols):
                header.append(f"{colname(col):^{cw}}",style=self.theme.style("table_header"));
                if self.host.show_gridlines and i<len(self.visible_cols)-1: header.append(" ",style=self.theme.style("border"));
            lines.append(header);
        border=glyphs(self.host.border if self.host.border!="none" else "single") if self.host.show_gridlines else None;
        def horizontal():
            line=(border.l if roww else "") if border else "";
            if roww: line=" "*roww;
            if border:
                line += border.x.join(border.h*cw for _c,_x,cw in self.visible_cols);
            return line;
        if border: lines.append(Text(horizontal(),style=self.theme.style("border")));
        for ri,(row,_ry,rh) in enumerate(self.visible_rows):
            for sub in range(rh):
                line=Text((f"{row:>{self.ROWW-1}} " if sub==0 else " "*self.ROWW) if self.host.show_row_headers else "",style=self.theme.style("table_header"));
                for ci,(col,_cx,cw) in enumerate(self.visible_cols):
                    address=f"{colname(col)}{row}"; cell=self.host.book.get(address); selected=self.host.contains(col,row); current=(col,row)==(self.host.cx,self.host.cy);
                    line.append(self._formatted(address,cw,sub),style=self._cell_style(cell,selected,current));
                    if border and ci<len(self.visible_cols)-1: line.append(border.v,style=self.theme.style("border"));
                lines.append(line);
            if border and ri<len(self.visible_rows)-1: lines.append(Text(horizontal(),style=self.theme.style("border")));
        yield Group(*lines);


class SESController:
    def __init__(self,book=None,filename=None,theme="DOS",border="single",preferences=None,show_gridlines=None,show_column_headers=None,show_row_headers=None):
        refresh_user_themes(); self.book=book or Book(); self.file=str(filename) if filename else None; self.preferences=preferences or {};
        self.cx=1; self.cy=1; self.scrollx=1; self.scrolly=1; self.anchor=None; self.extra=[]; self.mode="cell"; self.border=("single" if border=="none" else border);
        legacy_grid=(border!="none"); self.show_gridlines=self.preferences.get("show_gridlines",legacy_grid) if show_gridlines is None else bool(show_gridlines);
        self.show_column_headers=self.preferences.get("show_column_headers",True) if show_column_headers is None else bool(show_column_headers);
        self.show_row_headers=self.preferences.get("show_row_headers",True) if show_row_headers is None else bool(show_row_headers);
        self.preview_gridlines=bool(self.preferences.get("preview_gridlines",False));
        self.preview_column_headers=bool(self.preferences.get("preview_column_headers",False));
        self.preview_row_headers=bool(self.preferences.get("preview_row_headers",False));
        self.clipboard=None; self.message="READY"; self.theme_name=theme;
        self.app=Application("SES",theme=theme,capture_control_keys=True,mouse=True);
        self.formula=TextInput("",on_submit=self._formula_submit); self.formula_label=FormulaLabel(self); self.grid=SpreadsheetGrid(self); self.status=StatusBar();
        self.menu=self._menu(); self.root=MenuDesktop(self.menu,VBox(HBox(self.formula_label,self.formula,sizes=[None,None]),self.grid,self.status,sizes=[1,None,1]));
        self.app.set_root(self.root); self.app.focus.set(self.grid); self._install_bindings(); self.refresh_formula(); self.refresh_status();
    def addr(self): return f"{colname(self.cx)}{self.cy}";
    def rects(self):
        if self.anchor is None: base=(self.cx,self.cy,self.cx,self.cy);
        else:
            x,y=self.anchor;
            if self.mode=="row": base=(1,min(y,self.cy),256,max(y,self.cy));
            elif self.mode=="col": base=(min(x,self.cx),1,max(x,self.cx),8192);
            else: base=(min(x,self.cx),min(y,self.cy),max(x,self.cx),max(y,self.cy));
        return [*self.extra,base];
    def contains(self,x,y): return any(a<=x<=c and b<=y<=d for a,b,c,d in self.rects());
    def selected(self):
        out=[]; seen=set();
        for a,b,c,d in self.rects():
            if (c-a+1)*(d-b+1)>50000: raise SheetError("#RANGE!","Select fewer than 50,000 cells");
            for y in range(b,d+1):
                for x in range(a,c+1):
                    address=f"{colname(x)}{y}";
                    if address not in seen: seen.add(address); out.append(address);
        return out;
    def range_spec(self):
        a,b,c,d=self.rects()[-1]; return f"{colname(a)}{b}:{colname(c)}{d}";
    def select_cell(self,col,row,shift=False,ctrl=False):
        if ctrl: self.extra=self.rects(); self.anchor=None;
        elif not shift: self.extra=[]; self.anchor=None;
        if shift and self.anchor is None: self.anchor=(self.cx,self.cy);
        self.mode="cell"; self.cx=max(1,col); self.cy=max(1,row); self.selection_changed();
    def select_header(self,kind,value,shift=False,ctrl=False):
        if ctrl: self.extra=self.rects(); self.anchor=None;
        elif not shift: self.extra=[]; self.anchor=None;
        if shift and self.anchor is None: self.anchor=(self.cx,self.cy);
        self.mode=kind;
        if kind=="row": self.cy=max(1,value);
        else: self.cx=max(1,value);
        if self.anchor is None: self.anchor=(self.cx,self.cy);
        self.selection_changed();
    def move(self,dx,dy,extend=False):
        if extend and self.anchor is None: self.anchor=(self.cx,self.cy);
        if not extend: self.anchor=None; self.extra=[]; self.mode="cell";
        self.cx=max(1,self.cx+dx); self.cy=max(1,self.cy+dy); self.selection_changed();
    def selection_changed(self): self.refresh_formula(); self.refresh_status(); self.app.invalidate();
    def refresh_formula(self):
        raw=self.book.get(self.addr()).raw; self.formula.set(raw); self.formula.cursor=len(self.formula.value);
    def refresh_status(self):
        count=sum((c-a+1)*(d-b+1) for a,b,c,d in self.rects()); self.status.set(f"{self.book.active} | {self.addr()} | {count} selected | {self.message}");
    def note(self,text): self.message=str(text); self.refresh_status(); self.app.invalidate(); return True;
    def start_edit(self,replace=False,initial=""):
        value=initial if replace else self.book.get(self.addr()).raw; self.formula.set(value); self.formula.cursor=len(value); self.app.focus.set(self.formula); self.note("EDIT: Enter confirms / Esc cancels"); return True;
    def _formula_submit(self,value):
        try: self.book.put(self.addr(),value); self.note("Cell updated");
        except SheetError as exc: self.note(str(exc)); return True;
        self.app.focus.set(self.grid); self.refresh_formula(); return True;
    def cancel_edit(self): self.refresh_formula(); self.app.focus.set(self.grid); self.note("Edit cancelled"); return True;
    def _menu(self):
        colors=["Black","Red","Green","Yellow","Blue","Magenta","Cyan","White"];
        def color_menu(attr): return Menu(attr.title(),[MenuItem(name,lambda n=i,a=attr:self.set_color(a,n)) for i,name in enumerate(colors)]);
        grid_style=Menu("Grid style",[MenuItem(name.title(),lambda n=name:self.set_border(n),radio=lambda n=name:self.border==n) for name in ("single","thick")]);
        cell_borders=Menu("Cell borders",[
            MenuItem("Clear",lambda:self.set_cell_border("none",False)),Separator(),
            MenuItem("Outline single",lambda:self.set_cell_border("single",True)),
            MenuItem("All single",lambda:self.set_cell_border("single",False)),
            MenuItem("Outline thick",lambda:self.set_cell_border("thick",True)),
            MenuItem("All thick",lambda:self.set_cell_border("thick",False)),
        ]);
        style_menu=Menu("Style",[
            MenuItem("Bold",self.toggle_bold,"Ctrl+B"),MenuItem("Underline",self.toggle_underline,"Ctrl+U"),Separator(),
            MenuItem("Foreground",submenu=color_menu("fg")),MenuItem("Background",submenu=color_menu("bg")),
            MenuItem("Cell borders",submenu=cell_borders),MenuItem("PICTURE",self.set_picture),Separator(),
            MenuItem("Column width",self.set_column_width),MenuItem("Row height",self.set_row_height),Separator(),
            MenuItem("Align left",lambda:self.align("left")),MenuItem("Align center",lambda:self.align("center")),MenuItem("Align right",lambda:self.align("right")),
        ]);
        view_menu=Menu("View",[
            MenuItem("Grid lines",self.toggle_gridlines,checked=lambda:self.show_gridlines),
            MenuItem("Column headers",self.toggle_column_headers,checked=lambda:self.show_column_headers),
            MenuItem("Row headers",self.toggle_row_headers,checked=lambda:self.show_row_headers),
            MenuItem("Grid style",submenu=grid_style),
        ]);
        preview_options=Menu("Preview options",[
            MenuItem("Grid lines",lambda:self.toggle_preview("gridlines"),checked=lambda:self.preview_gridlines),
            MenuItem("Column headers",lambda:self.toggle_preview("column_headers"),checked=lambda:self.preview_column_headers),
            MenuItem("Row headers",lambda:self.toggle_preview("row_headers"),checked=lambda:self.preview_row_headers),
        ]);
        return MenuBar([
            Menu("File",[MenuItem("New",self.new),MenuItem("Open",self.open_dialog),MenuItem("Save",self.save,"Ctrl+S"),MenuItem("Save as",self.save_as),Separator(),MenuItem("Preview PDF",self.preview_pdf),MenuItem("Preview PNG",self.preview_png),MenuItem("Preview options",submenu=preview_options),Separator(),MenuItem("Add sheet",self.add_sheet),MenuItem("Quit",self.quit)]),
            Menu("Edit",[MenuItem("Undo",self.undo,"Ctrl+Z"),MenuItem("Redo",self.redo,"Ctrl+Y"),Separator(),MenuItem("Copy",self.copy,"Ctrl+C"),MenuItem("Cut",self.cut,"Ctrl+X"),MenuItem("Paste",self.paste,"Ctrl+V"),Separator(),MenuItem("Fill down",lambda:self.fill("down")),MenuItem("Fill right",lambda:self.fill("right")),Separator(),MenuItem("Insert row",self.insert_row),MenuItem("Insert column",self.insert_col)]),
            style_menu,view_menu,
            Menu("Data",[MenuItem("Recalculate",self.recalculate,"F9"),MenuItem("Go to cell",self.goto,"F5")]),
            Menu("Tools",[MenuItem("Theme",self.choose_theme)]),
            Menu("Help",[MenuItem("Keys",self.help),MenuItem("About",self.about)]),
        ],on_close=lambda:self.app.focus.set(self.grid));
    def _install_bindings(self):
        bindings={"f1":self.help,"f2":lambda:self.start_edit(False),"f5":self.goto,"f6":self.next_sheet,"f9":self.recalculate,"f10":self.open_menu,
                  "ctrl+z":self.undo,"ctrl+y":self.redo,"ctrl+c":self.copy,"ctrl+x":self.cut,"ctrl+v":self.paste,"ctrl+b":self.toggle_bold,"ctrl+u":self.toggle_underline,"ctrl+s":self.save,"escape":self.cancel_edit};
        for key,callback in bindings.items(): self.app.bind(key,callback);
    def open_menu(self): self.menu.open(); self.app.focus.set(self.menu); self.app.invalidate(); return True;
    def _external(self,callback): return self.app.run_external(callback);
    def persist(self):
        try: save_preferences({"theme":self.theme_name,"border":self.border,"show_gridlines":self.show_gridlines,"show_column_headers":self.show_column_headers,"show_row_headers":self.show_row_headers,"preview_gridlines":self.preview_gridlines,"preview_column_headers":self.preview_column_headers,"preview_row_headers":self.preview_row_headers,"last_dir":str(Path(self.file).expanduser().resolve().parent) if self.file else self.preferences.get("last_dir",str(Path.cwd()))});
        except OSError as exc: self.note(f"Preferences not saved: {exc}");
    def new(self): self.book=Book(); self.file=None; self.selection_changed(); self.note("New workbook"); return True;
    def open_dialog(self):
        start=self.preferences.get("last_dir",str(Path.cwd())); result=self._external(lambda:choose_file(path=start,title="Open SES",theme=self.theme_name));
        if not result.accepted: return True;
        try: self.book=Book.load(Path(result.value)); self.file=str(result.value); self.cx=self.cy=1; self.persist(); self.selection_changed(); self.note(f"Opened {self.file}");
        except Exception as exc: self.note(f"ERROR {exc}");
        return True;
    def save(self):
        if not self.file: return self.save_as();
        try: self.book.save(self.file); self.persist(); self.note(f"Saved {self.file}");
        except OSError as exc: self.note(f"ERROR {exc}");
        return True;
    def save_as(self):
        default=self.file or str(Path(self.preferences.get("last_dir",str(Path.cwd())))/"workbook.ses");
        result=self._external(lambda:read_entry(text="File name or full path",default=default,title="Save SES as",theme=self.theme_name));
        if not result.accepted or not result.value: return True;
        target=ensure_ses_extension(result.value);
        if target.exists():
            answer=self._external(lambda:ask_question(f"Overwrite {target.name}?",theme=self.theme_name));
            if not answer.accepted: return True;
        self.file=str(target); return self.save();
    def add_sheet(self):
        result=self._external(lambda:read_entry(text="Sheet name",title="Add sheet",theme=self.theme_name));
        if result.accepted and result.value:
            try: self.book.add_sheet(result.value); self.note("Sheet added");
            except Exception as exc: self.note(f"ERROR {exc}");
        return True;
    def quit(self): self.persist(); self.app.stop(); return True;
    def undo(self): self.book.undo(); self.refresh_formula(); self.note("Undo"); return True;
    def redo(self): self.book.redo(); self.refresh_formula(); self.note("Redo"); return True;
    def _copy_snapshot(self,cut=False):
        rects=self.rects();
        if len(rects)!=1: raise SheetError("#RANGE!","Copy one rectangular selection at a time");
        a,b,c,d=rects[0];
        if (c-a+1)*(d-b+1)>50000: raise SheetError("#RANGE!");
        data={(x-a,y-b):copy.deepcopy(self.book.get(f"{colname(x)}{y}")) for y in range(b,d+1) for x in range(a,c+1)};
        self.clipboard=(a,b,c,d,data,cut); self.note(("Cut" if cut else "Copied")+f" {colname(a)}{b}:{colname(c)}{d}"); return True;
    def copy(self):
        try: return self._copy_snapshot(False);
        except SheetError as exc: return self.note(str(exc));
    def cut(self):
        try: return self._copy_snapshot(True);
        except SheetError as exc: return self.note(str(exc));
    def paste(self):
        if not self.clipboard: return self.note("Clipboard empty");
        sx,sy,ex,ey,data,cut=self.clipboard; dx,dy=self.cx,self.cy;
        def apply():
            cells=self.book.sheets[self.book.active].cells;
            if cut:
                for y in range(sy,ey+1):
                    for x in range(sx,ex+1): cells.pop(f"{colname(x)}{y}",None);
            for (ox,oy),cell in data.items():
                target=copy.deepcopy(cell);
                if not cut and target.raw.startswith(("=","+","@")): target.raw=transform_formula(target.raw,dx-sx,dy-sy);
                cells[f"{colname(dx+ox)}{dy+oy}"]=target;
        self.book.change(apply); self.book.dirty=True;
        if cut: self.clipboard=None;
        return self.note("Pasted");
    def fill(self,direction):
        try: self.book.fill(self.range_spec(),direction); return self.note(f"Fill {direction}");
        except SheetError as exc: return self.note(str(exc));
    def insert_row(self): self.book.insert("row",self.cy); self.refresh_formula(); return self.note("Row inserted");
    def insert_col(self): self.book.insert("col",self.cx); self.refresh_formula(); return self.note("Column inserted");
    def toggle_bold(self):
        try: self.book.toggle_bold(self.selected()); return self.note("Bold toggled");
        except SheetError as exc: return self.note(str(exc));
    def toggle_underline(self):
        try: self.book.style(self.selected(),"underline"); return self.note("Underline toggled");
        except SheetError as exc: return self.note(str(exc));
    def set_color(self,attr,value):
        try: self.book.style(self.selected(),attr,value); return self.note(f"{attr.upper()}={value}");
        except SheetError as exc: return self.note(str(exc));
    def align(self,value):
        try: self.book.style(self.selected(),"align",value); return self.note("Alignment changed");
        except SheetError as exc: return self.note(str(exc));
    def set_column_width(self):
        result=self._external(lambda:read_entry(text="Width in characters",default=str(self.book.column_width(self.cx)),title="Column width",theme=self.theme_name));
        if result.accepted and result.value:
            try:
                cols=set();
                for a,_b,c,_d in self.rects(): cols.update(range(a,c+1));
                self.book.set_column_width(cols,int(result.value)); self.note(f"Column width {int(result.value)}");
            except (ValueError,SheetError) as exc: self.note(f"ERROR {exc}");
        return True;
    def set_row_height(self):
        result=self._external(lambda:read_entry(text="Height in terminal rows",default=str(self.book.row_height(self.cy)),title="Row height",theme=self.theme_name));
        if result.accepted and result.value:
            try:
                rows=set();
                for _a,b,_c,d in self.rects(): rows.update(range(b,d+1));
                self.book.set_row_height(rows,int(result.value)); self.note(f"Row height {int(result.value)}");
            except (ValueError,SheetError) as exc: self.note(f"ERROR {exc}");
        return True;
    def set_picture(self):
        current=self.book.get(self.addr()).picture;
        result=self._external(lambda:read_entry(text="PICTURE (0 required digit, # optional digit)",default=current,title="Cell PICTURE",theme=self.theme_name));
        if result.accepted:
            try: self.book.set_picture(self.selected(),result.value); self.note("PICTURE updated");
            except SheetError as exc: self.note(f"ERROR {exc}");
        return True;
    def set_border(self,name):
        self.border="single" if name=="none" else name; self.show_gridlines=(name!="none"); self.persist(); return self.note(f"Grid style: {self.border}");
    def toggle_gridlines(self): self.show_gridlines=not self.show_gridlines; self.persist(); return self.note("Grid lines "+("on" if self.show_gridlines else "off"));
    def toggle_column_headers(self): self.show_column_headers=not self.show_column_headers; self.persist(); return self.note("Column headers "+("on" if self.show_column_headers else "off"));
    def toggle_row_headers(self): self.show_row_headers=not self.show_row_headers; self.persist(); return self.note("Row headers "+("on" if self.show_row_headers else "off"));
    def toggle_preview(self,what):
        attr="preview_"+what; setattr(self,attr,not getattr(self,attr)); self.persist(); return self.note("Preview "+what.replace("_"," ")+" "+("on" if getattr(self,attr) else "off"));
    def set_cell_border(self,style,outline=False):
        try: self.book.border(self.selected(),style,outline=outline); return self.note(("Outline " if outline else "Cell borders ")+style);
        except SheetError as exc: return self.note(str(exc));
    def recalculate(self): self.book.dirty=True; self.note("Recalculated"); return True;
    def goto(self):
        result=self._external(lambda:read_entry(text="Cell",default=self.addr(),title="Go to",theme=self.theme_name));
        if result.accepted:
            try: self.cx,self.cy,*_=cellref(result.value); self.anchor=None; self.extra=[]; self.mode="cell"; self.selection_changed();
            except Exception as exc: self.note(f"ERROR {exc}");
        return True;
    def next_sheet(self):
        names=list(self.book.sheets); self.book.active=names[(names.index(self.book.active)+1)%len(names)]; self.book.dirty=True; self.selection_changed(); return True;
    def choose_theme(self):
        result=self._external(lambda:choose_list(available_theme_names(),title="SES theme",theme=self.theme_name));
        if result.accepted:
            self.theme_name=str(result.value); self.app.set_theme(self.theme_name); self.persist(); self.note("Theme "+self.theme_name);
        return True;
    def _preview(self,kind):
        try:
            maker=make_pdf if kind=="PDF" else make_png;
            path=maker(self.book,gridlines=self.preview_gridlines,column_headers=self.preview_column_headers,row_headers=self.preview_row_headers);
            self._external(lambda:open_file(path)); return self.note(f"Preview {kind}: {path}");
        except Exception as exc: return self.note(f"Preview {kind} error: {exc}");
    def preview_pdf(self): return self._preview("PDF");
    def preview_png(self): return self._preview("PNG");
    def preview(self): return self.preview_pdf();
    def help(self): self._external(lambda:show_message("\n".join(HELP),title="SES keys",theme=self.theme_name)); return True;
    def about(self): self._external(lambda:show_message(f"SES {__version__} - alpha\nGNU GPL-3.0-or-later",title="About SES",theme=self.theme_name)); return True;
    def run(self):
        try: return self.app.run();
        finally: self.persist();


def argument_parser():
    parser=argparse.ArgumentParser(prog="ses",description="SES - sumEditSpreadsheet");
    parser.add_argument("file",nargs="?",help="existing .ses workbook to open");
    parser.add_argument("--theme",help="sumTUI theme"); parser.add_argument("--list-themes",action="store_true"); parser.add_argument("--demo",action="store_true");
    parser.add_argument("--border",choices=border_names(),help="cell/grid border style"); parser.add_argument("--grid",action="store_true",help="alias for --border single"); parser.add_argument("--no-grid",action="store_true",help="alias for --border none");
    parser.add_argument("--version",action="version",version=f"SES {__version__}"); return parser;


def main(argv=None):
    parser=argument_parser(); args=parser.parse_args(argv); refresh_user_themes();
    if args.list_themes: print("\n".join(available_theme_names())); return 0;
    if args.demo and args.file: parser.error("choose either FILE or --demo");
    pref=load_preferences(); theme=args.theme or pref.get("theme","DOS");
    if theme.casefold() not in [name.casefold() for name in available_theme_names(include_hidden=True)]: parser.error("Unknown theme: "+theme);
    border=args.border or ("single" if args.grid else ("none" if args.no_grid else pref.get("border","single")));
    show_gridlines=True if (args.grid or (args.border and args.border!="none")) else (False if (args.no_grid or args.border=="none") else pref.get("show_gridlines",False));
    try: book=Book.load(Path(args.file).expanduser()) if args.file else (sample_book() if args.demo else Book());
    except Exception as exc: parser.exit(2,f"ses: cannot open {args.file}: {exc}\n");
    if not sys.stdin.isatty() or not sys.stdout.isatty(): parser.exit(2,"ses: interactive terminal required\n");
    return SESController(book=book,filename=args.file,theme=theme,border=border,preferences=pref,show_gridlines=show_gridlines).run();


if __name__=="__main__": raise SystemExit(main());
