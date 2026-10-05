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
"""SES's initial terminal front-end using the existing sumTUI API."""
import argparse;
import sys;
from rich.console import Group;
from rich.text import Text;
from sumtui import Application, Menu, MenuBar, MenuDesktop, MenuItem, Key, MouseEvent, Widget;
from .engine import Workbook, FormulaError, colname, split_cell;

HELP = (
    "F1 help  F2 edit  Enter commit  Esc cancel  F5 go to  F6 next sheet  F9 recalc  "
    "F10 menu  Shift+arrows range  Ctrl+C copy  Ctrl+V paste  Ctrl+B bold  Ctrl+Z/Y undo/redo  "
    "Ctrl+S save  Ctrl+O open  Ctrl+Q quit"
);

class SheetView(Widget):
    focusable = True;

    def __init__(self, book):
        super().__init__();
        self.book = book;
        self.col = 1;
        self.row = 1;
        self.anchor = (1, 1);
        self.first_col = 1;
        self.first_row = 1;
        self.width = 80;
        self.height = 24;
        self.cell_width = 12;
        self.editing = None;
        self.editor_cursor = 0;
        self.ask = "";
        self.ask_text = "";
        self.message = "READY";
        self.copy_block = None;
        self.help_visible = False;
        self.exit_callback = None;

    @property
    def address(self):
        return colname(self.col) + str(self.row);

    def selected(self):
        a, b = self.anchor;
        return [colname(c) + str(r) for r in range(min(b,self.row), max(b,self.row)+1)
                for c in range(min(a,self.col), max(a,self.col)+1)];

    def move(self, dc, dr, extend=False):
        if not extend: self.anchor = (max(1, self.col+dc), max(1, self.row+dr));
        self.col = max(1, min(16384, self.col+dc));
        self.row = max(1, min(100000, self.row+dr));
        if extend: self.message = "Selected: " + self.selected()[0] + ":" + self.selected()[-1];
        else: self.message = self.book.details.get((self.book.sheet,self.address), "READY");
        return True;

    def start_edit(self, replace=None):
        self.editing = self.book.cell(self.address).raw if replace is None else replace;
        self.editor_cursor = len(self.editing);
        self.message = "EDIT: Enter confirms / Esc cancels";
        return True;

    def start_prompt(self, kind, default=""):
        self.ask = kind;
        self.ask_text = default;
        self.message = "Input " + kind + ": Enter confirms / Esc cancels";
        return True;

    def commit(self):
        if self.ask:
            kind, content = self.ask, self.ask_text.strip();
            self.ask = "";
            self.ask_text = "";
            try:
                if kind == "Go to":
                    c, r, _, _ = split_cell(content);
                    self.col, self.row = c, r;
                    self.anchor = (c, r);
                elif kind == "Save as":
                    if not content: return True;
                    self.book.save(content);
                    self.message = "Saved: " + content;
                elif kind == "Open":
                    if not content: return True;
                    newer = Workbook.load(content);
                    self.book = newer;
                    self.col = 1; self.row = 1;
                    self.anchor = (1, 1);
                    self.message = "Opened: " + content;
                elif kind == "New sheet":
                    self.book.add_sheet(content);
                    self.book.sheet = content;
                    self.col = 1; self.row = 1; self.anchor = (1,1);
                    self.message = "New sheet: " + content;
            except (FormulaError, ValueError, OSError) as exc:
                self.message = "ERROR: " + str(exc);
            return True;
        if self.editing is not None:
            content = self.editing;
            self.editing = None;
            self.book.set(self.address, content);
            self.message = "Updated " + self.address;
            self.move(0, 1);
            return True;
        return False;

    def undo(self):
        self.message = "Undo" if self.book.undo() else "Nothing to undo";
        return True;

    def redo(self):
        self.message = "Redo" if self.book.redo() else "Nothing to redo";
        return True;

    def toggle_bold(self):
        cells = self.selected();
        self.book.set_bold(cells);
        self.message = "Bold toggled: " + str(len(cells)) + " cells";
        return True;

    def copy(self):
        a, b = self.anchor;
        self.copy_block = (self.book.sheet, min(a,self.col), min(b,self.row),
                           abs(self.col-a)+1, abs(self.row-b)+1);
        self.message = "Copied selection. Choose destination and Ctrl+V.";
        return True;

    def paste(self):
        if self.copy_block is None:
            self.message = "Clipboard empty";
            return True;
        sheet, col, row, count_cols, count_rows = self.copy_block;
        if sheet != self.book.sheet:
            self.message = "Cross-sheet paste: not implemented yet";
            return True;
        self.book.copy(colname(col)+str(row), self.address, count_rows, count_cols);
        self.message = "Pasted " + str(count_rows*count_cols) + " cells";
        return True;

    def next_sheet(self):
        names = list(self.book.sheets);
        self.book.sheet = names[(names.index(self.book.sheet)+1) % len(names)];
        self.anchor = (1,1); self.row = 1; self.col = 1;
        self.message = "Sheet: " + self.book.sheet;
        return True;

    def _write_input(self, event):
        if event.key == Key.ESCAPE:
            self.editing = None; self.ask = ""; self.ask_text = "";
            self.message = "Cancelled";
            return True;
        if event.key == Key.ENTER:
            return self.commit();
        if event.key == Key.BACKSPACE:
            if self.ask:
                self.ask_text = self.ask_text[:-1];
            elif self.editor_cursor:
                self.editing = self.editing[:self.editor_cursor-1] + self.editing[self.editor_cursor:];
                self.editor_cursor -= 1;
            return True;
        if self.editing is not None:
            if event.key == Key.LEFT:
                self.editor_cursor = max(0, self.editor_cursor-1);
                return True;
            if event.key == Key.RIGHT:
                self.editor_cursor = min(len(self.editing), self.editor_cursor+1);
                return True;
            if event.key == Key.HOME:
                self.editor_cursor = 0; return True;
            if event.key == Key.END:
                self.editor_cursor = len(self.editing); return True;
            if event.key == Key.DELETE:
                self.editing = self.editing[:self.editor_cursor] + self.editing[self.editor_cursor+1:];
                return True;
            # Explicit reference-picking: Ctrl+arrows moves the sheet selection
            # while a formula is being edited, without disturbing text caret.
            if event.ctrl and event.key in (Key.UP, Key.DOWN, Key.LEFT, Key.RIGHT):
                dc, dr = {Key.UP:(0,-1), Key.DOWN:(0,1), Key.LEFT:(-1,0), Key.RIGHT:(1,0)}[event.key];
                self.move(dc,dr,extend=event.shift);
                return True;
            if event.key == Key.F4 and self.editing and self.editing[0] in "=+@":
                start = self.anchor;
                ref = self.address;
                if start != (self.col,self.row): ref = colname(start[0])+str(start[1])+":"+ref;
                self.editing = self.editing[:self.editor_cursor] + ref + self.editing[self.editor_cursor:];
                self.editor_cursor += len(ref);
                self.anchor = (self.col,self.row);
                return True;
        if event.text and not event.ctrl and not event.alt and event.text.isprintable():
            if self.ask:
                self.ask_text += event.text;
            else:
                self.editing = self.editing[:self.editor_cursor] + event.text + self.editing[self.editor_cursor:];
                self.editor_cursor += len(event.text);
            return True;
        return False;

    def handle_event(self, event):
        if isinstance(event, MouseEvent):
            if event.action not in ("press", "drag") or event.button not in ("left", "none"):
                return False;
            # MenuDesktop owns y=0; body y=0 is the formula bar.
            if event.y == 0:
                self.start_edit();
                return True;
            if event.y >= 2 and event.x >= 5:
                c = self.first_col + (event.x-5)//(self.cell_width+1);
                r = self.first_row + event.y-2;
                if c >= 1 and r >= 1:
                    if event.action != "drag" and not event.shift:
                        self.anchor = (c,r);
                    self.col, self.row = c, r;
                    return True;
            return False;
        if self.ask or self.editing is not None:
            return self._write_input(event);
        if event.matches("ctrl+z"): return self.undo();
        if event.matches("ctrl+y"): return self.redo();
        if event.matches("ctrl+b"): return self.toggle_bold();
        if event.matches("ctrl+c"): return self.copy();
        if event.matches("ctrl+v"): return self.paste();
        if event.matches("ctrl+s"):
            if self.book.filename:
                self.book.save(self.book.filename);
                self.message = "Saved";
                return True;
            return self.start_prompt("Save as", "workbook.ses");
        if event.matches("ctrl+o"): return self.start_prompt("Open");
        if event.matches("ctrl+q"):
            if self.exit_callback: self.exit_callback();
            return True;
        if event.key == Key.F1:
            self.help_visible = not self.help_visible;
            return True;
        if event.key == Key.F2: return self.start_edit();
        if event.key == Key.F5: return self.start_prompt("Go to", self.address);
        if event.key == Key.F6: return self.next_sheet();
        if event.key == Key.F9:
            self.book.cache.clear(); self.book.details.clear();
            self.message = "Recalculated";
            return True;
        if event.key in (Key.UP, Key.DOWN, Key.LEFT, Key.RIGHT):
            dc, dr = {Key.UP:(0,-1), Key.DOWN:(0,1), Key.LEFT:(-1,0), Key.RIGHT:(1,0)}[event.key];
            return self.move(dc,dr,extend=event.shift);
        if event.key == Key.TAB: return self.move(1,0);
        if event.key == Key.ENTER: return self.move(0,1);
        if event.key == Key.PAGE_DOWN: return self.move(0,15,extend=event.shift);
        if event.key == Key.PAGE_UP: return self.move(0,-15,extend=event.shift);
        if event.key == Key.HOME: self.col=1;self.anchor=(self.col,self.row);return True;
        if event.key == Key.DELETE:
            addresses = self.selected();
            def remove():
                for address in addresses: self.book.sheets[self.book.sheet].pop(address, None);
            self.book.transaction(remove);
            return True;
        if event.text and event.text.isprintable() and not event.ctrl and not event.alt:
            return self.start_edit(event.text);
        return False;

    def __rich_console__(self, console, options):
        width = max(40, options.max_width);
        height = max(12, console.height-1);
        self.width, self.height = width, height;
        visible_cols = max(1, (width-5)//(self.cell_width+1));
        visible_rows = max(1, height-5-(3 if self.help_visible else 0));
        if self.col < self.first_col: self.first_col = self.col;
        if self.col >= self.first_col+visible_cols: self.first_col = self.col-visible_cols+1;
        if self.row < self.first_row: self.first_row = self.row;
        if self.row >= self.first_row+visible_rows: self.first_row = self.row-visible_rows+1;
        form = self.ask_text if self.ask else (self.editing if self.editing is not None else self.book.cell(self.address).raw);
        prefix = self.ask+": " if self.ask else self.address+": ";
        bar = Text(prefix + form[:max(0,width-len(prefix)-2)], style="bold black on bright_white");
        if self.editing is not None: bar.append(" ◀ EDIT", style="bold yellow on blue");
        yield bar;
        header = Text("    ");
        for col in range(self.first_col, self.first_col+visible_cols):
            header.append(colname(col).center(self.cell_width)+" ", style="black on bright_white");
        yield header;
        selected = set(self.selected());
        for row in range(self.first_row, self.first_row+visible_rows):
            line = Text(str(row).rjust(4), style="bright_white on dark_blue");
            for col in range(self.first_col, self.first_col+visible_cols):
                addr = colname(col)+str(row);
                value = self.book.display(addr);
                cell = self.book.cell(addr);
                if cell.align == "repeat" and value:
                    value = (value * (self.cell_width//len(value)+1))[:self.cell_width];
                elif cell.align == "center": value = value[:self.cell_width].center(self.cell_width);
                elif cell.align == "right" or (not cell.align and isinstance(self.book.cache.get((self.book.sheet,addr)),(int,float))):
                    value = value[:self.cell_width].rjust(self.cell_width);
                else: value = value[:self.cell_width].ljust(self.cell_width);
                if (col,row) == (self.col,self.row): style = "bold white on dark_red";
                elif addr in selected: style = "black on bright_cyan";
                elif value.startswith("#"): style = "bold bright_red on black";
                else: style = "white on black";
                if cell.bold: style = "bold " + style;
                line.append(value+" ", style=style);
            yield line;
        status = self.book.sheet + " | " + self.address + " | " + ("MODIFIED" if self.book.dirty else "READY");
        yield Text(status[:width].ljust(width), style="black on bright_white");
        yield Text(self.message[:width].ljust(width), style="white on dark_blue");
        if self.help_visible:
            yield Text(HELP[:width]);
            yield Text("Ctrl+arrow then F4 inserts a picked range into a formula.");
            yield Text("Menu: F10 / Alt+first-letter; file: Ctrl+S, Ctrl+O.");


def build_app(book, theme=None):
    view = SheetView(book);
    actions = {
        "Save": lambda: view.start_prompt("Save as", view.book.filename or "workbook.ses"),
        "Open": lambda: view.start_prompt("Open"),
        "New sheet": lambda: view.start_prompt("New sheet", "Sheet2"),
        "Undo": view.undo,
        "Redo": view.redo,
        "Copy": view.copy,
        "Paste": view.paste,
        "Bold": view.toggle_bold,
        "Go to": lambda: view.start_prompt("Go to", view.address),
        "Next sheet": view.next_sheet,
        "Help": lambda: setattr(view,"help_visible",not view.help_visible),
    };
    menu = MenuBar([
        Menu("File", [MenuItem("Open", actions["Open"], "Ctrl+O"),
                       MenuItem("Save", actions["Save"], "Ctrl+S"),
                       MenuItem("New sheet", actions["New sheet"]),
                       MenuItem("Quit", lambda: app.stop())]),
        Menu("Edit", [MenuItem("Undo", actions["Undo"], "Ctrl+Z"),
                       MenuItem("Redo", actions["Redo"], "Ctrl+Y"),
                       MenuItem("Copy", actions["Copy"], "Ctrl+C"),
                       MenuItem("Paste", actions["Paste"], "Ctrl+V")]),
        Menu("Style", [MenuItem("Font", submenu=Menu("Font", [MenuItem("Bold", actions["Bold"], "Ctrl+B")])),
                        MenuItem("Bold", actions["Bold"], "Ctrl+B")]),
        Menu("Data", [MenuItem("Go to", actions["Go to"], "F5"),
                       MenuItem("New sheet", actions["New sheet"]) ]),
        Menu("Tools", [MenuItem("Next sheet", actions["Next sheet"], "F6")]),
        Menu("Help", [MenuItem("Keys", actions["Help"], "F1")]),
    ], activation_key="f10");
    desktop = MenuDesktop(menu, view);
    app = Application("SES - sumEditSpreadsheet", root=desktop, theme=theme, mouse=True, capture_control_keys=True);
    view.exit_callback = app.stop;
    app.bind("f10", menu.open);
    return app;


def main(argv=None):
    parser = argparse.ArgumentParser(description="SES - sumEditSpreadsheet (alpha)");
    parser.add_argument("file", nargs="?", help="Open an SES workbook");
    parser.add_argument("--theme", help="Existing shared sumTUI theme, e.g. DOS");
    parser.add_argument("--demo", action="store_true", help="Populate a demonstration sheet");
    args = parser.parse_args(argv);
    try:
        book = Workbook.load(args.file) if args.file else Workbook();
        if args.demo:
            for cell, value in {"A1":"'Item", "B1":"'Price", "A2":"'Tea", "B2":"120",
                                "A3":"'Coffee", "B3":"175", "A4":"'Total", "B4":"=SUM(B2:B3)"}.items():
                book.set(cell,value);
        return build_app(book, theme=args.theme).run();
    except (OSError, ValueError) as exc:
        parser.exit(1, "SES: " + str(exc) + "\n");

if __name__ == "__main__":
    sys.exit(main());
