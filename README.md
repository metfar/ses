# SES 0.1.0a2 — experimental terminal spreadsheet

A first, **independent** implementation of SES, inspired by the keyboard-first text interface of Quattro Pro / Lotus 1-2-3. It does **not** alter sumcore or any existing sum packages. Python >= 3.10, stdlib-only runtime, curses (Linux).

## Run

```bash
cd SES-0.1.0
python3 -m ses
```

To install as command: `python3 -m pip install --user .` (or in a virtual environment); then `ses`.

## Keys

| Key | Action |
|---|---|
| Arrow keys | Navigate |
| Shift+arrows | Extend range (when terminal emits distinct shifted keys) |
| F1 | Help |
| F2, or click formula bar | Edit existing cell |
| Printable key | Replace active cell and start typing |
| Enter | Commit edit |
| Tab while editing | Pick formula reference with sheet cursor; press Enter to insert |
| Ctrl+B | Bold entire selection |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| F5 | Go to cell |
| F6 | Next sheet |
| F9 | Recalculate |
| F10 / Esc | Menus |
| `:` | Command line |

### Commands

`:save filename.ses`, `:open filename.ses`, `:sheet Pagos`, `:goto B20`, `:select A1:C12`, `:bold`, `:align center`, `:copy A1 C1`, `:undo`, `:redo`, `:quit`.

### Entering data

- Plain text or numbers, or formulas beginning `=`, `+`, `@` (e.g. `=SUM(A1:A3)`, `@SUM(A1:A3)`).
- `'Text` left-aligned; `^Text` centered; `"Text` right-aligned; `\-` repeat dash to column width.
- Cell addresses support `$A1`, `A$1`, `$A$1`; copy adjusts relative parts.
- Cross-sheet: `=Sheet2!A1`.
- `=SUMIF(A1:A5;"Ana";B1:B5)` and `=COUNTIF(A1:A5;">10")`.
- Errors such as `#PARSE!`, `#NAME?`, `#REF!`, `#CYCLE!`, `#DIV/0!` appear in cells.
- `ROUND` uses half-even; `ROUNDUP` away from zero, `ROUNDDOWN` towards zero; `CEIL` and `FLOOR` use +/- infinity (not synonyms for negative numbers).

## Important limitations

This is an **alpha prototype**, not production-ready for financial/business records. Only the native JSON-based `.ses` workbook is supported; external workbooks, Excel/ODS, locale customization, remote sync, printing, charts, stylesheets, Python cells and full mobile support remain out of scope. Formula expressions and function coverage are intentionally limited. The formula editor uses Tab as a range-picking toggle; terminals differ in mouse and shifted-arrow support. Single workbook, single-process calculation, bounded recursive evaluation with circular reference detection and cached results; no parallel evaluation.

Input is parsed without `eval()`. The `.ses` JSON document is not an encrypted or authenticated format. Keep backups of important documents.

## SES 0.1.0a2 additions

This development revision adds a visible text cursor in the formula bar while editing,
underline (`Ctrl+U`), foreground/background colors 0–7, optional DOS box-drawing
full grid, internal copy/cut/paste (`Ctrl+C`, `Ctrl+X`, `Ctrl+V`), fill down/right,
and insert row/column. Mouse-click column and row headings select full columns
and rows. Holding Shift while clicking extends a selection; Ctrl-click adds a
separate selected area **when the terminal reports those modifiers**. Affected
edits are recorded as single undo/redo operations. Cell formats survive save/load.

The Style menu toggles grid display. With the grid on, separators use an extra
terminal row between sheet rows; the grid never becomes part of cell content.

Examples of command-mode alternatives: `:copy A1:B3 D7`, `:cut A1:B3 D7`,
`:fill down B1:B20`, `:fill right A3:E3`, `:row 4`, `:col C`, `:fg 3`,
`:bg 1`, `:underline`, `:grid`.

**Alpha limitations:** Only internal clipboard; system clipboard and multi-area
copy/paste are not yet supported. Full-column formatting is capped at 50,000
cells per command. Row/column insertion adjusts local and unquoted `Sheet!A1`
references in the currently loaded workbook, but does not yet handle quoted
sheet names, external files, named ranges, or every possible formula grammar.
Cut/paste moves the source formula without retargeting all dependent formulas.
Use backups for actual business records. Shift/Ctrl mouse selection depends on
terminal modifier reporting; it may not be reliable in all terminals.

<p align=center><b>- oOo -</b></p>


