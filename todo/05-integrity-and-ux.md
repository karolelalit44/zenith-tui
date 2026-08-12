# 05 — Integrity & UX: partial writes, token-total mismatch, and no resume path

> Area: `server/agents/loop.py`, `server/agents/context.py`, `tui/src/screens/Composer/ComposerFooter.tsx`, `tui/src/components/CommandInput/CommandInput.tsx`
> Severity: **High** — the failed run left a corrupted, half-built project with no recovery, and the UI shows internally-contradictory token numbers.

---

## 1. Summary

After the failure, `library-mgmnt-sys/` contains only 4 files (`.env.example`, `.gitignore`, `docker-compose.yml`, `requirements.txt`) — no `app/`, no tests, no README — and `requirements.txt` was clobbered ~10 times with different contents. There is no way to resume. Separately, the UI's token readouts contradict each other (1048.6k model window vs 128k enforced budget; session "1%" vs turn "65.9%"), making the status bar actively misleading.

## 2. What is currently happening (evidence)

### 2.1 Corrupted, half-built project
`library-mgmnt-sys/` after the run:

```
.env.example          (97 B)
.gitignore            (78 B)
docker-compose.yml    (584 B)
requirements.txt      (187 B)   ← final content is whatever the LAST of ~10 writes left
```

The model had planned `app/main.py`, `app/models.py`, `app/routes/`, tests, a Dockerfile, and a README — none exist. The "requirements" file was written with 10 different contents (233→207→188→183→177→83→100→161→93→177 bytes).

### 2.2 Contradictory token readouts
- Backend enforces **128,000** budget (`context.py` reserve / `max_context_tokens`): `total: 128000`, `percent: 0.727` (turn 18).
- Frontend status bar shows **1048.6k** — because `CommandInput.tsx:90-91` uses `activeModelInfo?.context_window || SESSION_STATUS_DEFAULTS.maxTokens`, and the catalog's google `context_window` is `1048576` (the model's full window).
- `ComposerFooter.tsx:76` formats `layout.maxTokens` → "1048.6k".
- The "used" figure is session-scoped (~6.1k) while the backend's is turn-scoped (~93k) → "1%" vs "65.9%" both shown as if comparable.

So the status bar tells the user they have 1048.6k tokens and used ~1%, while the backend will hard-stop the task at 128k. A long task that "should be fine" dies at 12% of the displayed budget.

### 2.3 No resume path
The failure ends with `[FAILED] … Execution halted` and a zero-byte `zenith_server.log`. There's no "Continue where I left off" — the partial files are orphaned, and the user must re-issue the whole request (which re-burns quota).

## 3. Root causes (code-level)

1. **No write-integrity guard** — nothing blocks a second write to the same path (see `01-…` §5.1); the last content wins arbitrarily.
2. **No end-of-turn manifest** — the loop never emits a summary of created/modified files or a list of remaining steps, so a mid-task failure loses all context.
3. **Token base mismatch** — frontend reads `context_window` (model window 1,048,576) where it should read the effective budget (`max_context_tokens` = 128,000, or `min(context_window, max_context_tokens)`). The session/turn scoping of `used` is also not labelled.
4. **No persistence of turn state** — `library-mgmnt-sys/` state + prompt history are not saved in a way that allows a `continue` call.

## 4. Impact

- Partial/corrupted artifacts after failures; users lose work.
- Misleading status bar → users start tasks that are guaranteed to die at 12% of the displayed budget.
- Every failure forces a full re-run → more quota burn → more 429s (the `02-…` cascade).

## 5. What the correct behaviour should be

### 5.1 Integrity
- **One write per path per turn** (runtime guard + prompt rule, see `01-…`/`04-…`).
- **End-of-turn manifest**: on success *or* stall-finalize, the loop emits a structured summary event with `created[]`, `modified[]`, `remaining[]` so the UI can render "Built these files; not yet done: …".
- **Validate final state** on failure: after a hard error, run a light sanity pass (do declared files exist? non-empty?) and include the result in the error/summary event so the user knows exactly what survived.

### 5.2 Token totals
- Status bar should show the **effective budget** used by the backend: `min(context_window, max_context_tokens)`, i.e. 128k, labelled clearly, e.g. `12.4k / 128k (9.7%)`.
- Label scope: session-total vs current-turn tokens, or pick **one** consistently (recommend turn-scoped, matching what the loop actually enforces).
- Never display the raw model `context_window` as if it were the usable budget.

### 5.3 Resume
- Add a `continue` endpoint / UI button that replays the last turn's history + existing files state with an added instruction: *"Continue from where you left off. Files already written: [list]. Remaining steps: [list]."*
- Persist per-session state (files written, turn history, token budget) so the resume is cheap and doesn't re-burn quota.

## 6. Happy flow (step by step)

1. Task runs; every path is written exactly once; the loop ends with a manifest: `created: [.env.example, .gitignore, docker-compose.yml, requirements.txt, app/main.py, app/models.py, …]`, `remaining: [tests, README]`.
2. If the provider kills the turn anyway, the error event includes the manifest + which files survived, and the UI shows a **Continue** button.
3. Clicking Continue starts a cheap turn with the existing file list in context; only `remaining` work is performed.
4. The status bar shows `14.2k / 128k` (turn) consistently, and users can trust it.

## 7. Fix checklist

- [ ] Emit end-of-turn manifest event (`created`/`modified`/`remaining`) in `loop.py` for both success and stall-finalize paths.
- [ ] Add a light post-failure sanity check of the target directory and include its result in the terminal event.
- [ ] In `CommandInput.tsx`, compute `effectiveBudget = min(context_window, max_context_tokens)` and show that; label the used figure's scope (turn vs session).
- [ ] Add `continue` flow (endpoint + UI button) seeded with existing files + last manifest.
- [ ] Add a test: simulate a mid-turn 429 → assert the terminal event contains the manifest and that a `continue` turn lists existing files as "already written".
