# Call Ingestion UI Design

## Intent

Restore a user-facing way to add calls without restoring the old folder-path
evaluation workflow. Operators need to import one call or a folder of calls
from either their computer or the existing backend artifact storage.

## Current state

- `POST /api/v1/interactions` accepts canonical interaction JSON.
- `POST /api/v1/interactions/{id}/events` accepts events and transcript turns.
- Artifact-reference registration stores metadata, not file bytes.
- The local `ArtifactStore` can store files, and audio review reads a
  tenant-scoped `ArtifactRow`.
- The existing sample corpus has 50 call directories under
  `backend/storage/artifacts/health_campaign`; a call folder can contain
  `call.json`, `recording.wav`, `call.log`, manifests, and per-turn WAV files.
- Existing mapping code reads `call.json`, maps its `call_id` to the canonical
  interaction ID, and extracts messages/turns. The old validator also requires
  `call.log` and `manifest.jsonl`; import validation must instead require only
  the agreed `call.json` and `recording.wav`, while preserving other files when
  present.

## Goals

- Add an **Import Calls** UI for one call folder and a folder containing
  multiple call folders.
- Support folders selected from the user's computer and calls already staged
  under the tenant's backend artifact directory.
- Require `call.json` and `recording.wav`; preserve other regular files in the
  call folder recursively as local artifacts when present.
- Use `call.json`'s stable `call_id` as the canonical interaction ID and map
  message/turn data into existing interaction and transcript storage.
- Treat the source folder name as display metadata only; moving or renaming a
  folder must not change the canonical call identity.
- Show per-call validation and import outcomes; allow a failed call to be
  corrected and retried without hiding successful calls in the same batch.
- Make audio available to the existing review player without using it to infer
  or replace transcript text.

## Non-goals

- Do not automatically duplicate evaluation on replay; explicit reevaluation
  and retrying failed evaluation batches remain manual actions.
- Do not infer transcripts from audio.
- Do not add object storage, a message queue, background workers, or platform
  telemetry.
- Do not accept arbitrary filesystem paths from a browser or API caller.
- Do not restore folder aliases, path-based evaluation, or the removed
  `process-and-evaluate` behavior.
- Do not persist import-run history; return per-call results to the UI.

## Approaches considered

1. **Shared backend importer (selected).** One backend service validates and
   imports a call folder whether it was uploaded by the browser or selected
   from backend storage. It maps the manifest once, stores all call files in
   the existing local artifact store, and returns per-call results. This keeps
   mapping and validation consistent and supports safe retries; it requires a
   focused upload/import API.
2. **Frontend-orchestrated imports.** The UI parses each folder and makes
   separate calls for the interaction, events, and audio. This reuses current
   APIs but duplicates mapping behavior in the frontend and can leave partial
   interactions if one request fails. It is not recommended.

## Proposed user flow

```text
Import Calls
  [Single call] [Folder batch]
  Source: [Upload from computer] [Choose staged backend calls]
  Select a call folder or parent folder
  Validate -> per-call results -> import/retry failures
```

- For a computer upload, preserve relative folder names only to group files;
  never treat them as server paths.
- A selected call folder has `call.json` and `recording.wav` at its root.
- A selected batch folder contains call folders as immediate children. Each
  child is validated and imported independently.
- For staged imports, the backend lists eligible call folders beneath the
  configured artifact root and tenant directory. The client submits opaque
  folder identifiers, not filesystem paths.

## Import behavior

- Parse and validate the full call folder before persisting that call.
- Map `call.json` metadata and messages using canonical interaction fields and
  the existing transcript model. Preserve raw transcript text. Missing or
  unreliable timing and unknown speakers remain unknown.
- Validate `recording.wav` as a readable WAV container without imposing sample
  rate, channel-count, or duration requirements. Report audio properties and
  silence status; do not reject a valid silent recording.
