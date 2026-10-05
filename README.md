# SES 0.1.0a1 — sumEditSpreadsheet

**First executable alpha**, written against the actual sumTUI 0.8.0a30 snapshot in `Sum.Full.20261004.21.39.tar.gz`. No existing sum package is patched, and no release is published.

## Launch

With current sumTUI + sumUI installed:

```bash
cd ses/ses
python3 -m pip install -e .
ses --theme DOS --demo
```

Or with the unpacked snapshot checked out, point `PYTHONPATH` at `sumui/sumui/src`, `sumtui/sumtui/src` and `ses/ses/src` and launch `python3 -m ses.cli --demo`.

`ses filename.ses` opens a saved workbook. SES saves `.ses` **JSON workbook v1**, intentionally not ODS/XLSX. Never edit a real workbook without making a backup: this is an alpha format.

## Supported

- Shared `sumTUI` `MenuDesktop` and hierarchical menus, shared theme with `--theme DOS`, keyboard navigation, mouse picking, formula bar.
- F2 edits existing content; typing replaces it. Enter commits, Esc cancels. Shift+arrows selects rectangle; mouse click/drag selects. Ctrl+B applies bold across the selection.
- F5 go-to; F6 cycles sheets; File → New sheet. Ctrl+Z/Y undo/redo whole transactions, including copied blocks and formatting.
- Ctrl+C/V copies the selected rectangle, shifting relative cell references, retaining `$` absolute/mixed addresses.
- While editing a formula, Ctrl+arrows pick cells, Ctrl+Shift+arrows extend selection, F4 inserts selected reference (first prototype of the intended direct range picker).
- `SUM AVG MIN MAX COUNT COUNTIF COUNTIFS SUMIF SUMIFS SUMPRODUCT IF AND OR NOT CHOOSE INDEX VLOOKUP HLOOKUP DATE TODAY ABS ROUND ROUNDUP ROUNDDOWN CEIL FLOOR MOD LEFT RIGHT MID FIND LENGTH/LEN UPPER LOWER TRIM REPLACE CONCAT/CONCATENATE STRING/STR VALUE`.
- Formulas beginning `=`, `+`, `@` (the latter as direct function syntax), same-sheet ranges `A1:B4`, simple cross-sheet references `Sheet2!A1` or `Sheet2.A1`, nested formulas, comparisons, arithmetic, string concatenation with `&`.
- Errors visible in cells (`#CYCLE!`, `#PARSE!`, `#REF!`, `#NAME?`, `#VALUE!`, `#DIV/0!`, etc.). Lazy, single-threaded, version-invalidation recalc: no formula execution with `eval()`.
- Ctrl+S saves to current workbook (or prompts for name); Ctrl+O opens; atomic replacement on save.

## Deliberately not yet supported

- Full Calc/Excel external-workbook syntax and `.ods`/`.xlsx` import/export. External files are **not executed, linked or loaded**.
- Full range picker mouse while editing; clicks in that mode currently select the grid, F4 inserts. Selection referencing is provisional.
- Conditional formatting, numeric pictures, full cell font settings, per-cell color, column resizing, merge/sort/filter, print and graph UI, mobile, sync, python-in-formula, historical macros, GUI backend testing.
- Excel locale-aware numbers or formulas with `,` decimal separator. Semicolon/comma argument separators work for dot-decimal formulas.
- Exact cross-application semantic aliases of ROUNDUP vs CEIL: these intentionally differ for negatives and digits; CEIL is mathematical +∞ and FLOOR -∞.
- Circular references are rejected (`#CYCLE!`), not iteratively solved.

**Known limits:** Saved cell styles are bold and label alignment only. `F4` is reference insertion, not yet absolute-address cycling. Formula error propagation is intentionally strict; COUNTIF wildcard behavior is preliminary. Cell/literal coordinates are bounded and ranges limited to 100k cells; memory use is not tuned for large sheets. This alpha is for testing, not production accounting.

<p align=center><b>- oOo -</b></p>


