"""SES 0.1 calculation core; no eval, no user Python execution."""
from __future__ import annotations
import copy
import json
import math
import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_EVEN, ROUND_UP, ROUND_DOWN
from pathlib import Path

CELL = re.compile(r'(?i)^(\$?)([A-Z]+)(\$?)([1-9][0-9]*)$')
TOKEN = re.compile(r'''\s*(?:(?P<string>"(?:[^"]|"")*")|(?P<number>\d+(?:_\d+)*(?:\.\d+(?:_\d+)*)?(?:[eE][+-]?\d+)?)|(?P<word>\$?[A-Za-z_][A-Za-z0-9_.$]*\$?[0-9]*|\$[A-Za-z]+\$?[0-9]+)|(?P<op><=|>=|<>|!=|[+*/^&=<>(),;:!%-]))''')

class SheetError(Exception):
    def __init__(self, code, detail=''):
        self.code, self.detail = code, detail
        super().__init__(code)


def colnumber(label):
    result = 0
    for c in label.upper():
        result = result * 26 + ord(c) - 64
    return result


def colname(n):
    if n < 1: raise SheetError('#REF!')
    result = ''
    while n:
        n, k = divmod(n - 1, 26)
        result = chr(65+k) + result
    return result


def cellref(addr):
    m = CELL.fullmatch(addr)
    if not m: raise SheetError('#REF!', f'Invalid cell: {addr}')
    return colnumber(m[2]), int(m[4]), bool(m[1]), bool(m[3])


def shift_ref(ref, dc, dr):
    c, r, ca, ra = cellref(ref)
    c += 0 if ca else dc
    r += 0 if ra else dr
    if c < 1 or r < 1: return '#REF!'
    return ('$' if ca else '')+colname(c)+('$' if ra else '')+str(r)


def transform_formula(expr, dc, dr):
    """Shift cell references while leaving quoted literal strings untouched."""
    pat = re.compile(r'"(?:[^"]|"")*"|(?<![\w.])\$?[A-Za-z]{1,4}\$?[1-9]\d*(?![\w.])')
    def sub(m):
        word=m.group()
        if word.startswith('"'): return word
        return shift_ref(word, dc, dr)
    return pat.sub(sub, expr)


def tokenize(expr):
    pos, out = 0, []
    while pos < len(expr):
        if expr[pos:].strip() == '': break
        m = TOKEN.match(expr, pos)
        if not m: raise SheetError('#PARSE!', f'Unexpected character at {pos}: {expr[pos:pos+12]}')
        typ = m.lastgroup
        out.append((typ, m[typ]))
        pos=m.end()
    out.append(('end',''))
    return out


class Parser:
    def __init__(self, s): self.t=tokenize(s); self.i=0
    def see(self): return self.t[self.i][1]
    def take(self, value=None):
        typ, val = self.t[self.i]
        if value is not None and val != value: raise SheetError('#PARSE!', f'Expected {value}, got {val}')
        self.i+=1
        return typ, val
    def parse(self):
        node=self.expr()
        if self.see() != '': raise SheetError('#PARSE!', f'Unexpected token: {self.see()}')
        return node
    def expr(self, minimum=0):
        typ, val = self.take()
        if val in ('+', '-'): node=('unary',val,self.expr(65))
        elif val=='(':
            node=self.expr(); self.take(')')
        elif typ=='number': node=('literal',float(val.replace('_','')))
        elif typ=='string': node=('literal',val[1:-1].replace('""','"'))
        elif typ=='word':
            if self.see()=='!':
                self.take('!'); _,addr=self.take(); node=('ref',val,addr)
            elif self.see()=='(':
                self.take('('); args=[]
                if self.see()!=')':
                    while True:
                        args.append(self.expr())
                        if self.see() not in (',',';'): break
                        self.take()
                self.take(')'); node=('call',val.upper().lstrip('@'),args)
            elif CELL.fullmatch(val): node=('ref',None,val)
            elif val.upper() in ('TRUE','FALSE'): node=('literal',val.upper()=='TRUE')
            else: raise SheetError('#NAME?',f'Unknown name {val}')
        else: raise SheetError('#PARSE!', f'Unexpected {val}')
        precedence={'=':10,'<>':10,'!=':10,'>':10,'<':10,'>=':10,'<=':10,'&':15,'+':20,'-':20,'*':30,'/':30,'%':30,'^':40,':':50}
        while (op:=self.see()) in precedence and precedence[op]>=minimum:
            self.take(); p=precedence[op]
            rhs=self.expr(p if op=='^' else p+1)
            if op==':':
                if node[0]!='ref' or rhs[0]!='ref' or node[1]!=rhs[1]: raise SheetError('#RANGE!')
                node=('range',node[1],node[2],rhs[2])
            else: node=('bin',op,node,rhs)
        return node


