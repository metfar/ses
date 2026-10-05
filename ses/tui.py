"""Keyboard-first curses interface for SES. No dependency on graphical desktop."""
import argparse
import curses
import json
import os
import sys
from pathlib import Path
from .engine import Book, SheetError, cellref, colname

MENUS={
 'File':['New','Open','Save','Save as','Add sheet','Quit'],
 'Edit':['Undo','Redo','Copy','Cut','Paste','Fill down','Fill right','Insert row','Insert column','Select range'],
 'Style':['Bold','Underline','Foreground','Background','Align left','Align center','Align right','Grid lines','Theme'],
 'Data':['Recalculate','Go to cell'],
 'Tools':['Command line','Show formula'],
 'Help':['Keys','Functions','About']}
HELP=[
 'SES 0.1.0a3 - terminal spreadsheet',
 'F2 or click formula bar: edit; typing replaces; Tab in edit: pick range',
 'Ctrl+C copy  Ctrl+X cut  Ctrl+V paste  Ctrl+B bold  Ctrl+U underline',
 'Ctrl+Z undo  Ctrl+Y redo  F1 help  F5 goto  F6 next sheet',
 'Shift+arrows selects cells (if terminal supports shifted keys)',
 'Click column/row heading: select full column/row',
 'Shift+click header: extend selection; Ctrl+click: add disjoint range',
 'Mouse modifier reporting depends on your terminal emulator',
 'Menu Style: foreground/background, underlining, DOS grid borders',
 ':copy A1:B3 D5   :cut A1:B3 D5   :fill down A1:A9',
 ':row 4  :col C  :grid  :fg 3  :bg 1  :underline',
 'Formula: =SUM(A1:B4), @AVG(A1:A10), =COUNTIF(A1:A10;">5")',
 'Open/Save dialogs: sumTUI; --theme DOS; --demo; ses file.ses']

# Only SES preferences live here. Theme definitions stay in sumTUI/sumtheme.
def preference_path():
    base=Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')));
    return base/'sumtui'/'ses.json';


def load_preferences(path=None):
    target=Path(path) if path else preference_path();
    try:
        data=json.loads(target.read_text(encoding='utf-8'));
        if not isinstance(data,dict): return {};
        return {k:data[k] for k in ('theme','grid','last_dir') if k in data};
    except (FileNotFoundError,ValueError,OSError):
        return {};


def save_preferences(data,path=None):
    target=Path(path) if path else preference_path();
    target.parent.mkdir(parents=True,exist_ok=True);
    import tempfile;
    import os as _os;
    fd,tmp=tempfile.mkstemp(prefix='.ses-',dir=str(target.parent));
    try:
        with _os.fdopen(fd,'w',encoding='utf-8') as out:
            json.dump(data,out,ensure_ascii=False,indent=2);
            out.write('\n');
        _os.replace(tmp,target);
    finally:
        if _os.path.exists(tmp): _os.unlink(tmp);


def sample_book():
    book=Book();
    for addr,value in {'A1':"'Item",'B1':"'Price",'A2':"'Tea",'B2':'120',
                       'A3':"'Coffee",'B3':'175','A4':"'Total",'B4':'=SUM(B2:B3)'}.items():
        book.put(addr,value);
    return book;


def theme_palette(name):
    from sumtui.theme import make_theme, available_theme_names;
    names=available_theme_names(include_hidden=True);
    aliases={'spectrum':'ZX','pc':'DOS','turbo':'DOS','commodore':'C64','sumx':'XBASE'};
    resolved=aliases.get(name.lower(),name);
    if resolved.casefold() not in [n.casefold() for n in names] and resolved.upper() not in ('DOS','ZX','XBASE','C64','LIGHT','DARK'):
        raise ValueError('Unknown theme: '+name+' (try --list-themes)');
    return make_theme(resolved);


