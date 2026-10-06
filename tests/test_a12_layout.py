#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from ses.engine import Book, SheetError;
from ses.preview import workbook_html;
from ses.tui import SESController;
from sumtui import KeyEvent;


def test_merge_roundtrip_and_preview(tmp_path):
    b=Book(); b.put("A1","'Quarterly report"); b.merge(["A1","B1","A2","B2"]);
    assert b.merged_region_at("A1")== (1,1,2,2);
    assert b.merged_region_at("B2")== (1,1,2,2);
    html=workbook_html(b);
    assert "colspan='2'" in html and "rowspan='2'" in html;
    p=tmp_path/"merge.ses"; b.save(p); c=Book.load(p);
    assert c.merged_region_at("B2")== (1,1,2,2);


def test_unmerge_from_any_overlapping_cell():
    b=Book(); b.merge(["A1","B1","A2","B2"]); b.unmerge(["B2"]);
    assert b.merged_region_at("A1") is None;


def test_merge_rejects_discontinuous_selection():
    b=Book();
    try:
        b.merge(["A1","B2"]);
    except SheetError as exc:
        assert exc.code=="#RANGE!";
    else:
        raise AssertionError("discontinuous merge accepted");


def test_insert_inside_merge_expands_region():
    b=Book(); b.merge(["A1","B1","A2","B2"]); b.insert("row",2);
    assert b.merged_region_at("B3")== (1,1,2,3);
    b.insert("col",2);
    assert b.merged_region_at("C3")== (1,1,3,3);


def test_vertical_alignment_and_center_across_persist(tmp_path):
    b=Book(); b.put("A1","'Title"); b.style(["A1"],"align","center_across"); b.style(["A1"],"valign","bottom");
    p=tmp_path/"align.ses"; b.save(p); c=Book.load(p);
    assert c.get("A1").align=="center_across";
    assert c.get("A1").valign=="bottom";
    html=workbook_html(c);
    assert "text-align:center" in html and "vertical-align:bottom" in html;


def test_page_setup_is_logical_pixels_and_scale_changes_breaks(tmp_path):
    b=Book(); b.set_page_setup(page_width_px=300,page_height_px=300,margin_left_px=20,margin_right_px=20,margin_top_px=20,margin_bottom_px=20,scale_percent=100);
    breaks100=b.page_break_columns(6);
    b.set_page_setup(scale_percent=200);
    breaks200=b.page_break_columns(6);
    assert breaks100 != breaks200;
    html=workbook_html(b);
    assert "size:300px 300px" in html and "font-size:26.00px" in html;
    p=tmp_path/"page.ses"; b.save(p); c=Book.load(p);
    assert c.page_setup["scale_percent"]==200;


def test_alt_menu_mnemonics_are_enabled_by_sumtui():
    controller=SESController(theme="DOS",preferences={});
    event=KeyEvent("f",text="f",alt=True);
    assert controller.menu.handle_event(event) is True;
    assert controller.menu.active is True and controller.menu.menu_index==0;
