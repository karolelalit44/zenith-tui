# End-to-End Implementation Plan

## Branch: `fix-frontend-audit-remediation`

This plan covers all fixes, improvements, and debt remediation identified in the frontend audit. Each phase is self-contained with specific file changes, commands, and verification steps. Execute phases in order.

---

## Phase 0: Setup & Tooling Fixes

**Objective:** Fix formatting, create branch, establish baseline.

### Step 0.1 — Create Branch and Fix Line Endings
```bash
git checkout -b fix-frontend-audit-remediation
npx biome format --write src/
```
**Verification:** `npx biome check src/` should now have 0 errors.

### Step 0.2 — Run Tests to Confirm Baseline
```bash
npx vitest run
```
Expected: 3 failing (App.test.tsx), rest passing.

---

## Phase 1: Critical Bug Fixes

### Step 1.1 — Fix 3 Failing Tests in `App.test.tsx`

**File:** `tests/App.test.tsx`

Search for `'Mode:'` assertions — the component renders `[{mode}]` not `'Mode: {mode}'`.

**Changes needed:**
- Line ~14: `expect...Mode:` → expect the actual format `[{mode}]`
- Line ~75: same fix
- Line ~94: same fix

**Verification:** `npx vitest run tests/App.test.tsx` — all 9 tests pass.

### Step 1.2 — Fix Global ID Counter in `templateLoader.ts`

**File:** `src/services/scenario/templateLoader.ts`

Replace:
```ts
let idCounter = 0
```
With:
```ts
let idCounter = Date.now()
```
Or better, use `crypto.randomUUID()` in the `createScenarioEvent` function.

**Verification:** Run engine tests: `npx vitest run tests/engine.test.ts` — all 17 pass. Check no duplicate IDs across multiple scenario loads.

### Step 1.3 — Add Error Boundary Component

**Create `src/components/ErrorBoundary.tsx`:**
```tsx
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Box, Text } from 'ink'

interface Props { children: ReactNode }
interface State { hasError: boolean; error?: Error }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box flexDirection="column" padding={1}>
          <Text color="red">An error occurred</Text>
          <Text>{this.state.error?.message}</Text>
        </Box>
      )
    }
    return this.props.children
  }
}
```

**File:** `src/index.tsx` — Wrap `<App />` inside `<ErrorBoundary>`.

**Verification:** `npx vitest run` — all tests pass. App still renders.

---

## Phase 2: Remove Dead Code

### Step 2.1 — Delete `useModeSelector.ts`

**File:** `src/hooks/useModeSelector.ts` — Delete file.
**Check for imports:** `rg "useModeSelector" src/` — if no imports, safe to delete.

### Step 2.2 — Delete `TreeLog` Component

**Files to delete:**
- `src/components/Display/TreeLog/TreeLog.tsx`
- `tests/TreeLog.test.tsx` (tests for unused component)

### Step 2.3 — Delete `Divider` Component

**Files to delete:**
- `src/components/ui/Divider/Divider.tsx`
- `src/components/ui/Divider/` (entire folder if nothing else there)

### Step 2.4 — Delete `services/scenario/matcher.ts`

**File:** `src/services/scenario/matcher.ts`
**Update imports:** Find files importing from `'../scenario/matcher'` or `'./matcher'` and redirect to `'../data/ScenarioRepository'`.

### Step 2.5 — Check `addDirData.ts` and `contextData.ts`

**File:** `src/components/Display/data/addDirData.ts` — Check if imported anywhere. If not, delete.
**File:** `src/components/Display/data/contextData.ts` — If only one import remains, inline the data.

**Verification:** `npx vitest run` — still passes. `npx tsc --noEmit` — no errors.

---

## Phase 3: UI Bug Fixes

### Step 3.1 — Remove Empty Box in WelcomeScreen

**File:** `src/screens/Welcome/WelcomeScreen.tsx`
Find line ~76: `<Box></Box>` or equivalent empty box.
Remove it.

### Step 3.2 — Fix `void revealTimer` in ThinkingBlock

**File:** `src/components/Display/Scenario/thinkingBlock.tsx` (or `ThinkingBlock.tsx`)
Find `void revealTimer` at ~line 38. Remove the line.

### Step 3.3 — Fix Global ID Counter (already done in Phase 1)

### Step 3.4 — Fix Path Separator in FilePickerModal

**File:** `src/components/Input/FilePicker/FilePickerModal.tsx`
Search for `'/'` used as path separator.
Replace with `path.sep` or normalize: `const sep = path.sep` and use that.
Add import: `import path from 'path'`

