# SES 0.1.0a3 — experimental terminal spreadsheet

A first, **independent** implementation of SES, inspired by the keyboard-first text interface of Quattro Pro / Lotus 1-2-3. It does **not** alter sumcore or any existing sum packages. Python >= 3.10, curses (Linux) and sumTUI >= 0.8.0a30, which also supplies the shared dialogs and theme definitions.

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

## SES 0.1.0a3 — CLI, file dialogs and preferences (regression fix)

- `ses --theme DOS --demo` restores the demo and theme options.
- `ses /path/to/mybook.ses` opens a native workbook before the TUI starts.
- `ses --grid`, `ses --no-grid`, `ses --list-themes` and `ses --help`.
- `File -> Open` delegates to the existing **sumTUI FileDialog**; `File -> Save as` uses the existing **sumTUI read_entry**, with a prefilled filename and overwrite confirmation. `File -> Save` reuses the loaded filename, or enters Save as if none.
- `Style -> Theme` chooses an existing sumTUI theme. SES does not alter the transversal theme manager. Terminal rendering maps sumTUI RGB roles to available curses colors; true-color fidelity is not guaranteed.
- User preferences are stored in `${XDG_CONFIG_HOME:-~/.config}/sum/ses.json`: theme, grid enabled and last used directory. Explicit command-line options override saved preferences, and changes made in SES persist. Document data remains inside the workbook.
- `--demo` and positional filename are mutually exclusive. A nonexistent/invalid filename produces an error rather than silently starting an empty sheet.

**Integration caveat:** SES still uses curses for its sheet and sumTUI's Rich-backed event loop for file dialogs. It suspends curses during a dialog. This transition should be tested in the user's actual terminal; long term the sheet should migrate to a shared sumTUI application/event loop.

<p align=center><b>- oOo -</b></p>


