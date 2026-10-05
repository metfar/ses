#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from ses.engine import Book;

def test_spanish_formula_aliases():
    b=Book("es");
    b.put("A1","5");
    b.put("A2","=SI(A1>0; SUMA(A1;2); 0)");
    assert b.evaluate("A2")==7;

def test_french_and_portuguese_lookup_aliases():
    b=Book("fr"); b.put("A1","1"); b.put("B1","10"); b.put("A2","2"); b.put("B2","20");
    b.put("D1","=RECHERCHEV(2;A1:B2;2;FAUX)");
    assert b.evaluate("D1")==20;
    p=Book("pt"); p.put("A1","=SE(VERDADEIRO;SOMA(2;3);0)");
    assert p.evaluate("A1")==5;

def test_language_persists(tmp_path):
    path=tmp_path/"lang.ses"; b=Book("es"); b.put("A1","=SUMA(1;2)"); b.save(path); c=Book.load(path);
    assert c.formula_language=="es"; assert c.evaluate("A1")==3;