### Step 3.5 — Fix Hardcoded Date in FileList

**File:** `src/components/Input/FilePicker/FileList.tsx`
Find `'Jul 22, 2026'` at ~line 59.
Replace with `'—'` or `'N/A'` when `modifiedDate` is absent.

### Step 3.6 — Fix Separator Width in SessionStatusBar

**File:** `src/components/Display/SessionStatusBar.tsx`
Find hardcoded dash string `'────────────...'` at ~line 59.
Calculate dynamically:
```tsx
const separator = '─'.repeat(Math.min(process.stdout.columns ?? 80, 80))
```

**Verification:** `npx vitest run` — tests pass. Manually launch app with `npx tsx src/index.tsx` to verify visual fixes.

---

## Phase 4: Architecture Improvements

### Step 4.1 — Extract `ModalFooter` Shared Component

**Create `src/components/ui/ModalFooter.tsx`:**
```tsx
import { Box, Text } from 'ink'
import type { ReactNode } from 'react'

interface Shortcut { key: string; label: string }

interface ModalFooterProps {
  shortcuts: Shortcut[]
  children?: ReactNode
}

export function ModalFooter({ shortcuts, children }: ModalFooterProps) {
  return (
    <Box flexDirection="column" borderStyle="single" borderTop={false} paddingX={1}>
      {children}
      <Box gap={2}>
        {shortcuts.map((s, i) => (
          <Text key={i} dimColor>
            <Text bold>{s.key}</Text> {s.label}
          </Text>
        ))}
      </Box>
    </Box>
  )
}
```

**Refactor these screens to use `ModalFooter`:**
- `src/screens/Help/HelpModal.tsx`
- `src/screens/Settings/SettingsModal.tsx`
- `src/screens/Providers/ProvidersScreen.tsx`
- `src/screens/Agents/AgentsModal.tsx`
- `src/screens/Plugins/PluginsModal.tsx`
- `src/screens/Context/ContextModal.tsx`
- `src/screens/AddDir/AddDirModal.tsx`
- `src/components/Input/FilePicker/FilePickerModal.tsx`

### Step 4.2 — Extract `NavigationList` Shared Component

**Create `src/components/ui/NavigationList.tsx`:**
```tsx
import { Box, Text } from 'ink'
import { useInput } from 'ink'

interface Item { id: string; label: string; description?: string; disabled?: boolean }

interface NavigationListProps {
  items: Item[]
  activeIndex: number
  onSelect: (item: Item) => void
  onClose: () => void
  renderItem?: (item: Item, index: number, isActive: boolean) => JSX.Element
}

export function NavigationList({ items, activeIndex, onSelect, onClose, renderItem }: NavigationListProps) {
  // keyboard handling extracted from existing screen implementations
  // unified up/down/enter/esc pattern
}
```

**Refactor to use `NavigationList`:**
- `src/screens/ModeSelect/ModeSelectScreen.tsx`
- `src/screens/PersonaSelect/PersonaSelectModal.tsx`
- `src/screens/Settings/SettingsModal.tsx`

### Step 4.3 — Extract `GaugeBar` Shared Component

**Create `src/components/ui/GaugeBar.tsx`:**
```tsx
import { Text } from 'ink'

interface GaugeBarProps {
  current: number
  total: number
  width?: number
  color?: string
}

export function GaugeBar({ current, total, width = 20, color = 'green' }: GaugeBarProps) {
  const ratio = total > 0 ? current / total : 0
  const filled = Math.round(ratio * width)
  const empty = width - filled
  return (
    <Text color={color}>
      {'█'.repeat(filled)}{'░'.repeat(empty)} {current}/{total}
    </Text>
  )
}
```

**Refactor:**
- `src/components/Display/SessionStatusBar.tsx` — use `GaugeBar`
- `src/screens/Context/ContextModal.tsx` — use `GaugeBar`

### Step 4.4 — Extract Spinner Frames to Constants

**Create `src/constants/animation.ts`:**
```ts
export const SPINNER_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
```

**Remove `SPINNER_FRAMES` from:**
- `src/constants/app.ts`
- `src/components/Display/Scenario/ScenarioRenderer.tsx`
- `src/components/Display/Scenario/ProgressBar.tsx`
- `src/components/Display/Scenario/WaitingIndicator.tsx`
- Any other location found via `rg "SPINNER_FRAMES" src/`

Replace all with `import { SPINNER_FRAMES } from '../../constants/animation'` (or relative path adjusted).

