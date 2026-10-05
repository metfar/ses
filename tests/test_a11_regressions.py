#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from ses.engine import Book, Parser, translate_formula;
from ses.preview import workbook_html;


def test_range_compatibility_colon_two_and_three_dots():
    for formula in ("SUM(A1:A3)","SUM(A1..A3)","SUM(A1...A3)"):
        node=Parser(formula,"en").parse();
        assert node[0]=="call" and node[2][0][0]=="range";


def test_formula_language_translation_existing_cells():
    book=Book("es"); book.put("A1","1"); book.put("A2","=SUMA(A1;2)");
    assert book.evaluate("A2")==3;
    book.set_formula_language("en");
    assert book.get("A2").raw=="=SUM(A1;2)";
    assert book.evaluate("A2")==3;


def test_translation_preserves_strings_and_refs():
    assert translate_formula('SI(A1>0;"SI";FALSO)',"es","en") == 'IF(A1>0;"SI";FALSE)';


def test_preview_preserves_default_document_colours():
    book=Book(); book.put("A1","'hello");
    markup=workbook_html(book);
    assert "color:#aaaaaa" in markup;
    assert "background-color:#000000" in markup;


def test_instr_is_zero_based():
    book=Book();
    book.put("A1",'=INSTR("abcdef";"cd")'); assert book.evaluate("A1")==2;
    book.put("A2",'=INSTR("abcdef";"zz")'); assert book.evaluate("A2")==-1;
