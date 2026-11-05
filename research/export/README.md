# CPS portable export route (writer004 reproduction)

**Status: NOT ADMITTED.** Built 2026-11-03 under the owner decision to add a portable writer so CPS can run saved 17-column workbook QA and visual QA. The admitted writer, `writer004.mjs`, needs `@oai/artifact-tool` and a Windows source-verification helper, and neither exists here (DECISIONS_046b R2). Nothing in this directory may be used for CPS saved-cell QA, visual QA or deployment evidence until an independent reviewer (not the author) admits it. A successful run or a passing test is not admission.

**Mode v2 (added 2026-11-04 for candidate 046f, extended the same day for route v4.1 and v4.2; also NOT ADMITTED).** Route v4.2 (`cps046f-route.v4.2`; its writer port and relaxations are those of route v4.1) makes carriers that the archived writer004 gate refuses in exactly two documented ways: M and N proven by job inputs are carried as `selection_evidence` (owner decision O13; writer004 accepts it for L only), and a row whose C is null may have status `research_draft` (FIELD_ROLES R52, R57; writer004 requires `held`). A third route v4.1 relaxation, Q under unverified adoption (R54, O16), needs nothing here, because writer004 never reads the adoption status. Mode v2 relaxes exactly those two checks, by the method in "Mode v2" below. Mode v1 (the default) is unchanged.

**Review 2026-11-04 (independent reviewer): ADMIT_AFTER_LISTED_FIXES.** The reviewer listed four required fixes (S1 pin the node environment, S2 saved-QA structural strictness, S3 provenance of `EXPECTED_SAVED_VALUES.json`, S4 visual-QA limitations in the manifest) and two notes (N1 page mapping by a unique header marker, N2 README notes and conditions of use). Writer v2.3, saved_qa v2 and visual_qa v2 apply them; see "Review fixes (v2.3)" and "Conditions of use" below. The route stays **NOT ADMITTED** until a reviewer confirms the fixes and records the admission outside this README.

This directory holds code and invented test fixtures only. Do not commit case carriers, outputs, renders or reports made from case data. Write those outside the repository.

## Files

