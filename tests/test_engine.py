import tempfile
import unittest
from pathlib import Path
from ses.engine import Book, Parser, SheetError, transform_formula, function

class EngineTests(unittest.TestCase):
    def test_basic(self):
        b=Book(); b.put('A1','2'); b.put('A2','3'); b.put('B1','=SUM(A1:A2)')
        self.assertEqual(b.evaluate('B1'),5)
        b.put('B2','@AVG(A1:A2)'); self.assertEqual(b.evaluate('B2'),2.5)
        b.put('C1','+SUM(A1;A2)'); self.assertEqual(b.evaluate('C1'),5)
    def test_relative_absolute(self):
        self.assertEqual(transform_formula('=A11+$A11+A$11+$A$11',2,1),'=C12+$A12+C$11+$A$11')
        self.assertEqual(transform_formula('SUM(A1:B2)+"A1"',2,3),'SUM(C4:D5)+"A1"')
    def test_copy(self):
        b=Book(); b.put('A1','5'); b.put('B1','=A1'); b.copy_cell('B1','C1')
        self.assertEqual(b.get('C1').raw,'=B1')
    def test_cycle(self):
        b=Book(); b.put('A1','=B1'); b.put('B1','=A1'); self.assertEqual(b.evaluate('A1'),'#CYCLE!')
    def test_errors(self):
        b=Book(); b.put('A1','=1/0'); self.assertEqual(b.evaluate('A1'),'#DIV/0!')
        b.put('A2','=MYSTERY(1)'); self.assertEqual(b.evaluate('A2'),'#NAME?')
        b.put('A3','=SUM('); self.assertEqual(b.evaluate('A3'),'#PARSE!')
    def test_if_lazy(self):
        b=Book(); b.put('A1','=IF(1=1;"ok";1/0)'); self.assertEqual(b.evaluate('A1'),'ok')
    def test_countif(self):
        b=Book()
        for r,val in enumerate(['Ana','Luis','Ana'],1): b.put(f'A{r}',"'"+val)
        for r,val in enumerate([8,10,12],1): b.put(f'B{r}',str(val))
        b.put('C1','=COUNTIF(A1:A3;"Ana")'); self.assertEqual(b.evaluate('C1'),2)
        b.put('C2','=SUMIF(A1:A3;"Ana";B1:B3)'); self.assertEqual(b.evaluate('C2'),20)
        b.put('C3','=COUNTIF(B1:B3;">9")'); self.assertEqual(b.evaluate('C3'),2)
    def test_text(self):
        b=Book(); b.put('A1','=LEFT("ISABEL";3)'); b.put('A2','=MID("ISABEL";2;3)'); b.put('A3','=FIND("SA";"ISABEL")')
        self.assertEqual([b.evaluate(f'A{i}') for i in (1,2,3)],['ISA','SAB',2])
    def test_rounding(self):
        self.assertEqual(function('ROUND',[2.5]),2)
        self.assertEqual(function('ROUNDUP',[-1.2]),-2)
        self.assertEqual(function('ROUNDDOWN',[-1.2]),-1)
        self.assertEqual(function('CEIL',[-1.2]),-1)
        self.assertEqual(function('FLOOR',[-1.2]),-2)
    def test_sheets(self):
        b=Book(); b.add_sheet('Pagos'); b.put('A1','5'); b.active='Sheet1'; b.put('A1','=Pagos!A1*2')
        self.assertEqual(b.evaluate('A1'),10)
    def test_undo_save(self):
        b=Book(); b.put('A1','7'); b.put('A1','8'); b.undo(); self.assertEqual(b.evaluate('A1'),7)
        b.redo(); self.assertEqual(b.evaluate('A1'),8)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'book.ses'; b.save(p); c=Book.load(p); self.assertEqual(c.evaluate('A1'),8)
    def test_sumproduct(self):
        b=Book();
        for i in (1,2,3): b.put(f'A{i}',str(i)); b.put(f'B{i}',str(i+1))
        b.put('C1','=SUMPRODUCT(A1:A3;B1:B3)'); self.assertEqual(b.evaluate('C1'),20)

if __name__=='__main__': unittest.main()