def flatten(arg):
    if isinstance(arg,list):
        for x in arg: yield from flatten(x)
    else: yield arg


def number(x):
    if x is None or x=='': return 0.0
    if isinstance(x,bool): return float(x)
    if isinstance(x,(int,float)): return float(x)
    try: return float(str(x).replace('_',''))
    except (ValueError,TypeError): raise SheetError('#VALUE!',f'Not numeric: {x!r}')


def numeric_values(args):
    for x in flatten(args):
        if isinstance(x,(int,float)) and not isinstance(x,bool): yield float(x)


def predicate(test):
    if isinstance(test,str):
        m=re.match(r'^(>=|<=|<>|!=|>|<|=)(.*)$',test)
        if m:
            op, raw=m.groups()
            try: target=float(raw); cast=lambda v: number(v)
            except ValueError: target=raw.casefold(); cast=lambda v: str(v if v is not None else '').casefold()
            def check(v):
                try:
                    x=cast(v)
                    return {'>':lambda:x>target,'<':lambda:x<target,'>=':lambda:x>=target,'<=':lambda:x<=target,'=':lambda:x==target,'<>':lambda:x!=target,'!=':lambda:x!=target}[op]()
                except SheetError: return False
            return check
    return lambda v: v==test or (isinstance(v,str) and isinstance(test,str) and v.casefold()==test.casefold())


