# SES 0.1.0a7 — sumEditSpreadsheet

SES is the keyboard-first spreadsheet/table editor for the sum ecosystem. This revision moves the whole interactive shell to **sumTUI** instead of maintaining a parallel curses UI, so menus, mouse routing, dialogs, themes, status bars and focus behavior come from the same transversal layer used by the other sum applications.

## Main interaction

- `F2` or click the formula bar: edit the current cell.
- Typing while the grid has focus replaces the current cell and enters edit mode.
- `Ctrl+Z` / `Ctrl+Y`: undo / redo.
- `Ctrl+C` / `Ctrl+X` / `Ctrl+V`: copy / cut / paste.
- `Ctrl+B` / `Ctrl+U`: bold / underline the current selection.
- Click a row or column header to select it.
- `Shift` extends row, column or cell selections; `Ctrl` adds a disjoint selection when the terminal reports mouse modifiers.
- Relative, absolute and mixed references keep the existing SES calculation semantics (`A1`, `$A1`, `A$1`, `$A$1`).

## sumTUI integration

The top menu is now a real `sumTUI.MenuBar` inside `sumTUI.MenuDesktop`. Mouse clicks on the menu are therefore handled by sumTUI itself, including multi-level submenus. Open/Save/Save As, About, Help and theme selection also use sumTUI components and the active `sumtheme` roles.

SES-specific rendering is limited to the spreadsheet grid and formula semantics. Theme colors are not reimplemented in SES. Explicit foreground/background colors stored in cells remain document formatting and intentionally override the application theme for those cells.

## Borders and reusable tables

`Style -> Borders` supports:

- none
- single
- thick

The border glyphs are validated against `sumcore.charset.ASC`, so the grid uses the same canonical extended charset as the rest of sum. The model stores the semantic border style, not border characters as cell contents. This is intended to become the shared table behavior that SEP can invoke for editing embedded document tables.

Examples:

```text
┌────────────┬────────────┐
│            │            │
├────────────┼────────────┤
│            │            │
└────────────┴────────────┘
```

and the thick variant:

```text
┏━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃            ┃            ┃
┣━━━━━━━━━━━━╋━━━━━━━━━━━━┫
┃            ┃            ┃
┗━━━━━━━━━━━━┻━━━━━━━━━━━━┛
```

## Print preview

`File -> Print preview` builds a PDF from the active sheet and opens it with the platform viewer (`xdg-open` on Linux, `open` on macOS, the native shell on Windows). The PDF path is temporary. Preview uses WeasyPrint when available, which is already part of the sumdoc stack; SES does not attempt to emulate a graphical page preview inside the terminal.

Preview now separates editing aids from document formatting. Grid lines, column headers and row headers are independently configurable and are OFF by default for preview/printing. Explicit cell/table borders are stored in the workbook and are always rendered in preview regardless of those options. Page setup, repeating headers, print areas and full SDSS styling remain later work.

## Demo and command line

```bash
ses --theme MC --demo
ses --theme DOS --border thick workbook.ses
ses workbook.ses
ses --list-themes
```

`--grid` is retained as an alias for `--border single`, and `--no-grid` for `--border none`.

Preferences are stored under `${XDG_CONFIG_HOME:-~/.config}/sumtui/ses.json` and include theme, grid style, visible grid lines, row/column headers, preview grid/header choices, and the last directory.

## Grid aids and real table borders

`View` controls the editing surface independently: grid lines, column headers and row headers can each be shown or hidden. These are interface aids, not cell formatting.

`Style -> Cell borders` applies semantic borders (`single` or `thick`) to the selected cells/range. Those borders belong to the workbook and therefore remain visible in PDF preview even when preview grid lines and headings are disabled. This distinction is intended for reuse by SEP when SES is invoked to edit document tables.

Preview defaults are deliberately clean:

```text
grid lines      off
column headers  off
row headers     off
```

## Formula coverage

The current engine includes arithmetic, ranges, cross-sheet references, circular-reference detection, copying/filling of relative formulas, and functions including `SUM`, `AVG`, `COUNT`, `SUMPRODUCT`, `COUNTIF`, `COUNTIFS`, `SUMIF`, `SUMIFS`, `IF`, `AND`, `OR`, `NOT`, `ROUND`, `ROUNDUP`, `ROUNDDOWN`, `CEIL`, `FLOOR`, `VALUE`, `STRING`, `CONCAT`, `LEFT`, `RIGHT`, `MID`, `FIND`, `LENGTH`, `INDEX`, `CHOOSE`, `VLOOKUP` and `HLOOKUP`.

SES remains alpha software. Keep backups of real business workbooks while the file format and editing semantics are still evolving.

<p align=center><b>- oOo -</b></p>