**Verification:** `npx vitest run` — tests pass. `npx tsc --noEmit` — no errors.

---

## Phase 5: Hardcoded Data & Constants Cleanup

### Step 5.1 — Single-Source Version String

**File:** `src/constants/app.ts` — Keep `APP_VERSION` here as the canonical version.
**File:** `package.json` — This is source of truth. Consider reading at build time.

Update these files to import `APP_VERSION`:
- `src/constants/uiContent.ts` — remove `version`, import from `app.ts`
- `src/screens/Welcome/data/welcomeData.ts` — import `APP_VERSION`
- `src/screens/Help/HelpModal.tsx` — import `APP_VERSION`
- `src/screens/Plugins/PluginsModal.tsx` — use `APP_VERSION` for consistent labeling

### Step 5.2 — Extract Inline UI Strings

**Create `src/constants/strings.ts`:**
Move all inline hardcoded text strings from screens into this file. Group by screen.

Target files with most inline strings:
- `src/screens/Help/HelpModal.tsx`
- `src/screens/Settings/SettingsModal.tsx`
- `src/components/Providers/GenericProviderConfigForm.tsx`
- `src/screens/Welcome/WelcomeScreen.tsx`
- `src/components/Display/Scenario/ScenarioRenderer.tsx`

### Step 5.3 — Make Syntax Highlighting Theme-Aware

**File:** `src/utils/syntaxHighlight.ts`

Replace hardcoded Dracula hex colors with theme-derived colors:
```ts
interface SyntaxColors {
  keyword: string
  string: string
  number: string
  comment: string
  type: string
  function: string
  operator: string
  variable: string
}

const DARK_COLORS: SyntaxColors = { keyword: '#ff79c6', string: '#f1fa8c', /* ... */ }
const LIGHT_COLORS: SyntaxColors = { keyword: '#8250df', string: '#0a3069', /* ... */ }

function getSyntaxColors(themeName: string): SyntaxColors {
  return themeName.includes('light') ? LIGHT_COLORS : DARK_COLORS
}
```

Update callers (`FileDiffCard.tsx`) to pass theme name or colors.

**Verification:** `npx vitest run` — tests pass. `npx tsc --noEmit` — no errors.

---

## Phase 6: UX Improvements

### Step 6.1 — Add `/clear` Confirmation

**File:** `src/services/data/CommandService.ts`
In `/clear` handler, set a `pendingClear` flag instead of immediately clearing.

**File:** `src/App.tsx`
Check `pendingClear` flag in overlay logic. Show a confirmation overlay:
```
Are you sure you want to clear all conversation history? (y/N)
```

### Step 6.2 — Add Command Alias Feedback

**File:** `src/services/data/CommandService.ts`
In command routing, when an alias is used (e.g., `/plugins` → `/plugin`), push a system message:
```ts
addSystemMessage(`Redirecting /${alias} to /${canonical}`)
```

**Verification:** Manual test — type `/plugins`, see redirect message.

---

## Phase 7: Performance Optimizations

### Step 7.1 — Add React.memo to Scenario Components

Wrap these components with `React.memo`:
- `src/components/Display/Scenario/FileDiffCard.tsx`
- `src/components/Display/Scenario/ErrorBlock.tsx`
- `src/components/Display/Scenario/SuccessCard.tsx`
- `src/components/Display/Scenario/SummaryCard.tsx`
- `src/components/Display/Scenario/TerminalBlock.tsx`
- `src/components/Display/Scenario/ProgressBar.tsx`
- `src/components/Display/Scenario/WaitingIndicator.tsx`

Each: `export default React.memo(ComponentName)` or named export wrapper.

### Step 7.2 — Cache userProfileService Reads

**File:** `src/services/data/userProfileService.ts`
Add in-memory cache:
```ts
let profileCache: UserProfile | null = null
let cacheTimestamp = 0
const CACHE_TTL = 5000 // 5 seconds

function loadUserProfile(): UserProfile {
  const now = Date.now()
  if (profileCache && now - cacheTimestamp < CACHE_TTL) return profileCache
  // ... read from disk ...
  profileCache = profile
  cacheTimestamp = now
  return profile
}

function saveUserProfile(profile: UserProfile) {
  // ... write to disk ...
  profileCache = profile // update cache on write
  cacheTimestamp = Date.now()
}
```

### Step 7.3 — Cache Git Branch Result