def function(name, args):
    a=args
    vals=list(numeric_values(a))
    if name=='SUM': return sum(vals)
    if name in ('AVG','AVERAGE'): return sum(vals)/len(vals) if vals else 0
    if name=='MIN': return min(vals) if vals else 0
    if name=='MAX': return max(vals) if vals else 0
    if name=='COUNT': return len(vals)
    if name=='COUNTA': return sum(v not in (None,'') for v in flatten(a))
    if name in ('COUNTIF','SUMIF','COUNTIFS','SUMIFS'):
        if name in ('COUNTIF','SUMIF'):
            if len(a)<2: raise SheetError('#VALUE!')
            source=list(flatten([a[0]])); tests=[(source,predicate(a[1]))]
            target=list(flatten([a[2]])) if name=='SUMIF' and len(a)>2 else source
        else:
            if len(a)<2: raise SheetError('#VALUE!')
            if name=='SUMIFS':
                if len(a)<3 or (len(a)-1)%2: raise SheetError('#VALUE!')
                target=list(flatten([a[0]])); offset=1
            else:
                if len(a)%2: raise SheetError('#VALUE!')
                target=list(flatten([a[0]])); offset=0
            tests=[(list(flatten([a[i]])),predicate(a[i+1])) for i in range(offset,len(a),2)]
        if any(len(t[0])!=len(target) for t in tests): raise SheetError('#RANGE!')
        ids=[i for i in range(len(target)) if all(pred(seq[i]) for seq,pred in tests)]
        return len(ids) if name.startswith('COUNT') else sum(number(target[i]) for i in ids if target[i] not in (None,''))
    if name=='IF': return a[1] if a[0] else (a[2] if len(a)>2 else False)
    if name=='AND': return all(map(bool,a))
    if name=='OR': return any(map(bool,a))
    if name=='NOT': return not bool(a[0])
    if name=='ABS': return abs(number(a[0]))
    if name=='SQRT': return math.sqrt(number(a[0]))
    if name=='MOD': return number(a[0])%number(a[1])
    if name=='INT': return math.floor(number(a[0]))
    if name in ('ROUND','ROUNDUP','ROUNDDOWN'):
        d=int(number(a[1])) if len(a)>1 else 0
        mode={'ROUND':ROUND_HALF_EVEN,'ROUNDUP':ROUND_UP,'ROUNDDOWN':ROUND_DOWN}[name]
        try: return float(Decimal(str(number(a[0]))).quantize(Decimal('1').scaleb(-d),rounding=mode))
        except Exception: raise SheetError('#VALUE!')
    if name in ('CEIL','CEILING'): return math.ceil(number(a[0]))
    if name=='FLOOR': return math.floor(number(a[0]))
    if name=='VALUE': return number(a[0])
    if name in ('STRING','STR'): return str(a[0] if a[0] is not None else '')
    if name in ('CONCAT','CONCATENATE'): return ''.join(str(v if v is not None else '') for v in flatten(a))
    if name=='LEFT': return str(a[0])[:max(0,int(number(a[1])))]
    if name=='RIGHT':
        count=max(0,int(number(a[1]))); return str(a[0])[-count:] if count else ''
    if name=='MID': return str(a[0])[max(0,int(number(a[1]))-1):][:max(0,int(number(a[2])))]
    if name in ('FIND','SEARCH'):
        source=str(a[1]); needle=str(a[0]); pos=max(0,int(number(a[2]))-1) if len(a)>2 else 0
        idx=(source.find(needle,pos) if name=='FIND' else source.casefold().find(needle.casefold(),pos))
        if idx<0: raise SheetError('#VALUE!',f'{needle!r} not found')
        return idx+1
    if name in ('LENGTH','LEN'): return len(str(a[0]))
    if name=='UPPER': return str(a[0]).upper()
    if name=='LOWER': return str(a[0]).lower()
    if name=='TRIM': return ' '.join(str(a[0]).split())
    if name=='CHOOSE': return a[int(number(a[0]))]
    if name=='INDEX':
        matrix=a[0]; row=int(number(a[1]))-1; col=int(number(a[2]))-1 if len(a)>2 else 0
        if not isinstance(matrix,list): return matrix
        if matrix and isinstance(matrix[0],list): return matrix[row][col]
        return matrix[row]
    if name in ('VLOOKUP','HLOOKUP'):
        if len(a)<3 or not isinstance(a[1],list): raise SheetError('#VALUE!')
        matrix=a[1]; offset=int(number(a[2]))-1
        exact=not bool(a[3]) if len(a)>3 else True
        if not exact: raise SheetError('#VALUE!','Approximate lookup not implemented')
        if name=='VLOOKUP':
            for row in matrix:
                if row[0]==a[0]: return row[offset]
        else:
            for j,key in enumerate(matrix[0]):
                if key==a[0]: return matrix[offset][j]
        raise SheetError('#N/A','Lookup not found')
    if name=='SUMPRODUCT':
        seqs=[list(flatten([x])) for x in a]
        if len({len(s) for s in seqs})>1: raise SheetError('#RANGE!')
        return sum(math.prod(number(s[i]) for s in seqs) for i in range(len(seqs[0])))
    raise SheetError('#NAME?',f'Unknown function: {name}')


def display_value(value, picture=''):
    """Return the canonical display text for a cell value.

    The TUI and every preview/export path must use this same conversion so
    plain numeric cells do not acquire formatting that was never requested.
    """
    shown=format_picture(value,picture);
    if shown is None: return '';
    if isinstance(shown,float): return format(shown,'.11g');
    return str(shown);


