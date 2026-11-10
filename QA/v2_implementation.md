# v2.0 implementation and verification

## Decisions

- SPEC 2.0 takes priority. Section 7.3 is marked approved. Section 12's older
  pending wording is treated as superseded by that approval.
- Latest user revision supersedes the original direct-end policy: no automatic-end
  checkbox; blank end means known VOD end or unknown-length TXT data end.
- Python 3.10+ and standard-library Tkinter; requests is the only runtime dependency.
- Legacy keyword limit is 10 characters; detail log defaults to true.
- Rankings retain v1.3's TOP*3 candidate pool, initial TOP selection, chronological
  adjacent merge, candidate replenishment and ordering by best constituent rank.
  Merged groups do not invent an aggregate score. Individual rows remain visible.
- SPEC 2.0 corrects v1.3's keyword rate: matching messages / all messages, not
  repeated keyword count / all messages. Zero previous average is N/A.
- Old CLI remains available with --legacy-cli. Normal startup uses the v2 GUI.
- The user subsequently supplied four legacy collection/analysis pairs under
  멀럭킹. The reader and readable report layout are verified against those examples.

## Data and file policies

- Settings: %APPDATA%/ChzzkVodChat/CVC_settings.json. Apply validates, saves and
  activates options atomically; cancel discards edits. Corrupt input is backed up and replaced. Legacy setting
  files beside the source are migrated without modifying the source file.
- Output: Documents/ChzzkVodChat by default; configurable. Unique temp files and
  atomic publication prevent partial results and overwrites across windows.
  Windows uses non-replacing rename; other platforms use non-replacing hard links.
- New TXT uses a readable metadata block and [time][nickname] "message" rows.
  Latest revision prints whole seconds only (optional :00), retaining original
  precision internally and stable message order. Message/nickname escapes
  preserve brackets, quotes, newlines and Unicode. Whole-second normal rows resemble
  v1.3 output. The reader also supports the initial v2 JSON-row format and multiline
  v1.3 messages. New files should be analyzed with the v2 reader.
- Collected messages are passed directly to analysis. No temporary collection TXT
  is written in analysis-only mode. TXT-tab data is loaded once, cached for repeated
  analysis. Multiple files have independent inputs and immutable execution snapshots;
  removing and readding refreshes data. Deleted-file responses are discarded.
- Collection holds compact Chat records and only overlap-boundary deduplication
  keys. Identical messages without server IDs retain page multiplicity. Perfect
  identity cannot be established if the API omits IDs and changes page multiplicities.
- Pagination uses inclusive overlap and expands saturated same-time pages up to
  3200 rows. A stalled or saturated response fails instead of claiming completeness.

## Executed verification

- Latest narrow GUI revision: one targeted native Tk test passed for removal of
  the URL + button tooltip, URL-end autofill/manual-edit preservation and option
  wheel clamping at both content boundaries. The full suite was not rerun.

- Initial verification: 19 core tests and 6 native Tk widget tests passed.
- Revision verification adds native multi-file, wheel/date/placeholder and option
  persistence checks plus all four actual legacy files (149,189 messages, including
  five multiline messages). The format roundtrip preserves all messages.
- Final revision run: 31 tests passed (21 core, 9 native Tk, 1 corpus integration
  test covering all four files). Previous v2 JSON rows remain readable.
- Additional revision: 37 tests passed (25 core, 11 native Tk, 1 corpus test).
  New checks cover in-place URL-card conversion, source-specific tooltips, all
  option descriptions, whole-second output, report heading order, computed end,
  persisted completion receipts, input-change reruns, missing-result reruns and
  migration of readable pre-receipt results with identifiable range/keyword.
- Offline previews of all three tabs were captured and visually inspected at
  980x820; cards, input labels and action buttons fit without overlap.
- PyInstaller 6.21.0 Windows single-file windowed EXE built with the existing
  icon (embedded resource and bundled window icon). The built EXE was launched;
  its ChzzkVodChat v2.0 window reported Responding=True and closed normally.
- GUI checks instantiate actual Tk widgets and test independent inputs, manual-end
  retention, maximum count, output toggles, deletion/readdition, stale generations,
  execution snapshots and duplicate start prevention.
  Event-loop callbacks also execute while a background worker is active.
- Core coverage: interval 1..10, subsecond boundaries, partial ranges, zero buckets,
  automatic known-duration endpoint, explicit exclusive end, unknown duration,
  moving-average math, matching-message ratio, repeat limit, merge limits/replenishment,
  legacy and new TXT, all four time-display combinations, collision/cancel cleanup,
  settings repair/migration, overlapping API pages and three pipeline output modes.
- Fake API tests verify pagination behavior, not the live service contract.

## Not verified / remaining limitations

- Live public metadata was fetched for VOD 15944884: liveOpenDate was
  2026-10-30 18:02:05, publishDate was 2026-10-31 05:22:26 and duration was
  40078 seconds. The calculated end is 2026-10-31 05:10:03 KST, explicitly labeled
  as calculated, not an independently fetched actual end. The liveOpenDate field
  is also described in the [library author's type definition](https://github.com/kimcore/chzzk/blob/main/src/api/video.ts).
- No live full-chat collection was performed. Inclusive cursor semantics and larger
  previousVideoChatSize values need live verification; server caps can cause a
  deliberate incomplete-collection error.
- liveOpenDate supplies the broadcast date/start (KST); publishDate remains the
  legacy filename date and is shown separately as the posting date. Missing or
  invalid liveOpenDate leaves start/end unknown. Individual chat absolute-time
  semantics remain unverified and actual-time output can still be unknown.
- Completion receipts are independent of settings defaults and preserve the last
  successful range/keyword and published paths per VOD/output directory. Failed
  or cancelled jobs do not record success. Older ambiguous reports cannot prove
  an identical request and are rerun rather than incorrectly skipped.
- Unknown-duration URL collection cannot safely initialize the legacy backwards
  cursor and reports an error. TXT analysis supports unknown duration.
- Window movement during a long real collection, Premiere paste,
  real network retry/auth cases, disk-full/read-only destinations,
  and concurrent separate processes were not exercised.
- GUI uses standard ttk styling. No dashboard or drag/drop was added.

## Acceptance mapping

| Acceptance IDs | Evidence |
|---|---|
| GUI-02, UX-01..09 | native Tk tests, input validation and offline layout inspection; latest blank-end policy overrides UX-06 |
| BUCKET-01..05, MIN-01..05 | core boundary, partial-range, statistics and merge tests |
| FLOW-01,03,04 | fake-API pipeline tests |
| FLOW-02, META-01,02, TC-01,02 | reader roundtrip and shared analysis tests; live metadata pending |
| CFG-01,02 | settings and legacy migration tests |
| DATA-01 | overlap fixture including identical timestamps; live API pending |
| ANALYSIS-01,02, MERGE-01 | statistics and merge fixtures |
| FILE-01, STOP-01 | collision and cancelled-write tests; manual OS/network cases pending |
| GUI-01, CLOCK-01,02, TC-03 | implemented paths; full real-world/manual verification pending |
