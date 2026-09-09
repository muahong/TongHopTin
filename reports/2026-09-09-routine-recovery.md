# Routine recovery — 9 September 2026

The morning schedule ran at logon and again at 09:00, but both attempts failed during editorial generation. Collection succeeded: 405 articles in `output/runs/2026-09-09_075531_94ac7fec.json`. Neither failed attempt completed website publication.

## Cause and fix

The CLI returned HTTP 400: `The 'gpt-5.4-mini' model is not supported when using Codex with a ChatGPT account.` The existing subscription fallback caught quota exhaustion only. Consequently, even though Claude authentication was available, this explicit model/account rejection terminated the entire run.

Explicit model-unavailability errors now use the existing fallback, and disable Codex for the remainder of that process. Unrelated errors, such as invalid output schemas, still fail visibly. Parallel calls already in flight may each receive the rejection; subsequent batches avoid it. No API key, subscription purchase, or quota reset was introduced.

A second recovery defect was fixed: a successful backup after an editorial failure covers the crawl but not the future completed edition. Finishing editorial now invalidates that earlier backup checkpoint so new copy and rendered assets are archived before the website push.

During recovery, one Claude writing response omitted the beginning of its JSON object. It was rejected rather than cached or published. The malformed response was retained separately, and the batch was regenerated from its full original source prompt; all 16 completed batches were reused. Future malformed responses receive one bounded retry using the existing stronger repair tier. A second invalid response still fails visibly and is not cached.

Two later citation-repair responses were also malformed. The fallback now requests the Claude CLI native `--json-schema` output and reads its `structured_output` object; it rejects missing structured output instead of extracting text between braces. A live subscription smoke call passed. All 26 writing batches remained cached during this correction.

## Validation and scope

- 112 local tests passed, including unsupported-model fallback, stopping repeated rejected calls, preserving unrelated errors, backing up newly completed editorial output, and bounded malformed-JSON retry.
- [GitHub validation](https://github.com/muahong/TongHopTin/actions/runs/34321864481) passed for commit `b581be24d4195a9444b25ffa9249f6227401a4da`.
- Recovery was started through the existing `TongHopTin Startup` Windows task, reusing the frozen morning report. No second crawl was requested.
- Existing uncommitted performance, source-filter, policy and heartbeat changes were preserved. The repair commit stages only the relevant fallback/backup fixes and new tests.
- Source coverage remains partial. Scheduling and verified publication do not establish that all publishers were accessible or every generated sentence is factually correct.

## Verified outcome

The scheduled recovery completed at **14:11:51 UTC+7**, with Task Scheduler result **0**. The original 405 articles became 154 validated stories. No new crawl was required. Cached writing came from Claude; the final resumed repair/directory calls used Codex gpt-5.5. The edition backend field records that final process, not every earlier cached call.

- Private archive commit `79a721b229cedbd6fc737ae16a9428e5f9fad75e` matches remote HEAD. The new manifest records 1,831 changed/new paths and one pack. The archived rendered HTML was extracted and its bytes/hash matched the current output.
- Website commit `4f5552cf01c72078321b8ec3c63168660f4009f2` deployed successfully. Homepage SHA-256: `b1e1b9e772ece46caea7e42b45f1685ef8d96324483d208041cc7c6bf903d977`. The selected JSON/JS sidecars and image also matched committed bytes.
- Repeating the Startup task returned `Already verified: 2026-09-09-am`; the completed state hash was unchanged.
- Both existing schedules remain enabled: logon/09:00 morning fallback and 21:00 evening, UTC+7; wake and catch-up enabled; six retries every 30 minutes; four-hour execution limit. They use the signed-in Windows session. Tonight's future execution has not been observed.
- Detailed evidence: [routine-verification.json](2026-09-09-routine-verification.json).
