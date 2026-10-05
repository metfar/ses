"""Regression tests for SES command line, persisted preferences, demo and file loading."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ses.engine import Book
from ses.tui import argument_parser, load_preferences, save_preferences, sample_book, theme_palette, main


class CLIRegressionTests(unittest.TestCase):
    def test_parser_accepts_legacy_arguments(self):
        a=argument_parser().parse_args(['--theme','DOS','--demo'])
        self.assertEqual((a.theme,a.demo,a.file),('DOS',True,None))
        a=argument_parser().parse_args(['--theme','ZX','/tmp/example.ses'])
        self.assertEqual((a.theme,a.file),('ZX','/tmp/example.ses'))
        self.assertTrue(argument_parser().parse_args(['--grid']).grid)

    def test_demo_produces_real_formulas(self):
        b=sample_book()
        self.assertEqual(b.evaluate('J6'),795.0)
        self.assertEqual(b.get('J6').raw,'=SUM(J2:J4)')

    def test_preferences_roundtrip_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sum'/'ses.json'
            save_preferences({'theme':'XBASE','grid':True,'last_dir':'/tmp'},path)
            self.assertEqual(load_preferences(path),{'theme':'XBASE','grid':True,'last_dir':'/tmp'})
            path.write_text('{bad json}',encoding='utf-8')
            self.assertEqual(load_preferences(path),{})

    def test_theme_names_use_canonical_sumtui(self):
        self.assertEqual(theme_palette('dos').name,'DOS')
        self.assertEqual(theme_palette('ZX').name,'ZX')
        with self.assertRaises(ValueError): theme_palette('invented_theme')

    def test_loading_file_is_done_before_terminal_start(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'workbook with spaces.ses'
            b=Book(); b.put('A1','42'); b.save(path)
            with patch('ses.tui.curses.wrapper') as wrapper, patch('ses.tui.sys.stdin.isatty',return_value=True), patch('ses.tui.sys.stdout.isatty',return_value=True):
                self.assertEqual(main(['--theme','DOS',str(path)]),0)
            self.assertTrue(wrapper.called)
            self.assertEqual(wrapper.call_args.args[0].__name__,'run')

    def test_invalid_file_gives_nonzero_exit(self):
        with self.assertRaises(SystemExit) as failure:
            main(['/definitely/absent.ses'])
        self.assertEqual(failure.exception.code,2)


if __name__=='__main__': unittest.main()

class DialogIntegrationTests(unittest.TestCase):
    def test_existing_sumtui_file_picker_is_used(self):
        from unittest.mock import MagicMock
        from ses.tui import App
        window=MagicMock()
        app=App.__new__(App); app.win=window; app.theme_name='DOS'
        with patch('ses.tui.curses.def_prog_mode'), patch('ses.tui.curses.endwin'), patch('ses.tui.curses.reset_prog_mode'), patch('sumtui.dialogs.choose_file') as picker:
            picker.return_value=type('Result',(),{'accepted':True,'value':'book.ses'})()
            result=app.shared_dialog('open','/tmp',title='Open SES')
            picker.assert_called_once_with(path='/tmp',title='Open SES',theme='DOS')
            self.assertTrue(result.accepted)

    def test_existing_sumtui_text_input_has_default_filename(self):
        from unittest.mock import MagicMock
        from ses.tui import App
        app=App.__new__(App); app.win=MagicMock(); app.theme_name='ZX'
        with patch('ses.tui.curses.def_prog_mode'), patch('ses.tui.curses.endwin'), patch('ses.tui.curses.reset_prog_mode'), patch('sumtui.dialogs.read_entry') as entry:
            app.shared_dialog('entry','/tmp/my file.ses',title='Save as')
            entry.assert_called_once_with(text='File name or full path',default='/tmp/my file.ses',title='Save as',theme='ZX')

class DemoAndThemeRegressionTests(unittest.TestCase):
    def test_demo_exercises_condition_lookup_criteria_and_colors(self):
        b=sample_book()
        self.assertEqual(b.evaluate('I2'),120.0)
        self.assertEqual(b.evaluate('K2'),'SMALL')
        self.assertEqual(b.evaluate('K4'),'BIG')
        self.assertEqual(b.evaluate('J6'),795.0)
        self.assertEqual(b.evaluate('J7'),1)
        self.assertEqual(b.evaluate('J8'),240.0)
        self.assertEqual(b.evaluate('J9'),1)
        self.assertEqual(b.get('J6').bg,2)
        self.assertTrue(b.get('J6').bold)

    def test_apply_theme_uses_sumtui_semantic_roles(self):
        from ses.tui import App
        theme=type('Theme',(),{
            'name':'MC','style':lambda self,role:'STYLE:'+role
        })()
        app=App.__new__(App); app.colors=False; app.theme_pairs={}
        seen=[]
        app._style_attr=lambda style,number: seen.append((style,number)) or number
        with patch('ses.tui.theme_palette',return_value=theme):
            app.apply_theme('MC')
        self.assertEqual(app.theme_name,'MC')
        self.assertEqual([item[0] for item in seen],[
            'STYLE:menu_bar','STYLE:input','STYLE:table_header','STYLE:viewer',
            'STYLE:status','STYLE:selection','STYLE:border','STYLE:input_focus'])

def test_theme_palette_refreshes_user_themes(monkeypatch):
    import ses.tui as tui
    calls=[]
    class FakeTheme:
        name='MC'
    monkeypatch.setattr('sumtui.theme.refresh_user_themes', lambda: calls.append('refresh'))
    monkeypatch.setattr('sumtui.theme.available_theme_names', lambda include_hidden=False: ('DOS','MC'))
    monkeypatch.setattr('sumtui.theme.make_theme', lambda name: FakeTheme() if str(name).casefold()=='mc' else None)
    result=tui.theme_palette('MC')
    assert calls == ['refresh']
    assert result.name == 'MC'


def test_readme_has_standard_markdown_closure():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/'README.md').read_text(encoding='utf-8').rstrip()
    assert text.endswith('<p align=center><b>- oOo -</b></p>')