def format_picture(value, picture):
    """Format a display value without changing its stored value.

    SES PICTURE alpha syntax: 0 = required digit, # = optional digit; the
    rightmost '.' or ',' between digit placeholders is the decimal mark.
    Other characters are literals, so ``$ 0000.00`` is immediately useful.
    """
    if not picture or value is None: return value;
    if not isinstance(value,(int,float)) or isinstance(value,bool): return str(value);
    pic=str(picture); positions=[i for i,c in enumerate(pic) if c in '0#'];
    if not positions: return pic;
    first,last=min(positions),max(positions); core=pic[first:last+1]; prefix=pic[:first]; suffix=pic[last+1:];
    decimal=-1; decchar='.';
    for i,c in enumerate(core):
        if c in '.,' and any(x in '0#' for x in core[:i]) and any(x in '0#' for x in core[i+1:]): decimal=i; decchar=c;
    left=core if decimal<0 else core[:decimal]; right='' if decimal<0 else core[decimal+1:];
    lslots=sum(c in '0#' for c in left); rslots=sum(c in '0#' for c in right);
    neg=float(value)<0; num=abs(float(value)); rendered=f"{num:.{rslots}f}"; ip,_,fp=rendered.partition('.');
    # Preserve values wider than the picture instead of silently truncating them.
    if len(ip)>lslots: return str(value);
    digits=list(ip.rjust(lslots,'0')); di=0; out='';
    leading=len(ip); optional_to_blank=max(0,lslots-leading); seen_slots=0;
    for c in left:
        if c in '0#':
            d=digits[di]; di+=1;
            if c=='#' and seen_slots<optional_to_blank: d=' ';
            seen_slots+=1; out+=d;
        else: out+=c;
    if rslots:
        di=0; rout='';
        for c in right:
            if c in '0#': rout+=fp[di] if di<len(fp) else ('0' if c=='0' else ' '); di+=1;
            else: rout+=c;
        out+=decchar+rout;
    if neg: out='-'+out;
    return prefix+out+suffix;


@dataclass
class Cell:
    raw: str=''
    bold: bool=False
    align: str='general'
    underline: bool=False
    fg: int=7
    bg: int=0
    border_top: str='none'
    border_right: str='none'
    border_bottom: str='none'
    border_left: str='none'
    picture: str=''
    fg_explicit: bool=False
    bg_explicit: bool=False

@dataclass
class Sheet:
    cells: dict=field(default_factory=dict)
    column_widths: dict=field(default_factory=dict)
    row_heights: dict=field(default_factory=dict)


