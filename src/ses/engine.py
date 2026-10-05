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
"""SES formula engine: no eval/exec, bounded references and deterministic recalc."""
import json;
import math;
import os;
import re;
import tempfile;
from dataclasses import dataclass, field;
from decimal import Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_CEILING, ROUND_FLOOR, ROUND_DOWN, ROUND_UP;
from datetime import date;

CELL_RE = re.compile(r'^(\$?)([A-Za-z]{1,3})(\$?)([1-9][0-9]*)$', re.I);
TOKENS = re.compile(r'''\s*(?:(?P<string>"(?:""|[^"])*")|(?P<num>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|(?P<word>\$?[A-Za-z_][A-Za-z0-9_.$]*)|(?P<op><>|<=|>=|[+*/^&%=<>():;,!\-]))''');
MAX_ROWS = 100000;
MAX_COLS = 16384;
MAX_CELLS_PER_RANGE = 100000;

class FormulaError(Exception):
    def __init__(self, code, detail=""):
        self.code = code;
        self.detail = detail or code;
        super().__init__(self.detail);

@dataclass
class Cell:
    raw: str = "";
    bold: bool = False;
    align: str = "";


def colnumber(label):
    num = 0;
    for char in label.upper():
        num = num * 26 + ord(char) - 64;
    return num;

def colname(num):
    if num <= 0 or num > MAX_COLS:
        raise FormulaError("#REF!", "Column out of bounds");
    result = "";
    while num:
        num, r = divmod(num - 1, 26);
        result = chr(65 + r) + result;
    return result;

def split_cell(text):
    match = CELL_RE.fullmatch(text);
    if not match:
        raise FormulaError("#REF!", "Invalid cell reference: " + str(text));
    col = colnumber(match.group(2));
    row = int(match.group(4));
    if col > MAX_COLS or row > MAX_ROWS:
        raise FormulaError("#REF!", "Cell is out of bounds");
    return col, row, bool(match.group(1)), bool(match.group(3));

def shift_ref(address, dx, dy):
    col, row, fixed_col, fixed_row = split_cell(address);
    col += 0 if fixed_col else dx;
    row += 0 if fixed_row else dy;
    if not (1 <= col <= MAX_COLS and 1 <= row <= MAX_ROWS):
        return "#REF!";
    return ("$" if fixed_col else "") + colname(col) + ("$" if fixed_row else "") + str(row);

def relocate_formula(raw, dx, dy):
    """Copy with relative addressing; quoted strings are never modified."""
    if not raw or raw[0] not in "=+@":
        return raw;
    reference = re.compile(r'(?<![\w.])\$?[A-Za-z]{1,3}\$?[1-9]\d*(?![\w])');
    parts = re.split(r'("(?:""|[^"])*")', raw);
    for index in range(0, len(parts), 2):
        def replace(match):
            try:
                return shift_ref(match.group(0), dx, dy);
            except FormulaError:
                return match.group(0);
        parts[index] = reference.sub(replace, parts[index]);
    return "".join(parts);

class Lexer:
    def __init__(self, text):
        self.tokens = [];
        pos = 0;
        while pos < len(text):
            match = TOKENS.match(text, pos);
            if not match:
                if text[pos:].strip() == "":
                    break;
                raise FormulaError("#PARSE!", "Unexpected character at " + str(pos));
            kind = match.lastgroup;
            self.tokens.append((kind, match.group(kind)));
            pos = match.end();
            if len(self.tokens) > 5000:
                raise FormulaError("#PARSE!", "Formula too long");
        self.tokens.append(("end", ""));
        self.index = 0;

    def peek(self):
        return self.tokens[self.index][1];

    def get(self):
        value = self.tokens[self.index];
        self.index += 1;
        return value;

    def accept(self, *values):
        if self.peek() in values:
            return self.get()[1];
        return None;

    def expect(self, expected):
        if not self.accept(expected):
            raise FormulaError("#PARSE!", "Expected " + expected);

