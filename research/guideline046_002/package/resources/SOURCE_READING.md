# Source reading and boundaries

Candidate046b (unchanged policy from 046a except the inventory note below). This is a source-only reading policy, not a new authorization to open project folders. For cell sources the supplied `SOURCE_INVENTORY.json` (`cps.source-inventory.cells.v2`) is the complete authoritative surface: every position, type, merge, view and limitation is recorded there; do not look for other files.

## Authority and completeness

The run context must identify exact allowed source files by hash, their roles and adoption evidence, included sheets/pages, verified identity namespaces and any missing referenced annex. Reject wrong bytes and undeclared sources. Metadata absence is not acceptance. Record unverified adoption separately from readable content; an unverified source can support a labelled research draft but not an accepted contract rate or business release.

Read every in-scope sheet/page and every physical cell or declared PDF region. Include headers, repeated headers, continuations, hidden content, footers, commercial cells, totals, analysis blocks and references. A complete census is not the same as an approved demand denominator. Every source region needs a disposition and all unresolved regions remain visible.

## Workbook surfaces

Preserve original text, formulas when accessible, saved caches, cell types, merges, covered-cell conflicts, hidden state, external-link metadata and original addresses. Never execute workbook content. A cache is an observation, not verified recalculation. Missing cache/formula errors are unusable states, not zero. Numeric zero, text "0", a true blank and an explicit empty string remain distinct in the original inventory even where a declared derived raw-field profile maps some of them to the same representation.

Use merged anchors for visible content; do not multiply hidden covered values across rows. Retain covered conflicts separately. A name/header spanning cells requires actual merge/continuation evidence. Reconstructed images are inspection aids: wrapping in an image does not create stored spaces/newlines. Do not correct stored spelling from a raster glyph.

XLSX, cached legacy XLS and ODS each require a truthful, validated adapter. Do not relabel one as another. A legacy adapter unable to expose formula expressions must declare that limitation. A new source format is held until its complete reading and output route is qualified.

## PDF surfaces

Use exact pinned PDF bytes, page numbers and source row/region locators. Compare extracted/OCR text to the visible page where text or layout is uncertain. Preserve ambiguity, line endings and item boundaries under the declared PDF profile; do not silently repair glyphs or supply a missing model from memory. Visual wraps in a scanned page and workbook continuation cells have different provenance. This candidate's new source-reference schema initially describes cell-based inventories; a PDF region adapter is not yet admitted by that schema.

## Logical items

Headers can span rows and columns. Resolve column roles from the actual table; fixed coordinates are not portable. Read a complete logical item before allocating names/specifications. Join description, specification and remark streams separately in source order. Prove continuation ownership; stop at a new item number, new section or conflicting heading. Preserve multiple raw fragments and their locators even when the derived name becomes one phrase.

Search for the supplied object in every supported field. A blank description with a genuine item name in the specification cell is not automatically a nonitem. Conversely, "see pump specification" in a reference field alone does not establish a supplied pump. Unit/quantity, numbering and semantics must establish the item, not a noun-list match.

## Hierarchy, analysis and unsupported scope

Distinguish locations, quotation sections, contractual panel groups and physical enclosure ownership. Preserve complete panel labels and position suffixes. A shared enclosure does not prove one enclosure per child. Quantity allocation is a separate fact.

Separate project demands from per-unit composition and financial summaries. Link analysis only with proven parent identity, unit and positive literal basis; retain conflicting/ambiguous links as held. Do not silently omit analysis components, multiply them into purchases or use resource summaries to invent absent demand rows.

Do not discover additional sources during a generator run. Missing material triggers an explicit limitation and separate database investigation under the governing task, not an opportunistic file search from a target-exposed context.