class Book:
    def __init__(self):
        self.sheets={'Sheet1':Sheet()}
        self.active='Sheet1'
        self.history=[]; self.future=[]
        self.max_history=100
        self.values={}; self.dirty=True
        self.last_error_detail=''
    def snapshot(self): return copy.deepcopy((self.sheets,self.active))
    def change(self, callback):
        old=self.snapshot(); callback()
        if self.snapshot()!=old:
            self.history.append(old); self.history=self.history[-self.max_history:]; self.future.clear(); self.dirty=True
    def undo(self):
        if self.history:
            self.future.append(self.snapshot()); self.sheets,self.active=self.history.pop(); self.dirty=True
    def redo(self):
        if self.future:
            self.history.append(self.snapshot()); self.sheets,self.active=self.future.pop(); self.dirty=True
    def add_sheet(self,name):
        if not name or name in self.sheets: raise SheetError('#SHEET!')
        def apply(): self.sheets[name]=Sheet(); self.active=name
        self.change(apply)
    def get(self,addr,sheet=None):
        sh=sheet or self.active
        if sh not in self.sheets: raise SheetError('#SHEET!')
        c,r,*_=cellref(addr)
        return self.sheets[sh].cells.get(f'{colname(c)}{r}',Cell())
    def put(self,addr,raw,sheet=None):
        sh=sheet or self.active
        c,r,*_=cellref(addr); key=f'{colname(c)}{r}'
        def apply():
            old=self.get(key,sh)
            prefix=raw[0] if raw and raw[0] in ('\'','^','"','\\') else None
            align={'\'':'left','^':'center','"':'right','\\':'repeat'}.get(prefix,'general')
            self.sheets[sh].cells[key]=Cell(raw,old.bold,align,old.underline,old.fg,old.bg,old.border_top,old.border_right,old.border_bottom,old.border_left,old.picture,old.fg_explicit,old.bg_explicit)
        self.change(apply)
    def toggle_bold(self,addresses):
        def apply():
            for addr in addresses:
                c=self.get(addr); c.bold=not c.bold
                x,y,*_=cellref(addr); self.sheets[self.active].cells[f'{colname(x)}{y}']=c
        self.change(apply)
    def copy_cell(self,src,dst):
        a,b,*_=cellref(src); c,d,*_=cellref(dst)
        def apply():
            source=copy.deepcopy(self.get(src))
            if source.raw.startswith(('=','+','@')): source.raw=source.raw[:1]+transform_formula(source.raw[1:],c-a,d-b)
            self.sheets[self.active].cells[f'{colname(c)}{d}']=source
        self.change(apply)
    def style(self,addresses,attribute,value=None):
        if attribute not in ('bold','underline','fg','bg','align','border_top','border_right','border_bottom','border_left','picture'):
            raise ValueError('Unknown style')
        addresses=list(addresses)
        def apply():
            for addr in addresses:
                cell=copy.deepcopy(self.get(addr))
                current=getattr(cell,attribute)
                setattr(cell,attribute,not current if value is None else value)
                if attribute=='fg': cell.fg_explicit=True
                if attribute=='bg': cell.bg_explicit=True
                self.sheets[self.active].cells[addr]=cell
        self.change(apply)


    def column_width(self, col, sheet=None):
        sh=self.sheets[sheet or self.active];
        return max(1,int(sh.column_widths.get(str(int(col)),12)));

    def row_height(self, row, sheet=None):
        sh=self.sheets[sheet or self.active];
        return max(1,int(sh.row_heights.get(str(int(row)),1)));

    def set_column_width(self, cols, width):
        width=max(1,min(254,int(width))); cols=[int(c) for c in cols]; sh=self.sheets[self.active];
        def apply():
            for col in cols: sh.column_widths[str(col)]=width;
        self.change(apply);

    def set_row_height(self, rows, height):
        height=max(1,min(99,int(height))); rows=[int(r) for r in rows]; sh=self.sheets[self.active];
        def apply():
            for row in rows: sh.row_heights[str(row)]=height;
        self.change(apply);

    def set_picture(self, addresses, picture):
        self.style(addresses,'picture',str(picture or ''));



    def border(self, addresses, style="single", outline=False):
        """Apply semantic cell borders to a rectangular selection in one undo unit."""
        style=str(style or "none").lower();
        if style not in ("none","single","thick"): raise ValueError("Unknown border style")
        addresses=list(addresses);
        if not addresses: return
        coords=[cellref(addr)[:2] for addr in addresses];
        minc=min(c for c,_ in coords); maxc=max(c for c,_ in coords); minr=min(r for _,r in coords); maxr=max(r for _,r in coords);
        selected={(c,r) for c,r in coords};
        def apply():
            for c,r in selected:
                addr=f"{colname(c)}{r}"; cell=copy.deepcopy(self.get(addr));
                if style == "none":
                    cell.border_top=cell.border_right=cell.border_bottom=cell.border_left="none";
                elif outline:
                    cell.border_top=style if r==minr else cell.border_top;
                    cell.border_bottom=style if r==maxr else cell.border_bottom;
                    cell.border_left=style if c==minc else cell.border_left;
                    cell.border_right=style if c==maxc else cell.border_right;
                else:
                    cell.border_top=cell.border_right=cell.border_bottom=cell.border_left=style;
                self.sheets[self.active].cells[addr]=cell;
        self.change(apply);

    def copy_block(self,source,destination,move=False):
        """Copy rectangular block to destination top-left in one undo unit."""
        def bounds(spec):
            left,right=(spec.split(':',1)+[spec])[:2] if ':' in spec else (spec,spec)
            c1,r1,*_=cellref(left); c2,r2,*_=cellref(right)
            return min(c1,c2),min(r1,r2),max(c1,c2),max(r1,r2)
        x1,y1,x2,y2=bounds(source)
        dx,dy,*_=cellref(destination)
        width=x2-x1+1; height=y2-y1+1
        if width*height>50000: raise SheetError('#RANGE!','Block too large')
        sheet=self.sheets[self.active]
        originals={(x,y):copy.deepcopy(sheet.cells.get(f'{colname(x)}{y}',Cell()))
                   for y in range(y1,y2+1) for x in range(x1,x2+1)}
        def apply():
            if move:
                for x,y in originals: sheet.cells.pop(f'{colname(x)}{y}',None)
            for (x,y),source_cell in originals.items():
                cell=copy.deepcopy(source_cell)
                if not move and cell.raw.startswith(('=','+','@')):
                    cell.raw=cell.raw[:1]+transform_formula(cell.raw[1:],dx+x-x1-x,dy+y-y1-y)
                target=f'{colname(dx+x-x1)}{dy+y-y1}'
                if cell == Cell(): sheet.cells.pop(target,None)
                else: sheet.cells[target]=cell
        self.change(apply)

    def fill(self,range_spec,direction):
        """Fill down/right using top row/left column as source."""
        start,end=range_spec.split(':',1)
        x1,y1,*_=cellref(start); x2,y2,*_=cellref(end)
        lo_x,hi_x=sorted((x1,x2)); lo_y,hi_y=sorted((y1,y2))
        if (hi_x-lo_x+1)*(hi_y-lo_y+1)>50000: raise SheetError('#RANGE!')
        if direction not in ('down','right'): raise ValueError('fill down/right')
        sh=self.sheets[self.active]
        originals={k:copy.deepcopy(v) for k,v in sh.cells.items()}
        def apply():
            for y in range(lo_y,hi_y+1):
                for x in range(lo_x,hi_x+1):
                    sx,sy=(x,lo_y) if direction=='down' else (lo_x,y)
                    src=copy.deepcopy(originals.get(f'{colname(sx)}{sy}',Cell()))
                    if src.raw.startswith(('=','+','@')):
                        src.raw=src.raw[:1]+transform_formula(src.raw[1:],x-sx,y-sy)
                    key=f'{colname(x)}{y}'
                    if src==Cell(): sh.cells.pop(key,None)
                    else: sh.cells[key]=src
        self.change(apply)

    def insert(self,axis,index,count=1):
        """Insert rows/columns; adjust references on the active sheet.

        Current alpha cannot fully track references from other sheets or external files.
        """
        if axis not in ('row','col') or index<1 or count<1: raise ValueError('Invalid insertion')
        if count>1000: raise SheetError('#RANGE!')
        target_sheet=self.active
        pattern=re.compile(r'"(?:[^"]|"")*"|(?<![\w.])(?:(?P<sheet>[A-Za-z_][A-Za-z0-9_]*)!)?(?P<ref>\$?[A-Za-z]{1,4}\$?[1-9]\d*)(?![\w.])')
        def replace_refs(raw,formula_sheet):
            if not raw.startswith(('=','+','@')): return raw
            def sub(m):
                word=m.group()
                if word.startswith('"'): return word
                named=m.group('sheet')
                if (named or formula_sheet)!=target_sheet: return word
                x,y,ca,ra=cellref(m.group('ref'))
                if axis=='row' and y>=index: y+=count
                if axis=='col' and x>=index: x+=count
                ref=('$' if ca else '')+colname(x)+('$' if ra else '')+str(y)
                return (named+'!' if named else '')+ref
            return raw[:1]+pattern.sub(sub,raw[1:])
        def apply():
            for name,sh in self.sheets.items():
                rebuilt={}
                for addr,cell in sh.cells.items():
                    x,y,*_=cellref(addr)
                    if name==target_sheet:
                        if axis=='row' and y>=index: y+=count
                        if axis=='col' and x>=index: x+=count
                    cell=copy.deepcopy(cell)
                    cell.raw=replace_refs(cell.raw,name)
                    rebuilt[f'{colname(x)}{y}']=cell
                sh.cells=rebuilt
                if name==target_sheet:
                    if axis=='row':
                        sh.row_heights={str((int(k)+count) if int(k)>=index else int(k)):v for k,v in sh.row_heights.items()}
                    else:
                        sh.column_widths={str((int(k)+count) if int(k)>=index else int(k)):v for k,v in sh.column_widths.items()}
        self.change(apply)

    def evaluate(self,addr,sheet=None):
        if self.dirty: self.values={}; self.dirty=False
        try: return self._eval_cell(sheet or self.active,addr,set())
        except SheetError as ex:
            self.last_error_detail=ex.detail; return ex.code
    def _eval_cell(self,sheet,addr,path):
        c,r,*_=cellref(addr); addr=f'{colname(c)}{r}'; key=(sheet,addr)
        if key in self.values: return self.values[key]
        if key in path: raise SheetError('#CYCLE!', ' -> '.join(f'{s}.{a}' for s,a in [*path,key]))
        if sheet not in self.sheets: raise SheetError('#SHEET!')
        raw=self.get(addr,sheet).raw
        if not raw: return None
        if raw.startswith(('\'','^','"','\\')): return raw[1:]
        if raw.startswith(('=','+','@')):
            expr=raw[1:]
            if raw.startswith('@'): expr=raw[1:]
            try:
                result=self._node(Parser(expr).parse(),path|{key},sheet)
            except SheetError as e: result=e.code
            except (ValueError,IndexError,OverflowError,TypeError,ZeroDivisionError) as e:
                result='#DIV/0!' if isinstance(e,ZeroDivisionError) else '#VALUE!'
        else:
            try: result=float(raw.replace('_',''))
            except ValueError: result=raw
        self.values[key]=result
        return result
    def _node(self,n,path,sheet):
        typ=n[0]
        if typ=='literal': return n[1]
        if typ=='ref':
            sh=n[1] or sheet
            x=self._eval_cell(sh,n[2],path)
            if isinstance(x,str) and x.startswith('#'): raise SheetError(x)
            return x
        if typ=='range':
            sh=n[1] or sheet
            x1,y1,*_=cellref(n[2]); x2,y2,*_=cellref(n[3]); out=[]
            if (abs(x2-x1)+1)*(abs(y2-y1)+1)>100000: raise SheetError('#RANGE!','Range too large')
            for y in range(min(y1,y2),max(y1,y2)+1):
                row=[]
                for x in range(min(x1,x2),max(x1,x2)+1):
                    v=self._eval_cell(sh,f'{colname(x)}{y}',path)
                    if isinstance(v,str) and v.startswith('#'): raise SheetError(v)
                    row.append(v)
                out.append(row)
            return out
        if typ=='unary': return number(self._node(n[2],path,sheet)) * (-1 if n[1]=='-' else 1)
        if typ=='bin':
            a=self._node(n[2],path,sheet); b=self._node(n[3],path,sheet)
            op=n[1]
            if op=='&': return str(a if a is not None else '')+str(b if b is not None else '')
            if op in ('=','<>','!=','<','>','<=','>='):
                if op=='=': return a==b
                if op in ('<>','!='): return a!=b
                return {'<':lambda:a<b,'>':lambda:a>b,'<=':lambda:a<=b,'>=':lambda:a>=b}[op]()
            a=number(a); b=number(b)
            return {'+':lambda:a+b,'-':lambda:a-b,'*':lambda:a*b,'/':lambda:a/b,'^':lambda:a**b,'%':lambda:a%b}[op]()
        if typ=='call':
            name,args=n[1],n[2]
            # IF and logical operators short-circuit to avoid evaluating unused branches.
            if name=='IF':
                cond=self._node(args[0],path,sheet)
                index=1 if cond else 2
                return self._node(args[index],path,sheet) if index<len(args) else False
            if name=='AND':
                return all(bool(self._node(a,path,sheet)) for a in args)
            if name=='OR':
                return any(bool(self._node(a,path,sheet)) for a in args)
            return function(name,[self._node(a,path,sheet) for a in args])
        raise SheetError('#PARSE!')
    def save(self,path):
        obj={'format':'ses-0.1','active':self.active,'sheets':{
            name:{'cells':{k:vars(v) for k,v in sh.cells.items()},'column_widths':sh.column_widths,'row_heights':sh.row_heights} for name,sh in self.sheets.items()}}
        Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    @classmethod
    def load(cls,path):
        obj=json.loads(Path(path).read_text(encoding='utf-8'))
        if obj.get('format')!='ses-0.1': raise SheetError('#FILE!','Not a SES 0.1 document')
        b=cls(); b.sheets={}
        for name,data in obj['sheets'].items():
            # Backward compatible with a1-a7 files where the sheet value was directly the cells mapping.
            if 'cells' in data and isinstance(data.get('cells'),dict):
                cells=data.get('cells',{}); widths=data.get('column_widths',{}); heights=data.get('row_heights',{});
            else:
                cells=data; widths={}; heights={};
            loaded={}
            for k,v in cells.items():
                values=dict(v);
                if 'fg_explicit' not in values: values['fg_explicit']=values.get('fg',7)!=7
                if 'bg_explicit' not in values: values['bg_explicit']=values.get('bg',0)!=0
                loaded[k]=Cell(**values)
            b.sheets[name]=Sheet(loaded,dict(widths),dict(heights))
        b.active=obj['active']; return b
