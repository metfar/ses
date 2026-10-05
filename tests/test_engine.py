from pathlib import Path;
import pytest;
from ses.engine import Workbook, relocate_formula, FormulaError, Parser, call_function;
from ses.cli import build_app;
from sumtui import KeyEvent, Key;


def book_with_inputs():
    book=Workbook();
    for cell, raw in [('A1','10'), ('A2','20'), ('A3','30'), ('B1','4'), ('B2','6'), ('C1',"'Texto")]:
        book.set(cell,raw);
    return book;

@pytest.mark.parametrize('raw,dx,dy,expected',[
    ('=A11',2,0,'=C11'),('=A11',0,1,'=A12'),('=$A11',2,1,'=$A12'),
    ('=A$11',2,1,'=C$11'),('=$A$11',2,1,'=$A$11'),
    ('=SUM($A1:B$11)',2,1,'=SUM($A2:D$11)'),
    ('=SUM("A1";A1)',2,1,'=SUM("A1";C2)'),
    ('=SUM(A1)',-1,0,'=SUM(#REF!)'),
    ('=@IF(A1>0;1;0)',1,2,'=@IF(B3>0;1;0)')
])
def test_copy_transforms(raw,dx,dy,expected):
    assert relocate_formula(raw,dx,dy) == expected;

@pytest.mark.parametrize('raw,want',[
    ('=SUM(A1:A3)',60),('=AVG(A1:A3)',20),('=COUNT(A1:A3)',3),
    ('=SUMPRODUCT(A1:A2;B1:B2)',160),
    ('=SUMIF(A1:A3;">15";B1:B3)',6),
    ('=COUNTIF(A1:A3;">15")',2),
    ('=COUNTIFS(A1:A3;">15";A1:A3;"<=30")',2),
    ('=SUMIFS(B1:B3;A1:A3;">15")',6),
    ('=IF(1=1;"YES";1/0)',"YES"),
    ('=IF(FALSE;1/0;7)',7),
    ('=ROUND(2.345;2)',2.35),
    ('=ROUNDUP(-1.2;0)',-2),
    ('=ROUNDDOWN(-1.9;0)',-1),
    ('=CEIL(-1.2)',-1),
    ('=FLOOR(-1.2)',-2),
    ('=CONCAT(LEFT("ISABEL";3);RIGHT("ISABEL";3))','ISA BEL'.replace(' ','')),
    ('=MID("ISABEL";2;3)','SAB'),
    ('=FIND("AB";"ISABEL")',3),
    ('=LENGTH("ñandú")',5),
    ('=VALUE("25.5")+1',26.5),
    ('=1+2*3',7),('=2^3^2',512),('=A1&A2','1020'),
    ('@SUM(A1:A3)',60),('+SUM(A1:A3)',60)
])
def test_functions(raw,want):
    book=book_with_inputs();
    book.set('E1',raw);
    assert book.evaluate('E1') == want;

def test_circular_self_and_indirect():
    book=Workbook();
    book.set('A1','=A1+1');
    assert book.display('A1') == '#CYCLE!';
    book.set('A1','=B1');book.set('B1','=C1');book.set('C1','=A1');
    assert book.display('A1') == '#CYCLE!';
    assert book.display('B1') == '#CYCLE!';

def test_recalculation_and_undo_redo():
    book=Workbook();book.set('A1','5');book.set('B1','=A1+1');
    assert book.evaluate('B1') == 6;
    book.set('A1','7');assert book.evaluate('B1') == 8;
    assert book.undo();assert book.evaluate('B1') == 6;
    assert book.redo();assert book.evaluate('B1') == 8;

def test_multisheet_and_persist(tmp_path):
    book=Workbook();book.add_sheet('Sheet2');
    book.set('A1','55',sheet='Sheet2');
    book.set('A1','=Sheet2!A1+Sheet2.A1');
    assert book.evaluate('A1') == 110;
    target=tmp_path/'tienda.ses';book.save(target);
    copy=Workbook.load(target);
    assert copy.display('A1')=='110';
    assert not copy.dirty;

def test_bold_selection_as_transaction():
    book=Workbook();book.set_bold(['A1','A2','B1','B2']);
    assert all(book.cell(a).bold for a in ['A1','A2','B1','B2']);
    assert book.undo();
    assert not book.cell('B2').bold;

def test_block_copy():
    book=Workbook();book.set('A1','1');book.set('B1','=A1+2');
    book.copy('A1','A2',rows=1,cols=2);
    assert book.cell('B2').raw == '=A2+2';
    assert book.display('B2') == '3';
    assert book.undo();assert book.cell('B2').raw == '';

def test_formula_failures():
    book=Workbook();
    for raw, error in [('=1/0','#DIV/0!'),('=SUM(','#PARSE!'),('=NOPE(1)','#NAME?'),('=Z1/"Hi"','#VALUE!'),('=COUNTIF(A1:A2)','#VALUE!')]:
        book.set('D1',raw);
        assert book.display('D1') == error,raw;

def test_shared_tui_menu_and_keys():
    app=build_app(Workbook(),theme='DOS');
    view=app.root.body;
    assert len(app.root.menu.menus) == 6;
    assert view.handle_event(KeyEvent('x',text='x'));
    assert view.editing == 'x';
    assert view.handle_event(KeyEvent(Key.ENTER));
    assert view.book.cell('A1').raw == 'x';
    assert view.handle_event(KeyEvent('z',ctrl=True));
    assert view.book.cell('A1').raw == '';

def test_legacy_text_prefixes():
    book=Workbook();
    for addr, raw, align in [("A1","'123","left"),("A2","^Centered","center"),
                             ("A3",'"Right',"right"),("A4",r"\-","repeat")]:
        book.set(addr,raw);
        assert book.cell(addr).align == align;
    assert book.evaluate("A1") == "123";
    assert book.evaluate("A2") == "Centered";
    assert book.evaluate("A3") == "Right";
    assert book.evaluate("A4") == "-";

def test_non_evaluated_string_formula():
    book=Workbook();
    book.set("A1","'=SUM(1;2)");
    assert book.evaluate("A1") == "=SUM(1;2)";