**File:** `src/components/Display/SessionStatusBar.tsx`
Move `getActiveGitBranch()` call to a `useRef` or module-level cache that only refreshes every 30s:
```ts
const branchRef = useRef<string | null>(null)
const lastCheckRef = useRef(0)

const branch = useMemo(() => {
  if (Date.now() - lastCheckRef.current > 30000) {
    branchRef.current = getActiveGitBranch()
    lastCheckRef.current = Date.now()
  }
  return branchRef.current
}, [])
```

**Verification:** `npx vitest run` — tests pass.

---

## Phase 8: Testing Expansion

### Step 8.1 — Add Hook Tests for `useOverlayManager`

**Create `tests/hooks/useOverlayManager.test.ts`:**
```ts
import { renderHook, act } from '@testing-library/react'
import { useOverlayManager } from '../../src/hooks/useOverlayManager'

describe('useOverlayManager', () => {
  it('starts with no overlay', () => {
    const { result } = renderHook(() => useOverlayManager())
    expect(result.current.activeOverlay).toBeNull()
  })

  it('opens an overlay', () => {
    const { result } = renderHook(() => useOverlayManager())
    act(() => result.current.openOverlay('help'))
    expect(result.current.activeOverlay).toBe('help')
  })

  it('closes an overlay', () => {
    const { result } = renderHook(() => useOverlayManager())
    act(() => result.current.openOverlay('help'))
    act(() => result.current.closeOverlay())
    expect(result.current.activeOverlay).toBeNull()
  })
})
```

### Step 8.2 — Add Hook Tests for `useConversation`

**Create `tests/hooks/useConversation.test.ts`:**
Test: starts empty, adds turn, completes turn, resets.

### Step 8.3 — Add Hook Tests for `useAutocomplete`

**Create `tests/hooks/useAutocomplete.test.ts`:**
Test: filters commands by prefix, navigates with arrows, selects with enter.

**Verification:** `npx vitest run` — new tests pass alongside existing.

---

## Phase 9: Lint & Final Verification

### Step 9.1 — Final Format and Lint
```bash
npx biome format --write src/
npx biome check src/
```

### Step 9.2 — Full Test Suite
```bash
npx vitest run --coverage
```

### Step 9.3 — TypeScript Check
```bash
npx tsc --noEmit
```

### Step 9.4 — Manual Smoke Test
```bash
npx tsx src/index.tsx
```
Verify:
- App launches without error
- All screens accessible (mode select, help, settings, providers, etc.)
- Scenario execution works (type a prompt)
- /clear commands work
- No blank lines or visual artifacts

---

## Execution Order & Dependencies

```
Phase 0 (Setup)
  └─► Phase 1 (Critical Fixes) — unblocks everything
        └─► Phase 2 (Dead Code Removal) — safe cleanup
              ├─► Phase 3 (UI Bug Fixes) — visual fixes
              ├─► Phase 4 (Architecture) — shared components
              │     └─► Phase 5 (Constants Cleanup) — depends on architecture layer
              │           └─► Phase 6 (UX) — independent
              ├─► Phase 7 (Performance) — independent
              └─► Phase 8 (Testing) — can start after Phase 1
                    └─► Phase 9 (Final Verification) — must be last
```

**Parallel batches** (can be done simultaneously):
- Batch A: Phase 2 + Phase 3
- Batch B: Phase 6 + Phase 7
- Batch C: Phase 8
- Phase 4 and 5 are sequential (5 depends on 4's shared components)

---

## Commit Strategy

```
Commit 1: "fix: resolve critical bugs — failing tests, ID counter, error boundary"
Commit 2: "chore: remove dead code — useModeSelector, TreeLog, Divider, matcher"
Commit 3: "fix: resolve 5 UI bugs — empty box, void revealTimer, path sep, date, separator width"
Commit 4: "refactor: extract shared components — ModalFooter, NavigationList, GaugeBar, spinner constants"
Commit 5: "chore: consolidate hardcoded data — version strings, UI strings, theme-aware syntax highlighting"
Commit 6: "feat: improve UX — /clear confirmation, command alias feedback"
Commit 7: "perf: optimize rendering — memoize scenario components, cache disk reads, cache git branch"
Commit 8: "test: add hook unit tests — useOverlayManager, useConversation, useAutocomplete"
```

---

## Rollback Plan

- Each commit is self-contained. If a phase causes failures:
  - Identify the failing commit via `git bisect`
  - Revert with `git revert <commit-hash>`
  - Fix the issue and re-apply
- Critical path: Phase 1 must pass tests. If Phase 1.3 (Error Boundary) causes issues, remove the wrapper in `index.tsx`.
- Test safety net: Run `npx vitest run` after every commit.
