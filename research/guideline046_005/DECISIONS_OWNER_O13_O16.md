# Owner decisions O13–O16 (2026-11-04, after the creator-practice study)

The owner answered these through the session's question tool, choosing the recommended option each time. They apply from candidate 046f onward. They make the CPS reader reproduce the historical 未填 creator's majority practice, and they supply the information the contract does not contain (see STUDY_CREATOR_PRACTICE_20261104.md).

| ID | Question | Owner answer | Effect |
|---|---|---|---|
| O13 | Source of M (customer full name) and N (project name) | "Job inputs" | Whoever runs CPS supplies, with each job, the customer full name, the project short name and the internal case id. CPS copies them into M, N and L on every row. Nothing is inferred from letterheads; O2 stays in force for inference. |
| O14 | Brand and model (J/I) on priced device lines | "Company brand table" | A company default brand/model table by device type becomes a CPS resource. It is built from the creator's past non-reserved 未填 files and reviewed by the owner. CPS applies it, and a brand or model stated in the contract takes precedence. |
| O15 | Habitual Latin abbreviations in C | "Yes, use glossary" | A small abbreviation glossary (about 20 entries) becomes a CPS resource. It is built from her past non-reserved 未填 files and reviewed by the owner. A device without an entry keeps the contract noun. |
| O16 | Q, the not-estimated status text, and the enclosure row | "Adopt all" | Q = the quoted unit price on priced lines. I = J = 不含估價 on "not estimated" lines. The enclosure row gets A (enclosure type), B in the form W*H*D, and J = the company name, as the creator does. |

## Data boundaries

- **Building the tables.** The brand table and glossary are built only from non-reserved historical 未填 files. No reserved project is read.
- **The tables are company business data.** They are kept out of the public repository and supplied privately with each job packet, pinned by SHA-256 in every admission.
- **What a generator may receive.** Only the reviewed tables and the job inputs. It never receives historical 未填 rows, targets or evaluator data.
- **Effect on the AGENTS.md boundary.** "Do not supply … company selection habits" is relaxed solely for these owner-approved, reviewed tables (O14/O15).
