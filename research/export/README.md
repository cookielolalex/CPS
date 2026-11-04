# CPS portable export route (writer004 reproduction)

**Status: NOT ADMITTED.** Built 2026-11-03 under the owner decision to add a portable writer so CPS can run saved 17-column workbook QA and visual QA. The admitted writer, `writer004.mjs`, needs `@oai/artifact-tool` and a Windows source-verification helper, and neither exists here (DECISIONS_046b R2). Nothing in this directory may be used for CPS saved-cell QA, visual QA or deployment evidence until an independent reviewer (not the author) admits it. A successful run or a passing test is not admission.

**Mode v2 (added 2026-11-04 for candidate 046f; also NOT ADMITTED).** Owner decision O13 makes M and N job inputs, which route v4 carries as `selection_evidence`. The archived writer004 gate accepts selection evidence for L only. Mode v2 relaxes exactly that one check, by the method in "Mode v2" below. Mode v1 (the default) is unchanged.

This directory holds code and invented test fixtures only. Do not commit case carriers, outputs, renders or reports made from case data. Write those outside the repository.

## Files

| File | Role |
|---|---|
| `writer_portable.py` | Carrier → `research-draft.xlsx`, `EXPECTED_SAVED_VALUES.json` and `WRITER_RECEIPT.json` |
| `writer004_matrices.mjs` | Runtime cross-check. Runs the archived writer004 `prepareMatrices` in node and prints the `EXPECTED_SAVED_VALUES.json` text writer004 would save |
| `saved_qa.py` | Reopens the saved workbook and compares every cell with `EXPECTED_SAVED_VALUES.json`, then writes `SAVED_QA.json` |
| `visual_qa.py` | LibreOffice PDF → pdftoppm PNGs, then writes `VISUAL_QA_MANIFEST.json`. A reviewer makes the visual judgement later |
| `tests/run_export_tests.py` | Test suite (invented fixtures). Prints a JSON summary |
| `tests/make_export_fixtures.py` | Builds invented carrier variants from the 046d route-test fixture carrier |
| `tests/make_export_fixtures_v2.py` | Builds invented mode-v2 variants from two 046f route v4 fixture carriers (with and without M/N selection evidence) |
| `tests/parity_matrices.mjs`, `tests/stringify_fuzz.mjs` | Test-only node probes, written separately from the runtime cross-check |

## Route

1. **Gate.** The writer runs the archived `validate_carrier_v4.mjs` in node, unchanged and with the `@oai/artifact-tool` import resolved to the CPS validation stub. It refuses unless the result is `WRITER_STRUCTURAL_VALIDATION_ONLY` for the same carrier sha256. The writer files are pinned by sha256:
   - `writer004.mjs`: either `85a7f619…c0d7` (the archived original) or `70d7f664…efb7` (the public copy in `research/checkpoint045/writer/`). The two differ only in the redacted Windows helper path on line 218, which validateCarrier/prepareMatrices never reach.
   - `validate_carrier_v4.mjs`: `984da083…e013`.
   - `receipt_bytes.mjs`: `b2ff15fd…1d2c`.
2. **Matrices.** A Python reimplementation of writer004 `prepareMatrices`, including its review-cell check (`REVIEW_CELL_UNSAFE_OR_TOO_LONG`). `validate_carrier_v4.mjs` does not run that check. The reimplementation uses JavaScript semantics:
   - all JSON numbers are binary64;
   - `JSON.stringify` quoting, including escaped lone surrogates;
   - ECMAScript `Number::toString`;
   - property order with array-index keys first.

   The route tool's Python port (`cps046b_route.py`) validates only and builds no matrices, so it is not reused. The tests check that the shared constants match it.
3. **Cross-check (every run).** writer004's own `prepareMatrices` runs on the same carrier through `writer004_matrices.mjs`. Its `JSON.stringify({sheets}, null, 2) + "\n"` must be byte-identical to the Python text, or the carrier is refused (`CROSS_CHECK_MISMATCH`). Each saved `EXPECTED_SAVED_VALUES.json` is therefore the exact text writer004 would have written for that carrier.
4. **Writability.** The writer refuses cell text that the openpyxl/XML route cannot carry unambiguously. See "Extra refusals" below.
5. **Assembly.** openpyxl writes the workbook from the matrices. Strings stay strings, numbers stay numbers, empty stays empty, and no formula is ever written. Output bytes are reproducible: the same carrier gives the same xlsx sha256.