- Store `recording.wav` and other regular files recursively through the
  existing local artifact store. Register artifact rows so the current audio
  review endpoint can serve the recording.
- Import each folder independently. A failed call reports a clear error without
  discarding successful calls from the same batch.
- Stage and validate all files for one call before persistence. Persist the
  interaction, transcript, and artifact rows as one per-call unit; clean up
  newly created local files if persistence fails. Other calls in the batch
  remain independent.
- Return the audio validation summary (validity, channels, sample rate,
  duration, and silence status) with each call result.
- Use `call_id` for idempotency. The same canonical manifest and hashes for all
  files are an identical replay. Any changed manifest or artifact for an
  existing `call_id` is a conflict; never overwrite existing call data.
  Identical content under a different source folder name remains a replay.
- Do not return transcript content or audio bytes in import summaries.

## Post-import processing

After a call's interaction, transcript turns, and artifacts commit atomically,
the request waits for post-import processing before returning. Successful
created and replayed imports report transcript-turn, timeline, observability,
and evaluation stage statuses and errors. A derived-stage failure does not
undo the persisted import. If timeline or observability calculation fails,
evaluation is still attempted from the persisted transcript, and the
calculation failure is reported separately from the evaluation outcome.
Identical replays do not duplicate an existing evaluation run; missing
deterministic outputs may be rebuilt. Reevaluation requires an explicit manual
action, and failed evaluation batches are retried manually.

This behavior is detailed in
[the call import processing design](2026-11-15-call-import-processing-design.md).
Queue, background-worker, object-storage, and platform-telemetry infrastructure
remain out of scope.

## API and implementation boundaries

- Add bounded APIs to list eligible staged call folders and to import either
  uploaded folder files or selected staged folder identifiers.
- Include incomplete staged folders in the list with required-file readiness
  and safe validation messages, so operators can see why a folder cannot yet
  be imported. Never return absolute paths.
- Reuse the canonical ingestion service, transcript repository, local artifact
  store, and tenant-scoped artifact rows. Keep `ArtifactReference` metadata
  registration separate from binary upload semantics.
- Store imported artifacts under a content-addressed import subdirectory that
  is separate from the staged-folder listing root, so imported copies are not
  rediscovered as new staged calls and changed files cannot overwrite old ones.
- Keep tenant scoping consistent with the existing API. Resolve staged folders
  beneath the configured artifact root on the server and reject path traversal,
  symlinks, non-regular files, duplicate relative paths, and malformed
  manifests. Never use a multipart filename directly as a server filesystem
  path. The current multipart parser strips Windows drive-rooted filenames to
  their basename before the API receives them; treat that sanitized basename
  as relative input and reject any rooted or traversal segments that remain.
- Apply these initial limits: 100 calls per batch, 200 files per call, 10,000
  files per request, 512 MiB per file, and 5 GiB total uploaded bytes per
  request. Measure staged files against the same per-file and per-batch limits.
  Surface limit failures before persisting a call; do not silently truncate or
  return success-shaped partial results.
- Treat any parseable WAV container as structurally valid. Do not require a
  particular sample rate, channel count, or duration.

## Builder calls

- The initial limits are intentionally generous relative to the checked-in
  sample corpus (50 folders, about 207 MiB total, and about 11 MiB for its
  largest file, with 63 files in its largest folder) while remaining finite
  for local development.
- A batch is not all-or-nothing: each call is atomic, and the response reports
  each call's created, replayed, or failed result.

## Verification

- Unit tests cover manifest-to-interaction/turn mapping, missing required
  files, invalid audio, unsafe paths, duplicate/conflicting call IDs, and
  idempotent retries.
- API tests cover staged-folder listing, uploaded single-call and batch imports,
  tenant scoping, per-call partial failure reporting, and artifact playback
  registration.
- UI tests cover source selection, single-call and batch result states, and
  retry/error display.
- Run the focused backend/frontend tests, the full backend suite, and the
  production frontend build.
