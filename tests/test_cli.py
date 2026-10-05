import tempfile;
from pathlib import Path;

from ses.engine import Book;
from ses.tui import argument_parser, load_preferences, save_preferences, sample_book;
from ses.version import __version__;


def test_version_is_single_source():
    assert __version__ == "0.1.0a6";
    text=(Path(__file__).resolve().parents[1]/"README.md").read_text(encoding="utf-8");
    assert "SES 0.1.0a6" in text;
    assert text.rstrip().endswith('<p align=center><b>- oOo -</b></p>');


def test_parser_accepts_theme_demo_file_and_borders():
    a=argument_parser().parse_args(["--theme","DOS","--demo","--border","thick"]);
    assert (a.theme,a.demo,a.border)==("DOS",True,"thick");
    a=argument_parser().parse_args(["--theme","ZX","/tmp/example.ses"]);
    assert (a.theme,a.file)==("ZX","/tmp/example.ses");


def test_demo_formulas():
    b=sample_book();
    assert b.evaluate("J6")==795.0;
    assert b.evaluate("J7")==1;
    assert b.evaluate("J8")==240.0;
    assert b.evaluate("J9")==1;


def test_preferences_roundtrip():
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"sumtui"/"ses.json";
        save_preferences({"theme":"MC","border":"thick","last_dir":"/tmp"},path);
        assert load_preferences(path)=={"theme":"MC","border":"thick","last_dir":"/tmp"};