## Mode v2: the O13 relaxation for 046f carriers

`--mode v2` is for carriers made by route v4 (`research/guideline046_006/package/tools/cps046b_route.py`, `cps046f-route.v4`). The route's convert receipt says when it is needed (`o13_m_n_selection_evidence.export_mode_required`).

- **Carrier without M/N selection evidence:** exactly the v1 route above. The output bytes equal mode v1.
- **Carrier with M/N selection evidence** (an evidence object for column M or N that holds `selection_evidence`):
  1. **Placeholder copy.** In a copy of the carrier, each such M/N evidence object is replaced by the same object without `selection_evidence`, plus `location` = the item's own `location`, `anchor` = the item's `anchor` and `raw_text` = the `selection_evidence` text. `transformation` and any other key are unchanged, so a malformed object stays malformed. Nothing else changes. The copy has the shape writer004 requires for location evidence, and the item's own location is valid by construction.
  2. **Gate (both must pass).** writer004 `validate_carrier_v4.mjs` runs unchanged on the copy (stage `gate:validate_carrier_v4:o13_placeholder_copy`). The route v4 Python port `validate_carrier_port` runs on the original carrier (stage `gate:route_v4_port`). The port is writer004's validateCarrier plus the prepareMatrices review-cell check, with one difference: it accepts `selection_evidence` for L, M and N. The route tests show by parity fuzzing that this is the only divergence from node writer004. The writer checks the port's `VERSION` and records its sha256.
  3. **Cross-check.** writer004 `prepareMatrices` runs on the copy and must be byte-identical to the Python matrices of the copy (stage `cross_check:o13_placeholder_copy`).
  4. **Allowed difference.** The Python matrices of the original carrier, which are saved, may differ from the copy's matrices only in columns C–E (evidence location, anchor and JSON text) of the review rows `欄位依據 <id>.M` and `<id>.N` of those fields. There, the original has writer004's own selection-evidence form: an empty location, the anchor `"已核對工程選取"` and the JSON of the selection evidence. That is the same code path writer004 uses for L. Any other difference refuses the carrier (`O13_DIFF_OUTSIDE_M_N_EVIDENCE`).
  5. **Receipt.** `WRITER_RECEIPT.json` records `mode`, an `o13` section (fields, placeholder method, placeholder-copy sha256, route port path, sha256 and version, the copy cross-check, and every differing cell) and an extra limitation. `expected_saved_values.identical_to_writer004_prepareMatrices_output` is `false`, with `identical_to_writer004_prepareMatrices_on_o13_placeholder_copy_except_m_n_evidence_cells: true`.
- **Refusals in mode v2.** Selection evidence on any column other than L, M or N is still refused by writer004 on the copy (`SELECTION_ONLY_ENGINEERING_ID`). Path-like or malformed M/N selection evidence is refused by writer004 on the copy or by the route port. Every other writer004 refusal is unchanged.

## What it reproduces

- Sheet names and order: `未填研究草稿`, `來源與審查`, `組成參考`, `組成連結` (the writer004 `worksheets.add` order).
- Every cell value and type in writer004's matrices. These are the values writer004 hands to artifact-tool and records in `EXPECTED_SAVED_VALUES.json`. Numbers are written with JavaScript Number-to-String text, so 17-digit doubles such as 0.30000000000000004, 1e-7 and 5e-324 survive exactly.
- `EXPECTED_SAVED_VALUES.json` in writer004's shape and bytes (`{"sheets":[{"name","values"}…]}`, 2-space JSON.stringify, trailing newline).
- The formatting from writer004 `formatSheet` and the main-sheet extras that openpyxl can express:
  - Body cells: Arial 11, colour #172033, vertical top, wrap text.
  - Header row: fill #29445D, Arial 11 bold white, centred horizontally and vertically, height 36.
  - Column widths (17-column sheets `[18,30,38,48,9,12,12,12,20,18,22,18,24,24,18,12,14]`, links `[24,12,24,12,12,12,65,65]`, review `[18,23,38,38,88,62,18]`).
  - Gridlines hidden; frozen pane at D2.
  - Main sheet: tab colour #29445D; F/P/Q data cells General and right-aligned; G/H data cells filled #F1F3F5.