PRECEDENCE = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1, "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5};

class Parser:
    def __init__(self, source):
        self.lex = Lexer(source);

    def parse(self):
        result = self.expr();
        if self.lex.peek() != "":
            raise FormulaError("#PARSE!", "Unexpected token " + self.lex.peek());
        return result;

    def expr(self, minimum=0):
        kind, value = self.lex.get();
        if value in ("+", "-"):
            left = ("unary", value, self.expr(5));
        elif value == "(":
            left = self.expr();
            self.lex.expect(")");
        elif kind == "num":
            left = ("number", float(value));
        elif kind == "string":
            left = ("string", value[1:-1].replace('""', '"'));
        elif kind == "word":
            if self.lex.accept("!"):
                address = self.lex.get()[1];
                left = ("cell", value.lstrip("$"), address);
            elif self.lex.accept("("):
                args = [];
                if self.lex.peek() != ")":
                    while True:
                        args.append(self.expr());
                        if not self.lex.accept(";", ","):
                            break;
                self.lex.expect(")");
                left = ("call", value.upper(), args);
            elif CELL_RE.fullmatch(value):
                left = ("cell", None, value);
            elif "." in value:
                sheet, address = value.rsplit(".", 1);
                if CELL_RE.fullmatch(address):
                    left = ("cell", sheet.lstrip("$"), address);
                else:
                    raise FormulaError("#NAME?", "Unknown identifier: " + value);
            else:
                left = ("name", value.upper());
        else:
            raise FormulaError("#PARSE!", "Unexpected token " + value);
        if self.lex.accept(":"):
            target = self.expr(7);
            left = ("range", left, target);
        while self.lex.peek() in PRECEDENCE and PRECEDENCE[self.lex.peek()] >= minimum:
            op = self.lex.get()[1];
            priority = PRECEDENCE[op];
            right = self.expr(priority if op == "^" else priority + 1);
            left = ("binary", op, left, right);
        return left;


def _flatten(arguments):
    for item in arguments:
        if isinstance(item, list):
            yield from _flatten(item);
        else:
            yield item;

def _numeric(value):
    if isinstance(value, FormulaError):
        raise value;
    if value is None or value == "":
        return 0.0;
    if isinstance(value, bool):
        return float(value);
    try:
        return float(value);
    except (TypeError, ValueError, OverflowError):
        raise FormulaError("#VALUE!", "A numeric value is required");

def _numbers(args):
    result = [];
    for val in _flatten(args):
        if val is None or val == "":
            continue;
        try:
            result.append(_numeric(val));
        except FormulaError:
            if isinstance(val, str):
                continue;
            raise;
    return result;

def _round(value, places=0, mode=ROUND_HALF_UP):
    n = Decimal(str(_numeric(value)));
    quant = Decimal(1).scaleb(-int(_numeric(places)));
    return float(n.quantize(quant, rounding=mode));

def _pattern_match(value, criterion):
    if isinstance(criterion, (int, float)):
        return _numeric(value) == criterion if value not in (None, "") else False;
    criteria = str(criterion);
    match = re.match(r'^(<=|>=|<>|=|<|>)(.*)$', criteria);
    if match:
        op, rhs = match.groups();
        try:
            left, right = float(value), float(rhs);
        except (TypeError, ValueError):
            left, right = str(value).casefold(), rhs.casefold();
        return {"=": lambda: left == right, "<>": lambda: left != right,
                "<": lambda: left < right, ">": lambda: left > right,
                "<=": lambda: left <= right, ">=": lambda: left >= right}[op]();
    wildcard = re.escape(criteria).replace(r"\*", ".*").replace(r"\?", ".");
    return re.fullmatch(wildcard, str(value if value is not None else ""), re.I) is not None;

