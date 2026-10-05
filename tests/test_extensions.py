import tempfile
import unittest
from pathlib import Path
from ses.engine import Book,SheetError
from ses.tui import App

class ExtensionTests(unittest.TestCase):
    def test_styles_and_undo(self):
        b=Book(); b.put('A1',"'Texto"); b.style(['A1','B1'],'underline'); b.style(['A1'],'fg',3); b.style(['A1'],'bg',4)
        self.assertTrue(b.get('A1').underline); self.assertEqual((b.get('A1').fg,b.get('A1').bg),(3,4))
        b.undo(); self.assertEqual(b.get('A1').bg,0)
        with tempfile.TemporaryDirectory() as d:
            file=Path(d)/'test.ses'; b.save(file); loaded=Book.load(file)
            self.assertTrue(loaded.get('A1').underline); self.assertEqual(loaded.get('A1').fg,3)
    def test_copy_block_mixed_refs(self):
        b=Book(); b.put('B2','=A1+$A1+A$1+$A$1'); b.put('C2','5')
        b.copy_block('B2:C2','D4')
        self.assertEqual(b.get('D4').raw,'=C3+$A3+C$1+$A$1')
        self.assertEqual(b.get('E4').raw,'5'); b.undo()
        self.assertEqual(b.get('D4').raw,''); self.assertEqual(b.get('E4').raw,'')
    def test_fill(self):
        b=Book(); b.put('B1','=A1'); b.fill('B1:B3','down')
        self.assertEqual([b.get(f'B{r}').raw for r in range(1,4)],['=A1','=A2','=A3'])
        b.put('C1','=A$1'); b.fill('C1:E1','right')
        self.assertEqual([b.get(f'{c}1').raw for c in 'CDE'],['=A$1','=B$1','=C$1'])
    def test_insert_updates_other_sheet_only_on_target(self):
        b=Book(); b.put('A2','5'); b.put('B1','=A2+$A$2+"A2"'); b.add_sheet('Pagos')
        b.put('A1','=Sheet1!A2+Pagos!B2'); b.put('B2','3'); b.active='Sheet1'
        b.insert('row',2)
        self.assertEqual(b.get('A3').raw,'5')
        self.assertEqual(b.get('B1').raw,'=A3+$A$3+"A2"')
        self.assertEqual(b.get('A1','Pagos').raw,'=Sheet1!A3+Pagos!B2')
        self.assertEqual(b.evaluate('A1','Pagos'),8)
        b.undo(); self.assertEqual(b.get('A2').raw,'5')
    def test_insert_col(self):
        b=Book(); b.put('B1','3'); b.put('A2','=B1'); b.insert('col',2)
        self.assertEqual(b.get('C1').raw,'3'); self.assertEqual(b.get('A2').raw,'=C1')
    def test_move_block_undo(self):
        b=Book(); b.put('A1','7'); b.put('B1','=A1'); b.copy_block('A1:B1','C2',move=True)
        self.assertEqual(b.get('A1').raw,''); self.assertEqual(b.get('C2').raw,'7')
        self.assertEqual(b.get('D2').raw,'=A1')
        b.undo(); self.assertEqual(b.get('A1').raw,'7')
    def test_ui_syntax(self):
        self.assertTrue(callable(App)); self.assertIn('Style',__import__('ses.tui',fromlist=['MENUS']).MENUS)

if __name__=='__main__': unittest.main()