## What it does not reproduce (limitations, with evidence)

| # | Limitation | Evidence |
|---|---|---|
| L1 | **The gate is `validateCarrier` only.** writer004 `build()` also runs `authorizeSource`: allowlist pin, original-file sha256, and the receipt from the Windows `source_verify.py` helper. None of these runs here. | `writer004.mjs` lines 120–133 and 215–231 (the helper is a fixed Windows `python.exe` path). |
| L2 | **artifact-tool save semantics are unverified.** The portable workbook carries exactly the EXPECTED values and types. Whether artifact-tool saved numeric-looking or date-looking text (for example `123`, `2024/01/01`, `TRUE`) as text is unknown, because artifact-tool is unavailable. | Stub `node_modules/@oai/artifact-tool/index.mjs` throws `EXPORT_RUNTIME_UNAVAILABLE`. |
| L3 | **Column width units.** writer004's numbers are written as OOXML character widths. artifact-tool's `columnWidth` unit is unverified. | `src/installed_baseline/runtime/export_workbooks.mjs` sizes rows using `width-2` characters per line (character units). Office.js uses points. |
| L4 | **`autofitRows` is not reproduced.** Data rows have no explicit height, so the application that opens the file sizes them. LibreOffice auto-sizes them in renders. The header height (36) is written. | openpyxl has no autofit. |
| L5 | **Freeze.** writer004 calls `freezeRows(1)` and then `freezeColumns(3)`. This route writes one frozen pane at D2. Whether artifact-tool kept both freezes is unverified. | `writer004.mjs` line 156. |
| L6 | **Not produced:** `INSPECTION.ndjson` and `ERROR_SCAN.ndjson` (artifact-tool `inspect`); the three artifact-tool PNG renders; `source-carrier.json`, `INPUT_PINS.json`, `research-draft.json` and `BUILD_RESULT.json`. `saved_qa.py` reports a literal error-text scan, and `visual_qa.py` renders with LibreOffice instead. | `writer004.mjs` lines 180–204. |
| L7 | **openpyxl workarounds.** (a) openpyxl writes numbers with `"%.16g"`, which loses 17-digit doubles (`openpyxl/compat/strings.py`). During save the writer substitutes JavaScript Number text in `openpyxl.cell._writer`, then restores it. (b) openpyxl types strings equal to Excel error literals (`#N/A`, `#REF!`, …) as error cells (`openpyxl/cell/cell.py` `_bind_value`). The writer forces string type. (c) openpyxl writes inline strings, not a shared-string table. The values are identical either way, and artifact-tool's choice is unknown. | Probe runs during development; the tests cover all three. |
| L8 | **Reproducible bytes.** docProps `created`/`modified` and zip member times are fixed to 1980-01-01T00:00:00. The real run time is in `WRITER_RECEIPT.json`. `calcPr fullCalcOnLoad` is turned off (nothing to calculate). | — |
| L9 | **Visual QA is a LibreOffice rendering, not Excel.** Fonts are substituted: Arial → Liberation Sans, and CJK → WenQuanYi Zen Hei here (recorded by `fc-match` in the manifest). Glyphs missing from the installed fonts show as boxes. | `VISUAL_QA_MANIFEST.json` `render_tools`. |
| L10 | **Mode v2 is not writer004 on the original carrier.** For a carrier with M/N selection evidence, writer004 validates and builds matrices only on the placeholder copy. The relaxed check comes from the route v4 port, and the saved review cells of those M/N fields come from the Python reimplementation of writer004's selection-evidence branch (the branch used for L). | Mode v2 above; route tests `writer_port_parity_only_divergence_is_O13`. |

### Extra refusals (the portable writer refuses carriers writer004 might accept)

