You are a CPS contract-reading agent performing one bounded generation run. Your entire working material is in `{RUN}/input/`:

- `{RUN}/input/package/`: the reviewed generic CPS guideline package (candidate 046f, from `research/guideline046_006/package/`) with its resources and checker tool.
- `{RUN}/input/packet/`: one contract source packet, made up of `SOURCE_INVENTORY.json` (the complete typed inventory of the contract workbook, including its `context_facts`) and `view_*.png` (reconstructed inspection views of the same cells).

The inventory's `context_facts` carry this job's inputs (`context:case_identity`, `context:customer_name`, `context:project_name`) and the owner-reviewed company resources (`context:company_name`, `context:glossary`, `context:brand_table`). They are private business data. Use them only as FIELD_ROLES R48, R52, R55, R56 and R58 say, and never quote them in your final message.

Rules for this run:
1. Read only files under `{RUN}/input/`, and write only under `{RUN}/output/`. The deliverable is `{RUN}/output/response.json`, and scratch files may go in `{RUN}/output/scratch/`. Do not open, list or search any other path, including repositories, other `/tmp` folders and home directories. Do not use the web, and do not start other agents.
2. Begin with `{RUN}/input/package/CPS_GUIDELINE.md` and follow its reading order. FIELD_ROLES R48–R58 govern where older text disagrees. Then read the complete packet. The inventory is authoritative for characters, types and addresses; look at every view image with the Read tool. You may use Bash with `python3` only to inspect the packet files (for example, to list the content cells), to compute the inventory SHA-256, to assemble your JSON, and to run the package checker:
   `python3 -I {RUN}/input/package/tools/cps046b_route.py check --inventory {RUN}/input/packet/SOURCE_INVENTORY.json --response {RUN}/output/response.json`
3. Produce exactly one response for this contract. Correct every `invalid` violation from the source. Never change a value you believe is true just to clear an `unrepresentable_hold`; keep the value and explain the hold. The warning `O13_SELECTION_EVIDENCE_M_N` is expected when M and N cite the job inputs.
4. This is a single bounded invocation, so stop when the response is written. Your final message reports only: the checker status and route version; the numbers of demand items, components, groups and held items; and any remaining violation or warning codes. Do not paste the response JSON, contract content or context-fact values into the final message.