def call_function(name, args):
    flat = list(_flatten(args));
    nums = _numbers(args);
    if name == "SUM": return sum(nums);
    if name in ("AVG", "AVERAGE"): return sum(nums) / len(nums) if nums else 0;
    if name == "MIN": return min(nums) if nums else 0;
    if name == "MAX": return max(nums) if nums else 0;
    if name == "COUNT": return len(nums);
    if name in ("LENGTH", "LEN"): return len(str(args[0]));
    if name in ("CONCAT", "CONCATENATE"): return "".join(str(v if v is not None else "") for v in flat);
    if name in ("STRING", "STR"): return str(args[0]);
    if name == "VALUE": return _numeric(args[0]);
    if name == "ABS": return abs(_numeric(args[0]));
    if name == "MOD": return _numeric(args[0]) % _numeric(args[1]);
    if name == "ROUND": return _round(*args);
    if name in ("ROUNDUP", "ROUNDDOWN"):
        return _round(args[0], args[1] if len(args) > 1 else 0,
                      ROUND_UP if name == "ROUNDUP" else ROUND_DOWN);
    if name in ("CEIL", "CEILING"): return math.ceil(_numeric(args[0]));
    if name == "FLOOR": return math.floor(_numeric(args[0]));
    if name == "LEFT": return str(args[0])[:max(0, int(_numeric(args[1])))];
    if name == "RIGHT": return str(args[0])[-max(0, int(_numeric(args[1]))):] if int(_numeric(args[1])) else "";
    if name == "MID": return str(args[0])[max(0, int(_numeric(args[1])) - 1):][:max(0, int(_numeric(args[2])))];
    if name == "FIND":
        where = str(args[1]).find(str(args[0]), max(0, int(_numeric(args[2])) - 1) if len(args) > 2 else 0);
        if where < 0: raise FormulaError("#VALUE!", "Substring not found");
        return where + 1;
    if name == "UPPER": return str(args[0]).upper();
    if name == "LOWER": return str(args[0]).lower();
    if name == "TRIM": return " ".join(str(args[0]).split());
    if name == "REPLACE":
        text = str(args[0]); start = int(_numeric(args[1])) - 1; count = int(_numeric(args[2]));
        return text[:start] + str(args[3]) + text[start + count:];
    if name == "CHOOSE":
        index = int(_numeric(args[0]));
        if not 1 <= index < len(args): raise FormulaError("#VALUE!", "CHOOSE index out of range");
        return args[index];
    if name == "INDEX":
        data = args[0]; index = int(_numeric(args[1])) - 1;
        if not isinstance(data, list): raise FormulaError("#VALUE!", "INDEX expects a range");
        try: return data[index];
        except IndexError: raise FormulaError("#REF!", "INDEX out of bounds");
    if name == "COUNTIF": return sum(_pattern_match(val, args[1]) for val in flat_list(args[0]));
    if name == "SUMIF":
        criteria = flat_list(args[0]); values = flat_list(args[2]) if len(args) > 2 else criteria;
        if len(criteria) != len(values): raise FormulaError("#RANGE!", "SUMIF shapes differ");
        return sum(_numeric(v) for test, v in zip(criteria, values) if _pattern_match(test, args[1]));
    if name == "COUNTIFS":
        if len(args) % 2: raise FormulaError("#VALUE!", "COUNTIFS expects range/criterion pairs");
        pairs = [(flat_list(args[k]), args[k + 1]) for k in range(0, len(args), 2)];
        if len({len(x[0]) for x in pairs}) != 1: raise FormulaError("#RANGE!", "COUNTIFS shapes differ");
        return sum(all(_pattern_match(values[i], criterion) for values, criterion in pairs) for i in range(len(pairs[0][0])));
    if name == "SUMIFS":
        base = flat_list(args[0]); pairs = [(flat_list(args[k]), args[k + 1]) for k in range(1, len(args), 2)];
        if any(len(v) != len(base) for v, _ in pairs): raise FormulaError("#RANGE!", "SUMIFS shapes differ");
        return sum(_numeric(base[i]) for i in range(len(base)) if all(_pattern_match(v[i], crit) for v, crit in pairs));
    if name == "SUMPRODUCT":
        lists = [flat_list(v) for v in args];
        if not lists or len({len(v) for v in lists}) != 1: raise FormulaError("#RANGE!", "SUMPRODUCT shapes differ");
        return sum(math.prod(_numeric(v[i]) for v in lists) for i in range(len(lists[0])));
    if name == "DATE": return date(int(args[0]), int(args[1]), int(args[2])).isoformat();
    if name == "TODAY": return date.today().isoformat();
    if name == "VLOOKUP":
        needle, values, position = args[:3];
        if not isinstance(values, list) or not values or not isinstance(values[0], list):
            raise FormulaError("#VALUE!", "VLOOKUP requires a rectangular range");
        column = int(_numeric(position)) - 1;
        for line in values:
            if line and str(line[0]).casefold() == str(needle).casefold():
                try: return line[column];
                except IndexError: raise FormulaError("#REF!", "VLOOKUP column out of bounds");
        raise FormulaError("#N/A", "No matching row");
    if name == "HLOOKUP":
        needle, values, position = args[:3];
        if not isinstance(values, list) or not values or not isinstance(values[0], list):
            raise FormulaError("#VALUE!", "HLOOKUP requires rectangular range");
        row = int(_numeric(position)) - 1;
        for col, value in enumerate(values[0]):
            if str(value).casefold() == str(needle).casefold():
                try: return values[row][col];
                except IndexError: raise FormulaError("#REF!", "HLOOKUP row out of bounds");
        raise FormulaError("#N/A", "No matching column");
    raise FormulaError("#NAME?", "Unknown function: " + name);