def xterm_index(rgb,colors):
    if colors<256:
        # ANSI basic colors ordered by ncurses indices.
        palette=[(0,0,0),(190,0,0),(0,170,0),(170,85,0),
                 (0,0,170),(170,0,170),(0,170,170),(210,210,210)];
        return min(range(min(colors,8)),key=lambda n:sum((a-b)**2 for a,b in zip(rgb,palette[n])));
    levels=[0,95,135,175,215,255];
    choices=[(16+36*r+6*g+b,(levels[r],levels[g],levels[b])) for r in range(6) for g in range(6) for b in range(6)];
    choices.extend((232+i,(8+10*i,)*3) for i in range(24));
    return min(choices,key=lambda item:sum((a-b)**2 for a,b in zip(rgb,item[1])))[0];

class App:
    def __init__(self,win,book=None,filename=None,theme='DOS',grid=False,preferences=None):
        self.win=win; self.book=book if book is not None else Book(); self.cx=1; self.cy=1
        self.scrollx=1; self.scrolly=1; self.anchor=None; self.extra=[]
        self.mode='cell'; self.grid=bool(grid); self.clipboard=None
        self.message='READY'; self.file=str(filename) if filename else None; self.running=True
        self.theme_name=theme; self.preferences=preferences or {}; self.theme=None; self.theme_pairs={}
        self.menu_names=list(MENUS); self.mouse_anchor=None
        self.colors=False
        try:
            curses.start_color(); curses.use_default_colors()
            for bg in range(8):
                for fg in range(8):
                    curses.init_pair(1+bg*8+fg,fg,bg)
            self.colors=True
        except (curses.error,ValueError): pass
        self.apply_theme(theme)
        try: curses.curs_set(0)
        except curses.error: pass
        curses.mousemask(curses.ALL_MOUSE_EVENTS|curses.REPORT_MOUSE_POSITION)
        win.keypad(True); win.timeout(-1)

    def apply_theme(self,name):
        self.theme=theme_palette(str(name)); self.theme_name=self.theme.name;
        self.theme_pairs={};
        if not self.colors: return;
        roles={'menu':('text','panel'),'formula':('command_text','command_bg'),
               'headers':('text','panel'),'body':('viewer_text','viewer_bg'),
               'status':('text','panel'),'selection':('selection_text','selection_bg')};
        for number,(role,(fore,back)) in enumerate(roles.items(),65):
            if number>=curses.COLOR_PAIRS: break;
            f=xterm_index(getattr(self.theme,fore),curses.COLORS);
            b=xterm_index(getattr(self.theme,back),curses.COLORS);
            try:
                curses.init_pair(number,f,b);
                self.theme_pairs[role]=curses.color_pair(number);
            except curses.error: pass;

    def shade(self,role):
        return self.theme_pairs.get(role,0);

    def pref_snapshot(self):
        return {'theme':self.theme_name,'grid':self.grid,
                'last_dir':str(Path(self.file).expanduser().resolve().parent) if self.file else self.preferences.get('last_dir',str(Path.cwd()))};

    def persist(self):
        try: save_preferences(self.pref_snapshot());
        except OSError as exc: self.message=f'Preferences not saved: {exc}';

    def shared_dialog(self,kind,path='.',title='Open SES'):
        # sumTUI has its own event loop; suspend curses to prevent two screen owners.
        from sumtui.dialogs import choose_file,read_entry;
        curses.def_prog_mode(); curses.endwin();
        try:
            if kind=='open': return choose_file(path=path,title=title,theme=self.theme_name);
            return read_entry(text='File name or full path',default=path,title=title,theme=self.theme_name);
        finally:
            curses.reset_prog_mode();
            self.win.clear(); self.win.refresh();

    def open_dialog(self):
        path=self.preferences.get('last_dir',str(Path.cwd()));
        result=self.shared_dialog('open',path,title='SES - Open');
        if result.accepted and str(result.value).strip():
            self.command('open '+str(result.value));

    def save_as_dialog(self):
        suggestion=self.file or str(Path(self.preferences.get('last_dir',str(Path.cwd())))/'book.ses');
        result=self.shared_dialog('entry',suggestion,title='SES - Save as (full path)');
        if result.accepted and str(result.value).strip():
            target=Path(str(result.value)).expanduser();
            if target.exists():
                from sumtui.dialogs import ask_question;
                curses.def_prog_mode(); curses.endwin();
                try: answer=ask_question(f'Overwrite {target.name}?',theme=self.theme_name);
                finally: curses.reset_prog_mode(); self.win.clear(); self.win.refresh();
                if not answer.accepted: return;
            self.command('save '+str(target));

    def addr(self): return f'{colname(self.cx)}{self.cy}'
    def limits(self):
        h,w=self.win.getmaxyx()
        return h,w,max(1,(w-5)//12),max(1,(h-6)//(2 if self.grid else 1))
    def rects(self):
        if self.anchor is None: base=(self.cx,self.cy,self.cx,self.cy)
        else:
            x,y=self.anchor
            if self.mode=='row': base=(1,min(y,self.cy),256,max(y,self.cy))
            elif self.mode=='col': base=(min(x,self.cx),1,max(x,self.cx),8192)
            else: base=(min(x,self.cx),min(y,self.cy),max(x,self.cx),max(y,self.cy))
        return [*self.extra,base]
    def contains(self,x,y):
        return any(x1<=x<=x2 and y1<=y<=y2 for x1,y1,x2,y2 in self.rects())
    def selected(self):
        out=[]; seen=set()
        for x1,y1,x2,y2 in self.rects():
            cells=(x2-x1+1)*(y2-y1+1)
            if cells>50000: raise SheetError('#RANGE!','Select fewer than 50,000 cells for this command')
            for y in range(y1,y2+1):
                for x in range(x1,x2+1):
                    addr=f'{colname(x)}{y}'
                    if addr not in seen: out.append(addr); seen.add(addr)
        return out
    def range_spec(self):
        r=self.rects()[-1]; a,b,c,d=r
        return f'{colname(a)}{b}:{colname(c)}{d}'
    def adjust(self):
        _,_,cols,rows=self.limits()
        if self.cx<self.scrollx: self.scrollx=self.cx
        if self.cx>=self.scrollx+cols: self.scrollx=self.cx-cols+1
        if self.cy<self.scrolly: self.scrolly=self.cy
        if self.cy>=self.scrolly+rows: self.scrolly=self.cy-rows+1
    def put(self,y,x,s,attr=0):
        h,w=self.win.getmaxyx()
        if y<0 or x<0 or y>=h or x>=w: return
        try: self.win.addnstr(y,x,str(s),max(0,w-x-1),attr)
        except curses.error: pass
    def draw(self):
        self.adjust(); self.win.erase(); h,w,cols,rows=self.limits()
        self.put(0,0,'  '.join(self.menu_names),self.shade('menu')|curses.A_BOLD)
        self.put(1,0,f'{self.book.active}  {self.addr()}: {self.book.get(self.addr()).raw}',self.shade('formula')|curses.A_BOLD)
        self.put(2,0,'    '+''.join(f'{colname(x):^12}' for x in range(self.scrollx,self.scrollx+cols)),self.shade('headers')|curses.A_BOLD)
        for idx in range(rows):
            yy=3+idx*(2 if self.grid else 1); row=self.scrolly+idx
            row_selected=self.mode=='row' and self.contains(self.cx,row)
            self.put(yy,0,f'{row:>4}',self.shade('headers')|(curses.A_BOLD if row_selected else 0))
            for j in range(cols):
                col=self.scrollx+j; key=f'{colname(col)}{row}'
                cell=self.book.get(key); val=self.book.evaluate(key)
                s='' if val is None else (format(val,'.11g') if isinstance(val,float) else str(val))
                if cell.align=='repeat' and s: s=s*((12//len(s))+1)
                s=s[:12]
                if cell.align=='center': s=s.center(12)
                elif cell.align=='right' or (cell.align=='general' and isinstance(val,(int,float))): s=s.rjust(12)
                else: s=s.ljust(12)
                attr=self.shade('body')|(curses.A_BOLD if cell.bold else 0)|(curses.A_UNDERLINE if cell.underline else 0)
                if self.colors and (cell.fg!=7 or cell.bg!=0): attr=curses.color_pair(1+int(cell.bg)%8*8+int(cell.fg)%8)|(attr & (curses.A_BOLD|curses.A_UNDERLINE))
                if self.contains(col,row): attr|=curses.A_REVERSE
                if col==self.cx and row==self.cy: attr|=curses.A_BOLD|curses.A_UNDERLINE
                self.put(yy,4+12*j,s,attr)
                if self.grid:
                    self.put(yy,4+12*j+11,'│',curses.A_DIM)
            if self.grid and idx<rows-1:
                self.put(yy+1,4,('───────────┼'*cols)[:max(0,w-5)],curses.A_DIM)
        if self.grid:
            # One-line separators in the existing cell width; no layout/scroll changes.
            self.put(2,4,'┼'+''.join('───────────┼' for _ in range(cols))[:max(0,w-6)],curses.A_REVERSE)
            self.put(2,4,''.join(f'{colname(x):^11}│' for x in range(self.scrollx,self.scrollx+cols))[:w-5],curses.A_REVERSE)
        self.put(h-2,0,'─'*(w-1),curses.A_DIM)
        amount=sum((c-a+1)*(d-b+1) for a,b,c,d in self.rects())
        self.put(h-1,0,f'{self.book.active} | {self.addr()} | {amount} selected | {self.message}',self.shade('status'))
        self.win.refresh()
    def prompt(self,title,default=''):
        h,w=self.win.getmaxyx(); self.put(h-1,0,' '*(w-1),curses.A_REVERSE)
        self.put(h-1,0,title+default,curses.A_REVERSE)
        curses.echo()
        try: curses.curs_set(1)
        except curses.error: pass
        try:
            result=self.win.getstr(h-1,min(w-2,len(title)),max(1,w-len(title)-2))
            return result.decode('utf-8') or default
        finally:
            curses.noecho()
            try: curses.curs_set(0)
            except curses.error: pass
    def modal(self,lines):
        self.draw(); h,w=self.win.getmaxyx()
        top=max(1,(h-min(h-2,len(lines)+3))//2)
        width=min(w-2,max(32,max(map(len,lines))+3))
        for i,s in enumerate(lines[:max(0,h-top-2)]):
            self.put(top+i,1,s.ljust(width-2),curses.A_REVERSE)
        self.put(min(h-1,top+len(lines)),1,'Any key closes',curses.A_BOLD)
        self.win.refresh(); self.win.getch()
    def edit(self,replace=False,initial=''):
        addr=self.addr(); original=self.book.get(addr).raw
        value=initial if replace else original; pos=len(value)
        pick=False; old_cursor=(self.cx,self.cy)
        try:
            while True:
                self.draw(); h,w=self.win.getmaxyx()
                if pick:
                    self.put(h-1,0,('PICK '+self.range_spec()+'  Enter: insert; Esc: cancel').ljust(w-1),curses.A_REVERSE)
                    try: curses.curs_set(0)
                    except curses.error: pass
                else:
                    # Edit in formula bar, with a real visible cursor on the current character.
                    prefix=f'{self.addr()} ▸ '
                    usable=max(1,w-len(prefix)-2)
                    offset=max(0,pos-usable+1)
                    self.put(1,0,' '*(w-1),curses.A_REVERSE)
                    self.put(1,0,prefix+value[offset:offset+usable],curses.A_REVERSE|curses.A_UNDERLINE)
                    self.put(h-1,0,'EDIT: Enter confirms / Esc cancels / Tab selects range'.ljust(w-1),curses.A_REVERSE)
                    try: curses.curs_set(1)
                    except curses.error: pass
                    try: self.win.move(1,min(w-2,len(prefix)+pos-offset))
                    except curses.error: pass
                self.win.refresh(); k=self.win.getch()
                if pick:
                    if k in (10,13,curses.KEY_ENTER):
                        rect=self.rects()[-1]
                        x1,y1,x2,y2=rect
                        ref=f'{colname(x1)}{y1}'
                        if (x1,y1)!=(x2,y2): ref+=f':{colname(x2)}{y2}'
                        value=value[:pos]+ref+value[pos:]; pos+=len(ref)
                        pick=False; self.anchor=None; self.extra=[]; self.mode='cell'
                    elif k==27:
                        pick=False; self.anchor=None; self.mode='cell'
                    elif k==curses.KEY_MOUSE: self.mouse(allow_edit=False)
                    else: self.navigation(k)
                    continue
                if k in (10,13,curses.KEY_ENTER):
                    self.book.put(addr,value); self.message='Cell updated'; return
                if k==27: self.message='Edit cancelled'; return
                if k==9:
                    pick=True; self.mode='cell'; self.anchor=None; continue
                if k in (curses.KEY_BACKSPACE,127,8):
                    if pos: value=value[:pos-1]+value[pos:]; pos-=1
                elif k==curses.KEY_DC: value=value[:pos]+value[pos+1:]
                elif k==curses.KEY_LEFT: pos=max(0,pos-1)
                elif k==curses.KEY_RIGHT: pos=min(len(value),pos+1)
                elif k==curses.KEY_HOME: pos=0
                elif k==curses.KEY_END: pos=len(value)
                elif 32<=k<=0x10ffff:
                    try:
                        ch=chr(k); value=value[:pos]+ch+value[pos:]; pos+=1
                    except ValueError: pass
        finally:
            self.cx,self.cy=old_cursor
            try: curses.curs_set(0)
            except curses.error: pass
    def navigation(self,k):
        dx=dy=0; extend=False
        shifted={getattr(curses,'KEY_SLEFT',-99):(-1,0),getattr(curses,'KEY_SRIGHT',-98):(1,0),
                 getattr(curses,'KEY_SUP',-97):(0,-1),getattr(curses,'KEY_SDOWN',-96):(0,1)}
        if k in shifted: dx,dy=shifted[k]; extend=True
        elif k==curses.KEY_LEFT: dx=-1
        elif k==curses.KEY_RIGHT: dx=1
        elif k==curses.KEY_UP: dy=-1
        elif k==curses.KEY_DOWN: dy=1
        elif k==curses.KEY_NPAGE: dy=10
        elif k==curses.KEY_PPAGE: dy=-10
        else: return False
        if extend:
            if self.anchor is None: self.anchor=(self.cx,self.cy)
        else: self.anchor=None; self.extra=[]; self.mode='cell'
        self.cx=max(1,self.cx+dx); self.cy=max(1,self.cy+dy)
        return True
    def mouse(self,allow_edit=True):
        try: _,x,y,_,state=curses.getmouse()
        except curses.error: return
        h,w,cols,rows=self.limits()
        clickmask=(getattr(curses,'BUTTON1_CLICKED',0)|getattr(curses,'BUTTON1_PRESSED',0)
                   |getattr(curses,'BUTTON1_DOUBLE_CLICKED',0)|getattr(curses,'BUTTON1_RELEASED',0))
        if not state&clickmask: return
        shift=bool(state&getattr(curses,'BUTTON_SHIFT',0)); control=bool(state&getattr(curses,'BUTTON_CTRL',0))
        if y==1:
            if allow_edit: self.edit()
            return
        if y==2 and x>=4:
            col=self.scrollx+(x-4)//12; row=self.cy; mode='col'
        elif 3<=y<3+rows*(2 if self.grid else 1) and ((y-3)%(2 if self.grid else 1))==0 and x<4:
            col=self.cx; row=self.scrolly+(y-3)//(2 if self.grid else 1); mode='row'
        elif 3<=y<3+rows*(2 if self.grid else 1) and ((y-3)%(2 if self.grid else 1))==0 and 4<=x<4+cols*12:
            col=self.scrollx+(x-4)//12; row=self.scrolly+(y-3)//(2 if self.grid else 1); mode='cell'
        else: return
        if control:
            self.extra=self.rects(); self.anchor=None
        elif not shift:
            self.extra=[]; self.anchor=None
        if shift and self.anchor is None: self.anchor=(self.cx,self.cy)
        self.mode=mode; self.cx=col; self.cy=row
        if mode!='cell' and self.anchor is None: self.anchor=(col,row)
        if allow_edit and state&getattr(curses,'BUTTON1_DOUBLE_CLICKED',0) and mode=='cell': self.edit()
    def clipboard_copy(self,cut=False):
        rects=self.rects()
        if len(rects)!=1: raise SheetError('#RANGE!','Copy one rectangular selection at a time')
        a,b,c,d=rects[0]
        if (c-a+1)*(d-b+1)>50000: raise SheetError('#RANGE!')
        # Clipboard is an internal reference snapshot; pasted cells copy from this snapshot.
        import copy
        from .engine import Cell
        data={(x-a,y-b):copy.deepcopy(self.book.get(f'{colname(x)}{y}'))
              for y in range(b,d+1) for x in range(a,c+1)}
        self.clipboard=(a,b,data,cut)
        self.message=('Cut' if cut else 'Copied')+f' {colname(a)}{b}:{colname(c)}{d}'
    def paste(self):
        import copy
        from .engine import transform_formula,Cell
        if not self.clipboard: self.message='Clipboard empty'; return
        sx,sy,data,cut=self.clipboard; dx,dy=self.cx,self.cy
        def apply():
            cells=self.book.sheets[self.book.active].cells
            if cut:
                for ox,oy in data: cells.pop(f'{colname(sx+ox)}{sy+oy}',None)
            for (ox,oy),source in data.items():
                c=copy.deepcopy(source)
                if c.raw.startswith(('=','+','@')) and not cut:
                    c.raw=c.raw[:1]+transform_formula(c.raw[1:],dx-sx,dy-sy)
                addr=f'{colname(dx+ox)}{dy+oy}'
                if c==Cell(): cells.pop(addr,None)
                else: cells[addr]=c
        self.book.change(apply)
        if cut: self.clipboard=None
        self.message='Pasted'
    def command(self,line):
        parts=line.strip().split(); cmd=parts[0].lower() if parts else ''
        try:
            if cmd=='save':
                target=line.strip()[len(parts[0]):].strip() or self.file
                if not target: self.save_as_dialog(); return
                self.book.save(Path(target).expanduser()); self.file=str(Path(target).expanduser()); self.message=f'Saved {self.file}'; self.persist()
            elif cmd=='open':
                target=line.strip()[len(parts[0]):].strip()
                if not target: self.open_dialog(); return
                candidate=Book.load(Path(target).expanduser()); self.book=candidate; self.file=str(Path(target).expanduser()); self.message=f'Opened {self.file}'; self.persist()
            elif cmd=='sheet': self.book.add_sheet(' '.join(parts[1:])); self.message='Sheet added'
            elif cmd=='goto': self.cx,self.cy,*_=cellref(parts[1]); self.mode='cell'; self.anchor=None; self.extra=[]
            elif cmd=='select':
                a,b=parts[1].split(':'); self.cx,self.cy,*_=cellref(b); self.anchor=cellref(a)[:2]; self.mode='cell'; self.extra=[]
            elif cmd=='copy' and len(parts)>=3: self.book.copy_block(parts[1],parts[2]); self.message='Block copied'
            elif cmd=='cut' and len(parts)>=3: self.book.copy_block(parts[1],parts[2],move=True); self.message='Block moved'
            elif cmd=='copy': self.clipboard_copy()
            elif cmd=='cut': self.clipboard_copy(cut=True)
            elif cmd=='paste': self.paste()
            elif cmd=='bold': self.book.toggle_bold(self.selected()); self.message='Bold toggled'
            elif cmd=='underline': self.book.style(self.selected(),'underline'); self.message='Underline toggled'
            elif cmd in ('fg','bg'):
                color=int(parts[1]);
                if color not in range(8): raise ValueError('Color number must be 0..7')
                self.book.style(self.selected(),cmd,color); self.message=f'{cmd.upper()} set to {color}'
            elif cmd=='align': self.book.style(self.selected(),'align',parts[1].lower()); self.message='Alignment changed'
            elif cmd=='grid': self.grid=not self.grid; self.message='Grid '+('on' if self.grid else 'off'); self.persist()
            elif cmd=='theme': self.apply_theme(parts[1]); self.message='Theme '+self.theme_name; self.persist()
            elif cmd=='row': self.book.insert('row',int(parts[1])); self.message='Row inserted'
            elif cmd=='col':
                spec=parts[1].upper(); x=cellref(spec+'1')[0] if spec.isalpha() else int(spec)
                self.book.insert('col',x); self.message='Column inserted'
            elif cmd=='fill': self.book.fill(parts[2] if len(parts)>2 else self.range_spec(),parts[1].lower()); self.message='Range filled'
            elif cmd=='undo': self.book.undo()
            elif cmd=='redo': self.book.redo()
            elif cmd=='help': self.modal(HELP)
            elif cmd=='quit': self.persist(); self.running=False
            elif cmd: self.message=f'Unknown command: {cmd}'
        except (SheetError,ValueError,IndexError,KeyError,OSError) as e:
            self.message=f'ERROR {e}'
    def show_menu(self):
        idx=sub=0
        while True:
            self.draw(); h,w=self.win.getmaxyx()
            x=sum(len(n)+2 for n in self.menu_names[:idx]); options=MENUS[self.menu_names[idx]]
            for i,n in enumerate(self.menu_names):
                xx=sum(len(k)+2 for k in self.menu_names[:i]); self.put(0,xx,n,curses.A_REVERSE|curses.A_BOLD if i==idx else 0)
            x=max(0,min(w-25,x))
            for i,opt in enumerate(options):
                self.put(3+i,x,(' '+opt.ljust(21)+' ')[:max(0,w-x-1)],curses.A_REVERSE if i==sub else 0)
            self.win.refresh(); k=self.win.getch()
            if k==27: return
            if k==curses.KEY_LEFT: idx=(idx-1)%len(self.menu_names); sub=0
            elif k==curses.KEY_RIGHT: idx=(idx+1)%len(self.menu_names); sub=0
            elif k==curses.KEY_UP: sub=(sub-1)%len(options)
            elif k==curses.KEY_DOWN: sub=(sub+1)%len(options)
            elif k in (10,13,curses.KEY_ENTER):
                action=options[sub]
                if action=='New': self.book=Book(); self.file=None; self.message='New workbook'
                elif action=='Open': self.open_dialog()
                elif action=='Save': self.command('save')
                elif action=='Save as': self.save_as_dialog()
                elif action=='Add sheet': self.command('sheet '+self.prompt('Name: '))
                elif action=='Quit': self.persist(); self.running=False
                elif action=='Undo': self.command('undo')
                elif action=='Redo': self.command('redo')
                elif action=='Copy': self.command('copy')
                elif action=='Cut': self.command('cut')
                elif action=='Paste': self.command('paste')
                elif action=='Fill down': self.command('fill down')
                elif action=='Fill right': self.command('fill right')
                elif action=='Insert row': self.command(f'row {self.cy}')
                elif action=='Insert column': self.command(f'col {colname(self.cx)}')
                elif action=='Select range': self.command('select '+self.prompt('Range: '))
                elif action=='Bold': self.command('bold')
                elif action=='Underline': self.command('underline')
                elif action=='Foreground': self.command('fg '+self.prompt('FG 0..7: '))
                elif action=='Background': self.command('bg '+self.prompt('BG 0..7: '))
                elif action.startswith('Align '): self.command('align '+action[6:].lower())
                elif action=='Grid lines': self.command('grid')
                elif action=='Theme':
                    from sumtui.theme import available_theme_names
                    from sumtui.dialogs import choose_list
                    curses.def_prog_mode(); curses.endwin()
                    try: result=choose_list(available_theme_names(),title='SES theme',theme=self.theme_name)
                    finally: curses.reset_prog_mode(); self.win.clear(); self.win.refresh()
                    if result.accepted: self.command('theme '+str(result.value))
                elif action=='Recalculate': self.book.dirty=True; self.message='Recalculated'
                elif action=='Go to cell': self.command('goto '+self.prompt('Cell: '))
                elif action=='Command line': self.command(self.prompt(':'))
                elif action=='Show formula': self.message=self.book.get(self.addr()).raw
                elif action=='Keys': self.modal(HELP)
                elif action=='Functions': self.modal(['SUM AVG COUNT SUMPRODUCT COUNTIF SUMIF COUNTIFS SUMIFS',
                        'IF AND OR NOT ABS ROUND ROUNDUP ROUNDDOWN CEIL FLOOR',
                        'VALUE CONCAT STRING LEFT RIGHT MID FIND LENGTH',
                        'INDEX CHOOSE VLOOKUP HLOOKUP SQRT MOD UPPER LOWER'])
                elif action=='About': self.modal(['SES 0.1.0a3 - alpha','GNU GPL-3.0-or-later'])
                return
    def run(self):
        while self.running:
            self.draw(); k=self.win.getch()
            if k==curses.KEY_MOUSE: self.mouse()
            elif self.navigation(k): pass
            elif k==curses.KEY_F1: self.modal(HELP)
            elif k==curses.KEY_F2: self.edit()
            elif k==curses.KEY_F5: self.command('goto '+self.prompt('Cell: '))
            elif k==curses.KEY_F6:
                names=list(self.book.sheets); self.book.active=names[(names.index(self.book.active)+1)%len(names)]; self.book.dirty=True
            elif k==curses.KEY_F9: self.book.dirty=True; self.message='Recalculated'
            elif k in (curses.KEY_F10,27): self.show_menu()
            elif k==26: self.command('undo')
            elif k==25: self.command('redo')
            elif k==2: self.command('bold')
            elif k==21: self.command('underline')
            elif k==3: self.command('copy')
            elif k==24: self.command('cut')
            elif k==22: self.command('paste')
            elif k==ord(':'): self.command(self.prompt(':'))
            elif k in (10,13): self.edit()
            elif 32<=k<=126: self.edit(replace=True,initial=chr(k))

def argument_parser():
    parser=argparse.ArgumentParser(prog='ses',description='SES - sumEditSpreadsheet');
    parser.add_argument('file',nargs='?',help='existing .ses workbook to open');
    parser.add_argument('--theme',help='sumTUI theme, e.g. DOS, ZX, XBASE, Light');
    parser.add_argument('--list-themes',action='store_true',help='list available sumTUI themes');
    parser.add_argument('--demo',action='store_true',help='open example sheet');
    flags=parser.add_mutually_exclusive_group();
    flags.add_argument('--grid',action='store_true',help='show DOS gridlines');
    flags.add_argument('--no-grid',action='store_true',help='hide DOS gridlines');
    parser.add_argument('--version',action='version',version='SES 0.1.0a3');
    return parser;


def main(argv=None):
    parser=argument_parser(); args=parser.parse_args(argv);
    if args.list_themes:
        from sumtui.theme import available_theme_names;
        print('\n'.join(available_theme_names())); return 0;
    if args.demo and args.file: parser.error('choose either FILE or --demo');
    pref=load_preferences(); theme=args.theme or pref.get('theme','DOS');
    try: theme_palette(theme);
    except (ValueError,ImportError) as error: parser.error(str(error));
    grid=True if args.grid else (False if args.no_grid else bool(pref.get('grid',False)));
    if args.file:
        try: book=Book.load(Path(args.file).expanduser());
        except (OSError,ValueError,KeyError,TypeError,SheetError) as exc:
            parser.exit(2,f'ses: cannot open {args.file}: {exc}\n');
    else: book=sample_book() if args.demo else Book();
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.exit(2,'ses: interactive terminal required\n');
    def run(win):
        app=App(win,book=book,filename=args.file,theme=theme,grid=grid,preferences=pref);
        try: app.run();
        finally: app.persist();
    curses.wrapper(run);
    return 0

if __name__=='__main__': main()