- **Non-UTF-8 carrier bytes** (`UTF8_REQUIRED`). Node decodes them with U+FFFD and accepts.
- **A written cell string containing a lone surrogate, U+FFFE or U+FFFF** (`PORTABLE_UNREPRESENTABLE` / `XML_UNREPRESENTABLE_CHARACTER`). XML 1.0 cannot carry these. A lone surrogate that occurs only inside a JSON-encoded review cell is escaped by `JSON.stringify` and is written normally.
- **A literal OOXML escape sequence `_xHHHH_` in written text** (`LITERAL_OOXML_ESCAPE_SEQUENCE`). Spreadsheet applications decode it: LibreOffice reads an openpyxl-written `_x0041_` as `A` (measured), and openpyxl writes it unescaped. Escaping it as `_x005F_x0041_` would also make openpyxl readback differ from the value, so the route refuses. Partial patterns such as `AB_x12_` or `_x004` are fine.
- **Any difference between the Python and node matrices** (`CROSS_CHECK_MISMATCH`).
- **Mode v2:** any difference between the saved matrices and writer004's matrices of the placeholder copy outside the M/N evidence cells (`O13_DIFF_OUTSIDE_M_N_EVIDENCE`), and any refusal by the route v4 port.

## How to run

Prerequisites:

- `python3` with openpyxl 3.1.5 (lxml is used if present);
- node 22;
- LibreOffice (`soffice`) and poppler (`pdftoppm`, `pdfinfo`, `pdftotext`) for visual QA;
- the archived writer directory, with `@oai/artifact-tool` resolvable from it.

The CPS validation stub is enough for the writer directory. Put the stub at `<writer-dir>/../node_modules/@oai/artifact-tool/` as `index.mjs` (sha256 `67134aca…96a4`, exports `Workbook.create` and `SpreadsheetFile.exportXlsx`, which both throw) and `package.json` (`{"name":"@oai/artifact-tool","version":"0.0.0-cps-validation-stub","type":"module","main":"index.mjs","exports":"./index.mjs"}`).

```sh
W=/abs/route/writer                      # writer004.mjs, validate_carrier_v4.mjs, receipt_bytes.mjs
python3 -I -B research/export/writer_portable.py --carrier /abs/carrier.json --out /abs/new-output --writer-dir "$W"
#   --mode v2             candidate 046f carriers (O13: M/N job-input selection evidence); default v1
python3 -I -B research/export/saved_qa.py --output-dir /abs/new-output            # writes SAVED_QA.json there
python3 -I -B research/export/visual_qa.py --xlsx /abs/new-output/research-draft.xlsx --dest /abs/new-visual-dir
#   --mode exact          render an unmodified byte copy (LibreOffice default pagination)
#   --sheets 未填研究草稿,組成參考,組成連結   render PNGs only for these sheets (the PDF keeps every page)
```

- **Writer outputs.** A refusal creates no output directory and prints `{"status":"REFUSED","code","stage","detail"}` on stderr (exit 1). A failure after the output directory exists keeps the partial output and adds `WRITER_FAILURE.json`.
- **`saved_qa.py`.** Three readers: openpyxl `data_only=False`, openpyxl `data_only=True`, and an independent raw-OOXML reader. Each must match `EXPECTED_SAVED_VALUES.json` exactly in value and type, and the three must agree. The script also checks:
  - sheet order;
  - the 17-column header row of the main sheet (A1:Q1 equals the 17 headers, R1 empty);
  - no formula (`<f>`, formula-result or error cells, defined names), and no unexpected populated cell;
  - no external relationships;
  - Excel limits: 32,767 UTF-16 units per cell, 253 line feeds per cell, the grid, sheet-name rules, column widths up to 255, row heights up to 409 pt;
  - the integrity hashes in `WRITER_RECEIPT.json`;
  - unless `--no-formatting` is given, the formatting listed above.

  The original `research/checkpoint045/postqa/qa_saved_external.py` also runs unchanged on the same output layout.
- **`visual_qa.py`.** Default mode is `fit-width`. The temporary render copy gets print settings only: landscape A3, one page wide, header row repeated, page header = sheet name and page number. The tool verifies that every sheet's `<sheetData>` bytes are unchanged, and that the saved workbook is unchanged after rendering. PNG pixels are reproducible run to run; PDF bytes are not, because of LibreOffice metadata. Scale: a 407-item invented carrier (about 10,000 review rows) gave 434 A3 pages in about 4 minutes at 100 dpi.

