from pathlib import Path;
from unittest.mock import patch;

from ses.borders import border_names, glyphs;
from ses.engine import Book;
from ses.preview import workbook_html;
from ses.tui import SESController;


def test_border_styles_have_complete_glyph_sets():
    assert border_names()==("none","single","thick");
    assert glyphs("single").x=="┼";
    assert glyphs("thick").x=="╋";


def test_preview_contains_evaluated_values():
    b=Book(); b.put("A1","2"); b.put("B1","=A1*3");
    text=workbook_html(b);
    assert ">6<" in text;
    assert "<table>" in text;


def test_controller_uses_sumtui_menudesktop_and_real_menubar():
    from sumtui import MenuDesktop, MenuBar;
    with patch.object(SESController,"persist",lambda self:None):
        controller=SESController(theme="DOS");
    assert isinstance(controller.root,MenuDesktop);
    assert isinstance(controller.menu,MenuBar);
    assert controller.root.menu is controller.menu;


def test_about_uses_current_version():
    with patch.object(SESController,"persist",lambda self:None):
        controller=SESController(theme="DOS");
    seen={};
    controller._external=lambda cb: cb();
    with patch("ses.tui.show_message") as dialog:
        controller.about();
    assert "0.1.0a10" in dialog.call_args.args[0];


def test_preview_editing_aids_default_off_but_explicit_borders_remain():
    b=Book(); b.put("A1","'Name"); b.put("B1","'Value"); b.put("A2","'Tea"); b.put("B2","120");
    b.border(["A1","B1","A2","B2"],"single",outline=False);
    text=workbook_html(b);
    assert "<thead>" not in text;
    assert "<th>1</th>" not in text;
    assert "border:0.2mm solid #bbb" not in text;
    assert "border-top:0.35mm solid #555" in text;


def test_preview_headers_and_gridlines_are_independent_options():
    b=Book(); b.put("A1","1");
    text=workbook_html(b,gridlines=True,column_headers=True,row_headers=True);
    assert "<thead>" in text;
    assert "<th>A</th>" in text;
    assert "<th>1</th>" in text;
    assert "border:0.2mm solid #bbb" in text;


def test_cell_border_is_undoable_and_persistent(tmp_path):
    b=Book(); b.put("A1","1"); b.put("B1","2");
    b.border(["A1","B1"],"thick",outline=True);
    assert b.get("A1").border_left=="thick";
    assert b.get("B1").border_right=="thick";
    path=tmp_path/"borders.ses"; b.save(path); loaded=Book.load(path);
    assert loaded.get("A1").border_left=="thick";
    loaded.undo();  # load has no history; border remains
    assert loaded.get("B1").border_right=="thick";


def test_controller_preview_defaults_are_off():
    with patch.object(SESController,"persist",lambda self:None):
        controller=SESController(theme="DOS");
    assert controller.preview_gridlines is False;
    assert controller.preview_column_headers is False;
    assert controller.preview_row_headers is False;

def test_dimensions_picture_and_persistence(tmp_path):
    from ses.engine import Book, format_picture
    b=Book(); b.put('A1','5'); b.set_column_width([1],18); b.set_row_height([1],2); b.set_picture(['A1'],' $ 0000.00 ')
    assert b.column_width(1)==18
    assert b.row_height(1)==2
    assert format_picture(b.evaluate('A1'),b.get('A1').picture)==' $ 0005.00 '
    p=tmp_path/'dims.ses'; b.save(p); c=Book.load(p)
    assert c.column_width(1)==18 and c.row_height(1)==2 and c.get('A1').picture==' $ 0000.00 '

def test_picture_does_not_change_value():
    from ses.engine import Book
    b=Book(); b.put('A1','5'); b.set_picture(['A1'],'000.00')
    assert b.evaluate('A1')==5.0


def test_preview_plain_numbers_match_tui_without_forced_decimals():
    b=Book(); b.put("A1","120"); b.put("A2","8");
    text=workbook_html(b);
    assert ">120<" in text and ">8<" in text;
    assert ">120.0<" not in text and ">8.0<" not in text;

def test_preview_keeps_explicit_cell_colors_only():
    b=Book(); b.put("A1","1"); b.put("B1","2");
    b.style(["A1"],"fg",1); b.style(["A1"],"bg",6);
    text=workbook_html(b);
    assert "color:#aa0000" in text;
    assert "background-color:#00aaaa" in text;
    # Default B1 colors are not forced onto the printable page.
    assert text.count("background-color:")==1;

def test_explicit_color_flags_survive_roundtrip(tmp_path):
    b=Book(); b.put("A1","1"); b.style(["A1"],"fg",0); b.style(["A1"],"bg",7);
    p=tmp_path/"colors.ses"; b.save(p); c=Book.load(p);
    assert c.get("A1").fg_explicit is True and c.get("A1").bg_explicit is True;