| File | Role |
|---|---|
| `writer_portable.py` | Carrier → `research-draft.xlsx`, `EXPECTED_SAVED_VALUES.json` and `WRITER_RECEIPT.json` |
| `writer004_matrices.mjs` | Runtime cross-check. Runs the archived writer004 `prepareMatrices` in node and prints the `EXPECTED_SAVED_VALUES.json` text writer004 would save |
| `saved_qa.py` | Reopens the saved workbook and compares every cell with `EXPECTED_SAVED_VALUES.json`, checks the package structure, and with `--carrier`/`--writer-dir` the provenance of `EXPECTED_SAVED_VALUES.json`; then writes `SAVED_QA.json` |
| `visual_qa.py` | LibreOffice PDF → pdftoppm PNGs, then writes `VISUAL_QA_MANIFEST.json` (with the render's limits and the cells that may be clipped). A reviewer makes the visual judgement later |
| `tests/run_export_tests.py` | Test suite (invented fixtures). Prints a JSON summary |
| `tests/make_export_fixtures.py` | Builds invented carrier variants from the 046d route-test fixture carrier |
| `tests/make_tamper_fixtures.py` | Rebuilds the reviewer's invented fidelity probe carrier from `v01_base`, and from its writer output the reviewer's 22 tampered outputs plus extra structural tampers (review S2, S3) |
| `tests/make_export_fixtures_v2.py` | Builds invented mode-v2 variants from six 046f route v4.2 carriers: job inputs (M/N selection evidence), plain, C-null research_draft, Q under unverified adoption, all three together, and the package example |
| `tests/parity_matrices.mjs`, `tests/stringify_fuzz.mjs` | Test-only node probes, written separately from the runtime cross-check |

## Route

0. **Node environment (v2.3, review S1).** Every node process the writer starts runs with every `NODE_*` variable removed from its environment (`NODE_OPTIONS`, `NODE_PATH`, `NODE_EXTRA_CA_CERTS`, …), so no `--import`, `--require` or loader hook and no global module path can reach writer004. The writer directory is used by its real path, and each pinned writer file must be a regular file in it (`WRITER_FILE_OUTSIDE_WRITER_DIR`): node resolves imports from a module's real path, so a symlinked `validate_carrier_v4.mjs` would load `writer004.mjs` and `@oai/artifact-tool` from elsewhere. Before any other node run, `@oai/artifact-tool` is resolved the way node resolves it from `writer004.mjs`: `createRequire(<writer004.mjs URL>).resolve('@oai/artifact-tool')`, and also `import.meta.resolve` from the writer directory (writer004 imports it as ESM); the two must name the same file (`ARTIFACT_TOOL_RESOLUTION_DIVERGES`, for example conditional `exports`). The file must have the stub's sha256 `67134acad4326089bca7cd074c753bda88887a64c6a1499d15e1153d673796a4` (`ARTIFACT_TOOL_NOT_PINNED`) and its `package.json` the documented content (`ARTIFACT_TOOL_PACKAGE_UNEXPECTED`); an unresolvable specifier is `ARTIFACT_TOOL_UNRESOLVED`. The receipt's `node_environment` records the removed variable names, the node executable and version, and the resolved stub path and sha256.
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

## Mode v2: route v4.1 relaxations for 046f carriers (route v4.2)

`--mode v2` is for carriers made by route v4.2 (`research/guideline046_006/package/tools/cps046b_route.py`, `cps046f-route.v4.2`), which keeps the route v4.1 relaxations unchanged and adds only response checks (R48/R56 policy checks). The route's convert receipt says when it is needed (`export_mode_required`, with one entry per relaxation class).

The route's Python writer port `validate_carrier_port` is writer004's validateCarrier plus the prepareMatrices review-cell check, with the relaxations listed in its `PORT_RELAXATIONS`; `validate_carrier_port(c, strict=True)` applies none of them. The route tests show by parity fuzzing that the strict port equals node writer004 on every fuzz carrier, and that every divergence of the relaxed port falls in one of the classes below.

| Class | Carrier feature | writer004 check | Neutralization in the placeholder copy |
|---|---|---|---|
| `o13_m_n_selection_evidence` | an evidence object for column M or N that holds `selection_evidence` (O13, R48) | `SELECTION_ONLY_ENGINEERING_ID` | The object loses `selection_evidence` and gains `location` = the item's own `location`, `anchor` = the item's `anchor` and `raw_text` = the `selection_evidence` text. `transformation` and any other key are unchanged, so a malformed object stays malformed. |
| `r57_null_c_research_draft` | an item or component with `values[2]` (C) null and `status` `research_draft` (R52, R57) | `UNRESOLVED_ITEM_MUST_BE_HELD` | `status` becomes `held`. When `review_reasons` is an empty list, it becomes the one placeholder reason `R57 relaxation placeholder: C is null with status research_draft in the carrier; status held and this reason exist only in the writer004 validation copy.` (writer004 requires a reason for `held`). A non-list `review_reasons` is left unchanged, so writer004 still refuses it. Values, raw, evidence and `null_reasons` are unchanged, so the null reason for C is still required. |
| `o16_q_unverified_adoption` | a non-null Q while `metadata.source_adoption` is not `verified` (R54, O16) | none: writer004 never reads the adoption status | None. Q and the metadata stay unchanged, in the copy and on the v1 route. |

Nothing else in the carrier changes in the copy: groups, nonitems, metadata, limitations and every other item are copied unchanged.

- **Carrier without the first two classes** (including a carrier whose only relaxation is O16): exactly the v1 route above. The output bytes equal mode v1. The receipt still lists the O16 items.
- **Carrier with an O13 or R57 class:**
  1. **Placeholder copy** as in the table. The copy has the shape writer004 requires, and the item's own location is valid by construction.
  2. **Gate (both must pass).** writer004 `validate_carrier_v4.mjs` runs unchanged on the copy (stage `gate:validate_carrier_v4:placeholder_copy`). The route v4.2 Python port `validate_carrier_port` runs on the original carrier (stage `gate:route_v4_port`). The port is pinned by sha256 (`ROUTE_V4_SHA256` in `writer_portable.py`; 046f review N3): the writer reads the file once, refuses it unless its sha256 equals the pin (`ROUTE_V4_TOOL_NOT_PINNED`), executes exactly those bytes, then checks the port's `VERSION` and its `PORT_RELAXATIONS` keys, and records its sha256. Any change to the route file therefore needs a writer update and a re-run of these tests.
  3. **Cross-check.** writer004 `prepareMatrices` runs on the copy and must be byte-identical to the Python matrices of the copy (stage `cross_check:placeholder_copy`).
  4. **Allowed difference.** The Python matrices of the original carrier, which are saved, may differ from the copy's matrices only in these review-sheet cells. The rows of both matrices are aligned from writer004's review-row layout of each carrier, so every row is accounted for:
     - O13: columns C–E (evidence location, anchor and JSON text) of each `欄位依據 <id>.M` or `<id>.N` row of a field with selection evidence. The original has writer004's own selection-evidence form there: an empty location, the anchor `"已核對工程選取"` and the JSON of the selection evidence. That is the code path writer004 uses for L.
     - R57: column G (`狀態`) of every review row of the item (`research_draft` in the original, `held` in the copy).
     - R57 with an added placeholder reason: column F of the item's `項目` row (`[]` in the original), and the copy's one extra `待確認 <id>.1` row holding the placeholder reason, which the saved matrices do not have.
     Main, component and link sheets must be identical. Any other difference refuses the carrier (`RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS`); a relaxed cell or added row without the documented form refuses it too (`RELAXATION_DIFF_FORM`).
  5. **Receipt.** `WRITER_RECEIPT.json` records `mode` and a `relaxations` section: the three classes with their fields or items and their neutralization text, the placeholder-copy sha256, the route port path, sha256 and version, the copy cross-check, every differing cell (saved-matrix coordinates) and the rows added in the copy. It also adds an extra limitation. `expected_saved_values.identical_to_writer004_prepareMatrices_output` is `false`, with `identical_to_writer004_prepareMatrices_on_placeholder_copy_except_documented_cells: true`.
- **Refusals in mode v2.** Selection evidence on any column other than L, M or N is still refused by writer004 on the copy (`SELECTION_ONLY_ENGINEERING_ID`). Path-like or malformed M/N selection evidence is refused by writer004 on the copy or by the route port. A null C without a nonblank null reason, a non-list `review_reasons` and any other status are refused by writer004 on the copy. Every other writer004 refusal is unchanged.

## Review fixes (v2.3)

| Item | Reviewer's fix | Where |
|---|---|---|
| S1 | Pin the node environment: resolve `@oai/artifact-tool` as node does from `writer004.mjs`, refuse unless it is the pinned stub, run node without any `NODE_*` variable, record the resolved path | Route step 0; `writer_portable.py` `node_env`, `check_writer_dir`, `check_node_environment`; receipt `node_environment`; tests (f) |
| S2 | saved_qa structural strictness: 12-part whitelist, worksheet-child whitelist, `state="visible"`, no `hidden`/`zeroHeight`, unknown cell types as findings, missing receipt fails | "How to run", `saved_qa.py` bullets; `check_structure`, `read_raw`; tests (g) |
| S3 | Provenance of EXPECTED: `--carrier`, `--writer-dir`; carrier sha256 vs receipt; v1 rerun of `writer004_matrices.mjs`, v2 rerun of the writer, byte comparisons | `saved_qa.py` `check_provenance`; report `expected_provenance`; tests (h) |
| S4 | visual_qa limitations in the manifest (General format, page-high rows clipped, `complete_render` meaning) and the cells that may be clipped | `visual_qa.py` manifest `limitations`, `possibly_clipped_cells`; tests (i), (d) |
| N1 | Page mapping by a unique header marker | `visual_qa.py` header `&L[[&A]]`, `map_pages`; tests (i) |
| N2 | README: never re-save via LibreOffice for QA; subnormals may flush in Excel; the reviewer's conditions of use | "QA notes", "Conditions of use" |

Every one of the reviewer's 22 tampers is caught. T21 (a consistent replacement of `EXPECTED_SAVED_VALUES.json` and the xlsx with the receipt hashes updated) is caught only with `--carrier` and `--writer-dir`, which is why the conditions of use require them for CPS evidence. Output bytes are unchanged from v2.2 (the fixes add checks and receipt fields, not workbook content).

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
| L10 | **Mode v2 is not writer004 on the original carrier.** For a carrier with M/N selection evidence or a C-null `research_draft` row, writer004 validates and builds matrices only on the placeholder copy. The relaxed checks come from the sha256-pinned route v4.2 port. The saved review cells of the M/N fields come from the Python reimplementation of writer004's selection-evidence branch (the branch used for L); the saved status cells of R57 rows say `research_draft`, a status writer004 never wrote for a null C. | Mode v2 above; route tests `writer_port_strict_equals_writer004_on_every_carrier`, `writer_port_parity_fuzz_every_divergence_classified`, `writer_port_relaxed_accept_implies_writer004_accepts_neutralized_copy`. |

### Extra refusals (the portable writer refuses carriers writer004 might accept)

- **Non-UTF-8 carrier bytes** (`UTF8_REQUIRED`). Node decodes them with U+FFFD and accepts.
- **A written cell string containing a lone surrogate, U+FFFE or U+FFFF** (`PORTABLE_UNREPRESENTABLE` / `XML_UNREPRESENTABLE_CHARACTER`). XML 1.0 cannot carry these. A lone surrogate that occurs only inside a JSON-encoded review cell is escaped by `JSON.stringify` and is written normally.
- **A literal OOXML escape sequence `_xHHHH_` in written text** (`LITERAL_OOXML_ESCAPE_SEQUENCE`). Spreadsheet applications decode it: LibreOffice reads an openpyxl-written `_x0041_` as `A` (measured), and openpyxl writes it unescaped. Escaping it as `_x005F_x0041_` would also make openpyxl readback differ from the value, so the route refuses. Partial patterns such as `AB_x12_` or `_x004` are fine.
- **Any difference between the Python and node matrices** (`CROSS_CHECK_MISMATCH`).
- **A node environment other than the pinned one** (stage `gate:node_environment` or `gate`): `ARTIFACT_TOOL_UNRESOLVED`, `ARTIFACT_TOOL_RESOLUTION_DIVERGES`, `ARTIFACT_TOOL_NOT_PINNED`, `ARTIFACT_TOOL_PACKAGE_UNEXPECTED`, `WRITER_FILE_OUTSIDE_WRITER_DIR`, `NODE_UNAVAILABLE`. writer004 itself would run with whatever node resolves.
- **Mode v2:** any difference between the saved matrices and writer004's matrices of the placeholder copy outside the documented cells (`RELAXATION_DIFF_OUTSIDE_DOCUMENTED_CELLS`, `RELAXATION_DIFF_FORM`), any refusal by the route v4.2 port, a route tool whose bytes are not the pinned ones (`ROUTE_V4_TOOL_NOT_PINNED`, checked before it runs), and a pinned route tool whose `VERSION` or `PORT_RELAXATIONS` keys differ (`ROUTE_V4_TOOL_VERSION`, `ROUTE_V4_TOOL_RELAXATIONS`).

## How to run

Prerequisites:

- `python3` with openpyxl 3.1.5 (lxml is used if present);
- node 22;
- LibreOffice (`soffice`) and poppler (`pdftoppm`, `pdfinfo`, `pdftotext`) for visual QA;
- the archived writer directory, with `@oai/artifact-tool` resolvable from it.

The CPS validation stub is enough for the writer directory. Put the stub at `<writer-dir>/../node_modules/@oai/artifact-tool/` as `index.mjs` (sha256 `67134acad4326089bca7cd074c753bda88887a64c6a1499d15e1153d673796a4`, exports `Workbook.create` and `SpreadsheetFile.exportXlsx`, which both throw) and `package.json` (`{"name":"@oai/artifact-tool","version":"0.0.0-cps-validation-stub","type":"module","main":"index.mjs","exports":"./index.mjs"}`). Nothing else named `@oai/artifact-tool` may be resolvable first from the writer directory (for example `<writer-dir>/node_modules`): the writer resolves the specifier as node does and refuses anything but this stub.

```sh
W=/abs/route/writer                      # writer004.mjs, validate_carrier_v4.mjs, receipt_bytes.mjs
python3 -I -B research/export/writer_portable.py --carrier /abs/carrier.json --out /abs/new-output --writer-dir "$W"
#   --mode v2             candidate 046f carriers (route v4.2 with the v4.1 relaxations: M/N job-input selection evidence, C-null research_draft); default v1
python3 -I -B research/export/saved_qa.py --output-dir /abs/new-output --carrier /abs/carrier.json --writer-dir "$W"   # writes SAVED_QA.json there
#   --carrier/--writer-dir  required for CPS evidence: checks the provenance of EXPECTED_SAVED_VALUES.json (omit both: not checked)
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
  - `WRITER_RECEIPT.json` exists (v2) and its integrity hashes match;
  - **structure (v2, review S2; always checked):** the zip holds exactly the 12 parts the writer produces (`[Content_Types].xml`, `_rels/.rels`, `docProps/app.xml`, `docProps/core.xml`, `xl/workbook.xml`, `xl/_rels/workbook.xml.rels`, `xl/styles.xml`, `xl/theme/theme1.xml`, `xl/worksheets/sheet1.xml`–`sheet4.xml`), with no duplicate entry; every worksheet's children are only `sheetPr`, `dimension`, `sheetViews`, `sheetFormatPr`, `cols`, `sheetData`, `pageMargins`, in that order (no conditional formatting, data validation, drawing or other element); every sheet has `state="visible"` and the workbook window is visible; no `hidden` or `zeroHeight` attribute with a true value anywhere (openpyxl itself writes `hidden="0"` on the Normal cell style, so a false value is allowed); the writer's attributes only on `sheetView` (no zoom, `showZeros` or other view attribute), `sheetFormatPr` (`baseColWidth="8" defaultRowHeight="15"`), `col`, `row` (a height only on row 1, 36 pt), cell and `<t>`; an inline string is one plain `<t>` (no rich-text runs with their own font); text with leading or trailing whitespace carries `xml:space="preserve"` (applications may drop it otherwise); cell formats hold only an `alignment` with `horizontal`, `vertical`, `wrapText`. A cell type outside `n`, `s`, `inlineStr`, `b`, `e`, `str` (for example `t="d"`) or unparsable number text is a finding (`unknown_cell_type`, `unparsable_number`); no input crashes the script: a reader that fails is a `reader_error` finding, and any other exception still writes a failed report;
  - **provenance of `EXPECTED_SAVED_VALUES.json` (v2, review S3; with `--carrier` and `--writer-dir`):** the carrier's sha256 must equal the receipt's `input_carrier.sha256`. Receipt mode `v1`: `writer004_matrices.mjs` reruns writer004 `prepareMatrices` on the carrier, with the same pinned writer files, pinned stub and `NODE_*`-free environment as the writer (S1), and its text must be byte-identical to `EXPECTED_SAVED_VALUES.json`. Receipt mode `v2`, or no receipt: `writer_portable.py --mode v2` reruns into a temporary directory and both `EXPECTED_SAVED_VALUES.json` and the xlsx must be byte-identical (builds are reproducible; v2 gives the v1 bytes for a carrier without O13/R57). The result is `expected_provenance` in the report. Without the two options, `expected_provenance.checked` is `false`: a consistent replacement of `EXPECTED_SAVED_VALUES.json` and the workbook, with the receipt hashes updated, then passes (reviewer tamper T21). In mode v1 the provenance check does not regenerate the xlsx: its fidelity to `EXPECTED_SAVED_VALUES.json` is the three-reader comparison plus the structure and formatting checks;
  - unless `--no-formatting` is given, the formatting listed above.

  The original `research/checkpoint045/postqa/qa_saved_external.py` also runs unchanged on the same output layout.
- **`visual_qa.py`.** Default mode is `fit-width`. The temporary render copy gets print settings only: landscape A3, one page wide, header row repeated, page header = `[[sheet name]]` and page number. Pages are mapped to sheets by that `[[sheet name]]` marker in the page header (v2, review N1); before v2 the mapping searched the first lines of each page for any sheet name, which cell text near the top of a page could match. The tool verifies that every sheet's `<sheetData>` bytes are unchanged, and that the saved workbook is unchanged after rendering. PNG pixels are reproducible run to run; PDF bytes are not, because of LibreOffice metadata. Scale: a 407-item invented carrier (about 10,000 review rows) gave 434 A3 pages in about 4 minutes at 100 dpi.

  What the render does not show (v2, review S4; also in the manifest `limitations`):
  - numbers display in the General format, so the rendered text is rounded (at most about 10 significant digits, fewer in narrow columns) and the stored binary64 precision (0.30000000000000004, 5e-324) is not visible; saved QA checks the stored values;
  - a row taller than one printed page is clipped: LibreOffice does not split a row across pages (measured on the reviewer's invented 30,000-character cell: `pdftotext` finds 2,147 of its characters in the render);
  - `complete_render` means that every PDF page was rendered to a PNG, not that all text of every cell is visible.

  The manifest's `possibly_clipped_cells` lists, from the saved workbook itself, every string cell whose estimated wrapped height exceeds 409 pt, the Excel maximum row height (lines = sum over the cell's lines of ⌈width units / column width⌉, wide East Asian characters count 2, 15 pt per line). It is a heuristic: check the values of listed cells through saved QA, not in the PNGs.

### QA notes (review N2)

- **Never re-save the workbook with LibreOffice (or Excel, or any application) for QA.** Saved QA and visual QA run on the writer's bytes. A re-saved file is another workbook (string storage, number text, styles and types can change); its QA says nothing about the writer output. `visual_qa.py` renders a temporary copy and checks that the saved file is unchanged.
- **Subnormal numbers may flush to zero in Excel.** The workbook stores subnormal doubles such as 5e-324 exactly, and saved QA proves the stored text and value, but Excel may treat subnormals as 0 when it reads, displays or calculates them. The stored value is what CPS saved QA establishes.

## Conditions of use (review 2026-11-04)

These are the conditions under which the reviewer's ADMIT_AFTER_LISTED_FIXES verdict applies. They do not admit the route by themselves.

- **Modes.** Mode v1 (default) is for carriers that writer004 `validateCarrier` accepts unchanged; its `EXPECTED_SAVED_VALUES.json` is the text writer004 `prepareMatrices` gives for the carrier. Mode v2 is only for route v4.2 carriers of candidate 046f with the documented O13/R57 relaxations; its `EXPECTED_SAVED_VALUES.json` differs from writer004 `prepareMatrices` on the placeholder copy only in the documented review cells (L10), and a v2 run on a carrier without O13/R57 is the v1 route with the same bytes. Mode v2 is not a way past any other writer004 refusal.
- **What saved QA establishes**, when it passes with `--carrier` and `--writer-dir` (`expected_provenance.result` = `PASS`): the saved workbook holds exactly the values and types of `EXPECTED_SAVED_VALUES.json` in all four sheets, read by three readers that agree; `EXPECTED_SAVED_VALUES.json` comes from the carrier (v1: byte-identical to writer004 `prepareMatrices` on it; v2: byte-identical to a rerun, with the xlsx); the package holds only the writer's parts and nothing that hides or alters what a cell shows (structure list above); no formula; the writer004 formatting listed above. It does not establish source semantics, what `@oai/artifact-tool` would have saved (L2–L5), or how Excel displays the file. A saved QA without `--carrier`/`--writer-dir` is not CPS evidence.
- **What visual QA establishes:** reproducible PNG images of a LibreOffice rendering (fonts substituted, L9) of a print-settings copy, every page mapped to its sheet. The visual judgement is a separate reviewer's inspection of every PNG. It does not show stored number precision, text beyond a page-high row, or text of the `possibly_clipped_cells`.
- **Environment pins:** writer files by sha256 (`writer004.mjs` either pin, `validate_carrier_v4.mjs`, `receipt_bytes.mjs`) as regular files in the writer directory; `@oai/artifact-tool` resolving from `writer004.mjs` to the CPS validation stub `67134acad4326089bca7cd074c753bda88887a64c6a1499d15e1153d673796a4` with the documented `package.json`; every node process without `NODE_*` variables; in mode v2 the route v4.2 port by sha256 (`ROUTE_V4_SHA256`); node 22 and Python with openpyxl 3.1.5 (versions recorded in the receipt); LibreOffice and poppler versions recorded in the visual manifest. The receipt's `node_environment` and `writer_files`, and the saved-QA `expected_provenance`, are the record that these pins held.

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
- **(e) Mode v2.** The suite runs the 046f route's own `make_fixtures.py` and route v4.2 `convert` to get six invented carriers (job inputs and all-three on the fixtures' 046f job-packet inventory, the others on its pre-046f mechanics inventory): job inputs (M/N selection evidence), plain, C-null `research_draft` (one row with a review reason, one component without), Q under unverified adoption, all three classes together, and the package example. It derives 11 valid and 17 invalid v2 variants. The tests show:
  - writer004 refuses the original M/N and R57 carriers, mode v1 still refuses them, and writer004 accepts the Q-only carrier unchanged;
  - the writer's placeholder copy equals a test-side implementation of the documented method on all six carriers;
  - every relaxed v2 output has saved values equal to writer004 `prepareMatrices` on an independently built placeholder copy, except exactly the documented cells, by an independent content-based alignment; the cells equal the receipt's list, and the removed placeholder rows equal the receipt's added rows;
  - nine negative controls: hidden changes to the copy's matrices (metadata row, main sheet, status of an item without R57, status column of an O13 row, raw text of an R57 item, a nonitem row, the placeholder row's text or its removal, an R57 status left unchanged) are refused by the difference check;
  - the receipt records the classes; saved QA and the checkpoint045 saved QA pass; repeated builds are byte-identical;
  - a carrier without O13/R57 (plain, and Q only) gives the same bytes in v1 and v2;
  - each invalid v2 variant is refused at the expected stage with the expected code; the writer's pin equals the route file's sha256; a route tool with other bytes (one added comment, same `VERSION`) is refused before it runs; and a route tool with a different `VERSION`, even when the pin is pointed at it, is refused.
- **(f) Node environment (review S1).** For each attack the suite first shows that it works when node runs `validate_carrier_v4.mjs` directly (writer004 then accepts an invented carrier with status `partial`, which it otherwise refuses with `REVIEW_STATUS_REQUIRED`), then that the writer refuses it for that carrier and for a valid one, with no output: the reviewer's planted module (the `Array.prototype.includes` patch under `<writer-dir>/node_modules/@oai/artifact-tool`, verbatim) → `ARTIFACT_TOOL_NOT_PINNED`; conditional `exports` (require → the stub, import → the patch) → `ARTIFACT_TOOL_RESOLUTION_DIVERGES`; pinned writer files symlinked to a directory whose `node_modules` holds the patch → `WRITER_FILE_OUTSIDE_WRITER_DIR`. Also: a `package.json` other than the documented one → `ARTIFACT_TOOL_PACKAGE_UNEXPECTED`; `NODE_OPTIONS=--import=<patch>` changes writer004's verdict on direct node but not in the writer (it still refuses `partial` with `REVIEW_STATUS_REQUIRED`); a stub reachable only through `NODE_PATH` is not used (`ARTIFACT_TOOL_UNRESOLVED`); with `NODE_OPTIONS` and `NODE_PATH` set, a valid carrier gives the same bytes and the receipt names the removed variables; the receipt records the resolved stub path (require and import agree) and sha256; saved_qa's pins equal the writer's.
- **(g) Saved-QA structure (review S2).** `make_tamper_fixtures.py` rebuilds the reviewer's invented fidelity probe from `v01_base` (byte-identical to the reviewer's `p01_fidelity.json` when the base is the same) and, from its writer output, the reviewer's 22 tampers: T01–T20 as in the reviewer's scripts (T05 and T10 in their corrected form), T21 = consistent `EXPECTED_SAVED_VALUES.json` + xlsx change with the receipt hashes updated, T22 = the same with the receipt deleted; every tamper but T22 also has its receipt hashes updated, so the integrity check alone cannot catch it. Extra tampers: an added comments part, a white rich-text run, a hidden workbook window, `showZeros="0"`, a duplicate zip entry, `<protection hidden="1">`, a 1-pt row, an out-of-range style index, and a file that is not a zip; plus C1, the consistent change with a stale receipt. Every tamper must fail saved QA with its expected finding and without a crash, except T21, which passes without `--carrier`/`--writer-dir` (no structural check can tell a consistent replacement from the writer's output; that is the provenance check's job).

  | Tamper | Finding | Tamper | Finding |
  |---|---|---|---|
  | T01 number text rounded | `value_type_mismatch` | T12 `t="d"` date cell | `unknown_cell_type` (no crash) |
  | T02 text `123` → number | `value_type_mismatch` | T13 header text | `header_row` |
  | T03 formula with cached value | `formula` | T14 CR lost | `value_type_mismatch` |
  | T04 sheet order | `sheet_order` | T15 `xml:space` dropped on `' 0012 '` | `whitespace_not_preserved` |
  | T05 main sheet hidden | `sheet_state` | T16 print-area defined name | `defined_names` |
  | T06 column D hidden | `hidden_attribute` | T17 freeze removed | `formatting` |
  | T07 row 3 hidden | `hidden_attribute` | T18 data validation | `worksheet_structure` |
  | T08 `zeroHeight` | `hidden_attribute` | T19 zoom 10% | `worksheet_structure` |
  | T09 conditional white text | `worksheet_structure` | T20 white body font | `formatting` |
  | T10 `;;;` number format | `formatting` | T21 consistent, receipt updated | only `provenance` (with `--carrier`) |
  | T11 `t="str"` cell | `formula` | T22 consistent, receipt deleted | `integrity`, and `provenance` |

- **(h) Provenance (review S3).** With `--carrier` and `--writer-dir`: every valid v1 and v2 output passes (v1: byte-identical to writer004 `prepareMatrices`; v2: EXPECTED and xlsx byte-identical to the rerun); every tamper of (g) still fails, and T21, T22 and C1 fail with a `provenance` finding; on a relaxed v2 output, the consistent change (receipt stale, updated or deleted) and a zoom tamper with the receipt updated fail with a `provenance` finding (the rerun's xlsx differs); a carrier other than the receipt's, a relaxed v2 output whose receipt claims mode v1 (writer004 refuses its carrier), and the planted writer directory (v1 and v2 path) fail; `--carrier` without `--writer-dir` is a usage error.
- **(i) Visual-QA helpers (review S4, N1), without LibreOffice.** Pages map by the `[[sheet name]]` marker, not by any sheet name near the top of the page; the print patch writes the marker; `possibly_clipped_cells` lists the 16,000-character and 7,000-astral-character cells of `v05_long_text` and nothing in `v01_base`; the line estimate counts wide characters as 2 and line feeds as new lines. With visual tests, (d) also checks that the manifest states the three render limits and the no-re-save rule, that every modification names the marker, and that a render of `v05_long_text` lists its possibly clipped cells.

Latest run (2026-11-04, writer v2.3 engineer's run for the review fixes, not a review): 349 of 349 tests passed with visual tests (13 visual), against the archived writer004 original; without visual tests 336 of 336 passed against the archived original and 336 of 336 against the public writer004 copy. Fixtures: 11 valid and 21 invalid v1, 11 valid and 17 invalid v2, 32 saved-QA tampers of the fidelity probe (the reviewer's 22, 9 extra, C1) and 4 of a v2 output. All runs used writer_portable.py `f1c95537…0e21` (`cps-export-writer-portable.v2.3`), saved_qa.py `dc45c0de…ab63` (`cps-export-saved-qa.v2`), visual_qa.py `7b1f8ec1…e143` (`cps-export-visual-qa.v2`), writer004_matrices.mjs `028dbdae…b3f8` (unchanged), tests/make_tamper_fixtures.py `3464bbfd…b541` and route v4.2 `cps046b_route.py` `9db8033b…811d`, with `NODE_OPTIONS`, `NODE_PATH` and `NODE_EXTRA_CA_CERTS` set in the caller's environment (the writer removed them). The 24 workbook and `EXPECTED_SAVED_VALUES.json` outputs of the fixtures are byte-identical to the reviewer's v2.2 runs. Re-checked with these versions, the reviewer's own 22 tamper directories all fail saved QA (T21 only with `--carrier`/`--writer-dir`), and the writer refuses the reviewer's planted-module directory with `ARTIFACT_TOOL_NOT_PINNED`.

Before v2.3: 2026-11-04, route v4.2 (writer v2.2 `abdd9e61…8459`, saved_qa.py `4db50b42…e89c`, visual_qa.py `ebfcb352…d59a`), 224 of 224 with visual tests against the archived original and 213 of 213 without visual tests against the public copy.

Earlier runs: 2026-11-04 with route v4.1, 222 of 222 with visual tests (writer v2.1, route v4.1 `40639537…104e`); 2026-11-04 before route v4.1, 169 of 169 with visual tests (writer v2.0, route v4 `b01f34f5…fdfd`); 2026-11-03, before mode v2, 118 of 118.

## Admission checklist for the independent reviewer

- Re-run the tests from a fresh work directory and confirm the writer pins.
- Read `prepare_matrices`/`_review_rows` against writer004 lines 135–168, and `_format_sheet` against lines 152–158 and 184–191.
- Decide whether L2–L5 are acceptable for CPS saved QA, or whether they need owner decisions.
- Inspect a full `visual_qa` PNG set for one invented carrier.
- Mode v2: read `relaxation_scan`, `placeholder_copy`, `relaxation_matrix_difference` and the v2 branch of `build` against the method above; confirm from the route tests that the strict route port equals writer004 and that the relaxed port differs only in the documented classes; decide whether L10 is acceptable and whether a saved `research_draft` status on a null-C row is acceptable for CPS saved QA. (The route port is now pinned by sha256, as the 046f semantic review asked, N3.)
- v2.3 fixes: confirm S1 by the (f) tests (and by re-running the reviewer's planted-module demo), S2 by the 22 tampers of (g), S3 by (h), S4/N1 by (i) and the visual manifest, N2 by "QA notes" and "Conditions of use".
- Record the admission decision outside this README. Until then the route stays NOT ADMITTED.