## Tests

```sh
python3 -I -B research/export/tests/run_export_tests.py --writer-dir /abs/route/writer --work /abs/new-work-dir [--skip-visual]
```

The fixtures are invented. The suite runs the 046d route's own `make_fixtures.py` and `cps046b_route.py convert` to get an invented carrier, then derives 11 valid and 21 invalid variants. The variants cover:

- components, groups, held items and held components, selection evidence;
- CJK, astral, RTL and combining text; CR/LF/TAB/U+2028/NEL/BOM inside text;
- error literals, plus numeric-looking and date-looking text;
- 16,000-character and 30,000-character strings;
- numeric edge cases: 17-digit doubles, 1e-7, MAX_SAFE with grouping, −0, the denormal 5e-324, leading `+`;
- JavaScript key order;
- no components or groups; 407 items;
- `cached_xlsx`;
- leading-sign and formula-like strings that the validator rejects.

What the tests prove:

- **(a)** Python matrices and `EXPECTED_SAVED_VALUES.json` equal writer004 `prepareMatrices` (node + stub) on every fixture, byte for byte and structurally. A 3,000-value `JSON.stringify` fuzz test agrees with node.
- **(b)** Write → saved_qa round trips show 0 mismatches, and the checkpoint045 saved QA passes. Four tampered workbooks are detected. Repeated builds are byte-identical.
- **(c)** Every invalid carrier is refused at the expected stage with the expected code, and leaves no output. The suite confirms which refusals come from writer004 itself and which are portable-only. Usage, existing-output and unpinned-writer refusals are also covered.
- **(d)** `visual_qa` produces PNGs for every sheet, every page maps to its sheet, the manifest hashes match the files, renders are reproducible, `--sheets` renders exactly the selected sheets' pages of the 407-item fixture, and exact mode works. A mode-v2 output renders every sheet.
- **(e) Mode v2.** The suite runs the 046f route's own `make_fixtures.py` and route v4 `convert` to get two invented carriers, one with and one without M/N selection evidence. It derives 6 valid and 9 invalid v2 variants. The tests show:
  - writer004 refuses the original M/N carrier, and mode v1 still refuses it;
  - the writer's placeholder copy equals a test-side implementation of the documented method;
  - every valid v2 output has saved values equal to writer004 `prepareMatrices` on an independently built placeholder copy, except exactly the M/N evidence cells, which keep writer004's selection-evidence form;
  - the receipt records the relaxation; saved QA and the checkpoint045 saved QA pass; repeated builds are byte-identical;
  - a carrier without M/N selection evidence gives the same bytes in v1 and v2;
  - each invalid v2 variant is refused at the expected stage with the expected code.

Latest run (2026-11-04, author's run, not a review): 169 of 169 tests passed, with 11 valid and 21 invalid v1 fixtures and 6 valid and 9 invalid v2 fixtures; visual tests included; writer004 archived original. The same suite without visual tests also passed (159 of 159) against the public writer004 copy. That run used writer_portable.py `1cfe9ec9…b4fd`, saved_qa.py `4db50b42…e89c`, visual_qa.py `ebfcb352…d59a`, writer004_matrices.mjs `028dbdae…b3f8` and route v4 `cps046b_route.py` `b01f34f5…fdfd`. The previous run (2026-11-03, before mode v2) passed 118 of 118. The suite writes `EXPORT_TEST_RESULTS.json` in the work directory.

## Admission checklist for the independent reviewer

- Re-run the tests from a fresh work directory and confirm the writer pins.
- Read `prepare_matrices`/`_review_rows` against writer004 lines 135–168, and `_format_sheet` against lines 152–158 and 184–191.
- Decide whether L2–L5 are acceptable for CPS saved QA, or whether they need owner decisions.
- Inspect a full `visual_qa` PNG set for one invented carrier.
- Mode v2: read `o13_placeholder_copy`, `o13_matrix_difference` and the v2 branch of `build` against the method above; confirm from the route tests that the route v4 port differs from writer004 only in the L/M/N selection-evidence check; decide whether L10 is acceptable and whether the route port should be pinned by sha256 rather than by `VERSION`.
- Record the admission decision outside this README. Until then the route stays NOT ADMITTED.
