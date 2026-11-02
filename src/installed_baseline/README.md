# Previously installed deterministic CPS baseline

This folder is the installed baseline snapshot, not the checkpoint045 semantic reader and not deployment-approved software. Its synthetic tests and mechanical verification are limited to this implementation. Current project work is paused.

See [architecture](../../docs/implementation/ARCHITECTURE.md) and [local prerequisites](../../docs/implementation/LOCAL_SETUP.md) before using any source file. The historical runtime README is retained for interface detail; its command examples do not override the pause or provide missing private manifests. The PowerShell launcher has a `.txt` suffix because it is a reference with placeholder host paths, not a portable entrypoint.

`runtime/cps.py` and the generation path read only allowlisted contracts. `eligibility/screen_targets.py` is an evaluation-only target screen; its observations must not become generation inputs. A screen with no detected dimension plus sign is not proof of genuine 未填 stage or a compatible source/target pair.
