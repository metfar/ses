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
    assert ">6.0<" in text;
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
    assert "0.1.0a6" in dialog.call_args.args[0];