def flat_list(value):
    return list(_flatten([value]));

class Workbook:
    def __init__(self):
        self.sheets = {"Sheet1": {}};
        self.sheet = "Sheet1";
        self.undo_stack = [];
        self.redo_stack = [];
        self.version = 0;
        self.cache = {};
        self.details = {};
        self.filename = "";
        self.dirty = False;

    def _snapshot(self):
        return ({s: {k: (v.raw, v.bold, v.align) for k, v in cells.items()} for s, cells in self.sheets.items()}, self.sheet);

    def _restore(self, snapshot):
        self.sheets = {s: {k: Cell(*attrs) for k, attrs in data.items()} for s, data in snapshot[0].items()};
        self.sheet = snapshot[1];
        self._changed();

    def _changed(self):
        self.version += 1;
        self.cache.clear();
        self.details.clear();
        self.dirty = True;

    def transaction(self, changes):
        prior = self._snapshot();
        changes();
        if self._snapshot() != prior:
            self.undo_stack.append(prior);
            self.undo_stack = self.undo_stack[-200:];
            self.redo_stack.clear();
            self._changed();

    def undo(self):
        if not self.undo_stack: return False;
        self.redo_stack.append(self._snapshot());
        self._restore(self.undo_stack.pop());
        return True;

    def redo(self):
        if not self.redo_stack: return False;
        self.undo_stack.append(self._snapshot());
        self._restore(self.redo_stack.pop());
        return True;

    def add_sheet(self, name):
        if not name.strip() or name in self.sheets: raise FormulaError("#SHEET!", "Duplicate or empty sheet name");
        self.transaction(lambda: self.sheets.__setitem__(name, {}));

    def cell(self, addr, sheet=None):
        split_cell(addr);
        tab = sheet or self.sheet;
        if tab not in self.sheets: raise FormulaError("#SHEET!", "Unknown sheet: " + tab);
        return self.sheets[tab].get(addr.replace("$", "").upper(), Cell());

    def set(self, addr, raw, sheet=None):
        tab = sheet or self.sheet;
        key = addr.replace("$", "").upper();
        split_cell(key);
        if tab not in self.sheets: raise FormulaError("#SHEET!", "Unknown sheet: " + tab);
        def action():
            old = self.sheets[tab].get(key, Cell());
            content = str(raw);
            alignment = old.align;
            if content and content[0] in "'^\"\\":
                alignment = {"'": "left", "^": "center", '"': "right", "\\": "repeat"}[content[0]];
                content = content[1:];
                content = "'" + content if content.startswith(("=", "+", "@")) or raw.startswith("'") else content;
            if content or old.bold:
                self.sheets[tab][key] = Cell(content, old.bold, alignment);
            else:
                self.sheets[tab].pop(key, None);
        self.transaction(action);

    def set_bold(self, addresses, sheet=None):
        tab = sheet or self.sheet;
        keys = list(addresses);
        def action():
            target = not all(self.cell(a, tab).bold for a in keys);
            for a in keys:
                key = a.upper(); old = self.cell(key, tab);
                self.sheets[tab][key] = Cell(old.raw, target, old.align);
        self.transaction(action);

    def copy(self, start, dest, rows=1, cols=1, sheet=None):
        tab = sheet or self.sheet;
        a, b, _, _ = split_cell(start);
        x, y, _, _ = split_cell(dest);
        snapshot = {};
        for j in range(rows):
            for i in range(cols):
                source = colname(a + i) + str(b + j);
                snapshot[i, j] = self.cell(source, tab);
        def action():
            for (i, j), item in snapshot.items():
                target = colname(x + i) + str(y + j);
                raw = relocate_formula(item.raw, x - a, y - b);
                self.sheets[tab][target] = Cell(raw, item.bold, item.align);
        self.transaction(action);

    def evaluate(self, address, sheet=None):
        tab = sheet or self.sheet;
        return self._eval_cell(tab, address.replace("$", "").upper(), set());

    def _eval_cell(self, sheet, address, stack):
        key = (sheet, address);
        if key in stack: raise FormulaError("#CYCLE!", "Circular dependency: " + " -> ".join(a for _, a in list(stack) + [key]));
        if key in self.cache:
            result = self.cache[key];
            if isinstance(result, FormulaError): raise result;
            return result;
        stack.add(key);
        try:
            raw = self.cell(address, sheet).raw;
            if not raw:
                result = None;
            elif raw.startswith("'"):
                result = raw[1:];
            elif raw[0] in "=+@":
                source = raw[1:] if raw[0] in "=+" else raw;
                if source.startswith("@"):
                    source = source[1:];
                node = Parser(source).parse();
                result = self._eval(node, sheet, stack);
            else:
                try: result = float(raw) if "." in raw or "e" in raw.lower() else int(raw);
                except ValueError: result = raw;
            self.cache[key] = result;
            return result;
        except FormulaError as exc:
            self.cache[key] = exc;
            self.details[key] = exc.detail;
            raise;
        except (ZeroDivisionError, OverflowError) as exc:
            error = FormulaError("#DIV/0!" if isinstance(exc, ZeroDivisionError) else "#NUM!", str(exc));
            self.cache[key] = error;
            self.details[key] = error.detail;
            raise error;
        finally:
            stack.remove(key);

    def _eval(self, node, sheet, stack):
        kind = node[0];
        if kind in ("number", "string"): return node[1];
        if kind == "name":
            if node[1] in ("TRUE", "FALSE"): return node[1] == "TRUE";
            raise FormulaError("#NAME?", "Unknown name: " + node[1]);
        if kind == "cell":
            return self._eval_cell(node[1] or sheet, node[2].replace("$", "").upper(), stack);
        if kind == "range":
            left, right = node[1], node[2];
            if left[0] != "cell" or right[0] != "cell":
                raise FormulaError("#RANGE!", "Range boundaries must be cell addresses");
            owner = left[1] or sheet;
            if (right[1] or sheet) != owner:
                raise FormulaError("#RANGE!", "Cross-sheet ranges not yet supported");
            a, b, _, _ = split_cell(left[2]);
            c, d, _, _ = split_cell(right[2]);
            if (abs(c-a)+1) * (abs(d-b)+1) > MAX_CELLS_PER_RANGE:
                raise FormulaError("#RANGE!", "Range too large");
            return [[self._eval_cell(owner, colname(i) + str(j), stack)
                     for i in range(min(a,c), max(a,c)+1)]
                    for j in range(min(b,d), max(b,d)+1)];
        if kind == "unary":
            value = _numeric(self._eval(node[2], sheet, stack));
            return value if node[1] == "+" else -value;
        if kind == "binary":
            a = self._eval(node[2], sheet, stack);
            b = self._eval(node[3], sheet, stack);
            op = node[1];
            if op == "&": return str(a if a is not None else "") + str(b if b is not None else "");
            if op in ("=", "<>", "<", ">", "<=", ">="):
                x, y = (_numeric(a), _numeric(b)) if isinstance(a, (int,float)) and isinstance(b, (int,float)) else (str(a), str(b));
                return {"=": lambda: x == y, "<>": lambda: x != y, "<": lambda: x < y,
                        ">": lambda: x > y, "<=": lambda: x <= y, ">=": lambda: x >= y}[op]();
            x, y = _numeric(a), _numeric(b);
            return {"+": lambda: x+y, "-": lambda: x-y, "*": lambda: x*y,
                    "/": lambda: x/y, "^": lambda: x**y}[op]();
        if kind == "call":
            name, parameters = node[1], node[2];
            if name == "IF":
                if len(parameters) not in (2, 3): raise FormulaError("#VALUE!", "IF(condition; true; false)");
                chosen = 1 if self._eval(parameters[0], sheet, stack) else 2;
                return self._eval(parameters[chosen], sheet, stack) if chosen < len(parameters) else False;
            if name == "AND":
                return all(bool(self._eval(x, sheet, stack)) for x in parameters);
            if name == "OR":
                return any(bool(self._eval(x, sheet, stack)) for x in parameters);
            if name == "NOT":
                return not bool(self._eval(parameters[0], sheet, stack));
            args = [self._eval(x, sheet, stack) for x in parameters];
            try:
                return call_function(name, args);
            except (IndexError, ValueError, ArithmeticError, TypeError) as exc:
                raise FormulaError("#VALUE!", str(exc));
        raise FormulaError("#PARSE!", "Unknown AST node");

    def display(self, address, sheet=None):
        try:
            value = self.evaluate(address, sheet);
            if value is None: return "";
            if isinstance(value, bool): return "TRUE" if value else "FALSE";
            if isinstance(value, float): return str(int(value)) if value.is_integer() else format(value, ".12g");
            return str(value);
        except FormulaError as exc:
            return exc.code;

    def save(self, path):
        data = {"format": "ses-workbook-v1", "sheets": {s: {a: vars(c) for a, c in cells.items()} for s, cells in self.sheets.items()}, "active": self.sheet};
        path = os.path.abspath(path);
        directory = os.path.dirname(path);
        fd, temp = tempfile.mkstemp(prefix=".ses-", suffix=".tmp", dir=directory);
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2);
                handle.flush(); os.fsync(handle.fileno());
            os.replace(temp, path);
        finally:
            if os.path.exists(temp): os.unlink(temp);
        self.filename = path;
        self.dirty = False;

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle);
        if data.get("format") != "ses-workbook-v1":
            raise ValueError("Unsupported SES workbook format");
        book = cls();
        book.sheets = {};
        for name, cells in data["sheets"].items():
            book.sheets[name] = {};
            for addr, payload in cells.items():
                split_cell(addr);
                book.sheets[name][addr] = Cell(**payload);
        book.sheet = data.get("active", next(iter(book.sheets)));
        if not book.sheets or book.sheet not in book.sheets:
            raise ValueError("Invalid sheet set");
        book.filename = os.path.abspath(path);
        return book;
