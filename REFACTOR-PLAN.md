# Refactoring Plan: Production-Ready Architecture

## Current State Analysis

**Technology Stack**: React 19 + Ink 6 (TUI) + TypeScript 7 + Vitest  
**Current Issues**:
- Flat file structure with no clear organization
- Monolithic `App.tsx` (~300 lines) handling routing, state, and UI composition
- Inline constants scattered across components
- Modals instead of proper screen-based navigation
- Input logic embedded in screen rather than as standalone component
- Types exported from usage sites rather than centralized
- No separation between business logic and UI

---

## Target Architecture

```
src/
├── index.tsx                          # Entry point (unchanged)
├── App.tsx                            # Root: ThemeProvider + NavigationProvider + Router
│
├── navigation/
│   ├── NavigationContext.tsx           # Navigation state provider (replaces OverlayState)
│   └── types.ts                       # Navigation types (Screen, Route, etc.)
│
├── screens/
│   ├── Welcome/
│   │   ├── WelcomeScreen.tsx          # Welcome/landing screen (ASCII logo + status)
│   │   ├── index.ts                   # Re-export
│   │   └── data/
│   │       └── welcomeData.ts         # Static session data, workspace path, greetings
│   │
│   ├── Chat/
│   │   ├── ChatScreen.tsx             # Main chat/command execution screen
│   │   ├── index.ts
│   │   └── data/
│   │       └── chatData.ts            # Command descriptions, mock responses
│   │
│   └── Settings/
│       ├── SettingsScreen.tsx         # Settings parent screen
│       ├── index.ts
│       ├── Theme/
│       │   ├── ThemeScreen.tsx        # Theme picker
│       │   ├── index.ts
│       │   └── data/
│       │       └── themeData.ts       # Theme metadata (labels, icons, descriptions)
│       ├── Account/
│       │   ├── AccountScreen.tsx      # Account/persona settings
│       │   ├── index.ts
│       │   └── data/
│       │       └── accountData.ts     # Persona definitions
│       └── Plugins/
│           ├── PluginsScreen.tsx      # Plugin manager
│           ├── index.ts
│           └── data/
│               └── pluginsData.ts     # Plugin catalog, marketplace data
│
├── components/
│   ├── ui/                            # Primitive/reusable UI components
│   │   ├── RoundedBox/
│   │   │   ├── RoundedBox.tsx
│   │   │   ├── index.ts
│   │   │   └── types.ts
│   │   ├── Text/
│   │   │   ├── index.ts              # Re-export of themed text primitives
│   │   │   └── types.ts
│   │   └── Divider/
│   │       ├── Divider.tsx
│   │       └── index.ts
│   │
│   ├── Input/                         # Standalone input component
│   │   ├── InputBox.tsx              # Main input with autocomplete
│   │   ├── AutocompleteDropdown.tsx   # "/" command autocomplete
│   │   ├── index.ts
│   │   ├── types.ts
│   │   └── data/
│   │       └── commands.ts           # Command definitions for autocomplete
│   │
│   ├── Display/                       # Display/result components
│   │   ├── TreeLog/
│   │   │   ├── TreeLog.tsx
│   │   │   ├── index.ts
│   │   │   └── types.ts
│   │   ├── WordDiffViewer/
│   │   │   ├── WordDiffViewer.tsx
│   │   │   ├── index.ts
│   │   │   └── types.ts
│   │   └── AddDirLog/
│   │       ├── AddDirLog.tsx
│   │       ├── index.ts
│   │       └── data/
│   │           └── mockMetrics.ts    # Mock sync data
│   │
│   └── ContextModal/
│       ├── ContextModal.tsx
│       ├── index.ts
│       └── data/
│           └── contextData.ts        # File tree mock data
│
├── hooks/
│   ├── useMockEngine.ts              # Mock backend engine
│   └── useTheme.ts                   # Re-export of theme hook
│
├── services/
│   └── mockEngine/
│       ├── engine.ts                 # Command execution logic
│       ├── commands.ts               # Command definitions and handlers
│       └── types.ts                  # LogItem, ExecutionResult types
│
├── theme/
│   ├── theme.ts                      # Theme definitions (all 6 themes)
│   ├── ThemeContext.tsx               # Theme provider
│   └── types.ts                      # Theme type, ThemeName
│
├── types/
│   ├── index.ts                      # Central type exports
│   ├── navigation.ts                 # Navigation types
│   └── common.ts                     # Shared types (LogItem, DiffLine, etc.)
│
└── constants/
    ├── index.ts                      # Central constant exports
    ├── ui.ts                         # UI constants (dimensions, padding, etc.)
    └── app.ts                        # App-level constants (version, name, etc.)
```

---

## Implementation Phases

### Phase 1: Foundation (Types, Constants, Theme)

**Goal**: Establish the type system and extract all static data without changing behavior.

| Step | Action | Files |
|------|--------|-------|
| 1.1 | Create `src/types/common.ts` with shared types | New file |
| 1.2 | Create `src/types/navigation.ts` with navigation types | New file |
| 1.3 | Create `src/types/index.ts` as barrel export | New file |
| 1.4 | Create `src/constants/app.ts` with app-level constants | New file |
| 1.5 | Create `src/constants/ui.ts` with UI constants | New file |
| 1.6 | Create `src/constants/index.ts` as barrel export | New file |
| 1.7 | Update `src/theme/types.ts` (extract from theme.ts) | New file |
| 1.8 | Update components to import from centralized types | Edit existing |

**Types to Extract**:
- `LogItem` (from useMockEngine)
- `DiffLine`, `DiffSegment` (from WordDiffViewer)
- `Persona` (from PersonaModal)
- `OverlayState` → `Screen` (navigation types)

**Constants to Extract**:
- App version, name (from package.json)
- UI dimensions (box widths, padding)
- Theme metadata (currently in ThemeModal.tsx)
- Persona definitions (currently in PersonaModal.tsx)
- Settings definitions (currently in SettingsModal.tsx)
- Command definitions (currently in AutocompleteDropdown.tsx)

---

### Phase 2: Navigation System

**Goal**: Replace overlay-based navigation with a proper navigation context.

| Step | Action | Files |
|------|--------|-------|
| 2.1 | Create `src/navigation/types.ts` | New file |
| 2.2 | Create `src/navigation/NavigationContext.tsx` | New file |
| 2.3 | Update `App.tsx` to use NavigationProvider | Edit existing |
| 2.4 | Remove `OverlayState` from App.tsx | Edit existing |

**Navigation Types**:
```typescript
type Screen = 
  | 'welcome'
  | 'chat'
  | 'settings'
  | 'settings.theme'
  | 'settings.account'
  | 'settings.plugins';

interface NavigationState {
  currentScreen: Screen;
  history: Screen[];
}

interface NavigationContextType {
  state: NavigationState;
  navigate: (screen: Screen) => void;
  goBack: () => void;
  canGoBack: boolean;
}
```

---

### Phase 3: Screen Extraction

**Goal**: Break monolithic App.tsx into screen-based modules.

| Step | Action | Files |
|------|--------|-------|
| 3.1 | Create `src/screens/Welcome/` directory | New directory |
| 3.2 | Extract DashboardScreen → WelcomeScreen | Move + Edit |
| 3.3 | Create `src/screens/Welcome/data/welcomeData.ts` | New file |
| 3.4 | Create `src/screens/Chat/` directory | New directory |
| 3.5 | Extract chat logic from App.tsx → ChatScreen | New file |
| 3.6 | Create `src/screens/Chat/data/chatData.ts` | New file |
| 3.7 | Create `src/screens/Settings/` directory | New directory |
| 3.8 | Extract SettingsModal → SettingsScreen | Move + Edit |
| 3.9 | Create `src/screens/Settings/Theme/` | New directory |
| 3.10 | Extract ThemeModal → ThemeScreen | Move + Edit |
| 3.11 | Create `src/screens/Settings/Account/` | New directory |
| 3.12 | Extract PersonaModal → AccountScreen | Move + Edit |
| 3.13 | Create `src/screens/Settings/Plugins/` | New directory |
| 3.14 | Extract PluginModal → PluginsScreen | Move + Edit |
| 3.15 | Update App.tsx to render screens based on navigation | Edit existing |

---

### Phase 4: Component Architecture

**Goal**: Refactor components into single-responsibility, reusable units.

| Step | Action | Files |
|------|--------|-------|
| 4.1 | Create `src/components/ui/RoundedBox/` | New directory |
| 4.2 | Move and clean up RoundedBox.tsx | Move + Edit |
| 4.3 | Create `src/components/ui/Divider/` | New directory |
| 4.4 | Extract divider logic from components | New file |
| 4.5 | Create `src/components/Input/` directory | New directory |
| 4.6 | Extract input logic from App.tsx → InputBox | New file |
| 4.7 | Move AutocompleteDropdown → components/Input/ | Move |
| 4.8 | Create `src/components/Display/` directory | New directory |
| 4.9 | Move TreeLog, WordDiffViewer, AddDirLog | Move |
| 4.10 | Create barrel exports for all component directories | New files |

---

### Phase 5: Services Layer

**Goal**: Extract business logic from hooks into a services layer.

| Step | Action | Files |
|------|--------|-------|
| 5.1 | Create `src/services/mockEngine/` directory | New directory |
| 5.2 | Extract command execution logic → engine.ts | New file |
| 5.3 | Extract command definitions → commands.ts | New file |
| 5.4 | Create `src/services/mockEngine/types.ts` | New file |
| 5.5 | Refactor useMockEngine to use services | Edit existing |
| 5.6 | Remove dead code (refactor.cjs, prompt.md) | Delete files |

---

### Phase 6: Data Layer

**Goal**: Move all static data into dedicated data files.

| Step | Action | Files |
|------|--------|-------|
| 6.1 | Create data directories for each screen | New directories |
| 6.2 | Extract Welcome screen static data | New file |
| 6.3 | Extract Chat screen static data | New file |
| 6.4 | Extract Settings screen static data | New file |
| 6.5 | Extract Theme screen static data | New file |
| 6.6 | Extract Account screen static data | New file |
| 6.7 | Extract Plugins screen static data | New file |
| 6.8 | Update all screens to consume data from files | Edit existing |

---

### Phase 7: Cleanup & Validation

**Goal**: Ensure everything compiles, tests pass, and dead code is removed.

| Step | Action | Files |
|------|--------|-------|
| 7.1 | Remove old component files after migration | Delete files |
| 7.2 | Update all imports to use new paths | Edit existing |
| 7.3 | Run TypeScript compiler to verify types | Command |
| 7.4 | Run linter to verify code style | Command |
| 7.5 | Run tests to verify functionality | Command |
| 7.6 | Fix any broken imports or references | Edit as needed |
| 7.7 | Update barrel exports | Edit existing |

---

## Migration Strategy

### Approach: Incremental Refactoring

1. **No Big Bang**: Refactor in small, testable increments
2. **Preserve Behavior**: Each phase maintains identical functionality
3. **Verify After Each Phase**: Run tests after each phase completes
4. **Update Imports Gradually**: Use barrel exports to minimize import changes

### Import Update Strategy

Before each phase:
```typescript
// Old
import { RoundedBox } from './components/RoundedBox';
import { Theme } from './theme/theme';

// After Phase 1
import { RoundedBox } from '@/components/ui/RoundedBox';
import { Theme } from '@/theme';
```

### Barrel Export Pattern

Each directory will have an `index.ts`:
```typescript
// src/components/ui/RoundedBox/index.ts
export { RoundedBox } from './RoundedBox';
export type { RoundedBoxProps } from './types';
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Breaking imports | Use barrel exports; update imports incrementally |
| Type errors | Run `tsc --noEmit` after each phase |
| Test failures | Run `npm test` after each phase |
| Lost functionality | Create git branch; commit after each phase |
| Circular dependencies | Enforce one-way imports (types ← components ← screens ← App) |

---

## Success Criteria

- [ ] All screens have dedicated folders under `src/screens/`
- [ ] Navigation reflects user flow (Welcome → Chat → Settings hierarchy)
- [ ] Input component is standalone and reusable
- [ ] All static data is in dedicated data files
- [ ] Types are centralized in `src/types/`
- [ ] Constants are centralized in `src/constants/`
- [ ] Business logic is in `src/services/`
- [ ] Components are single-responsibility and reusable
- [ ] No circular dependencies
- [ ] All tests pass
- [ ] TypeScript compiles without errors
- [ ] No hardcoded values in components

---

## Estimated Effort

| Phase | Estimated Time |
|-------|----------------|
| Phase 1: Foundation | 30 minutes |
| Phase 2: Navigation | 45 minutes |
| Phase 3: Screen Extraction | 60 minutes |
| Phase 4: Component Architecture | 45 minutes |
| Phase 5: Services Layer | 30 minutes |
| Phase 6: Data Layer | 30 minutes |
| Phase 7: Cleanup | 30 minutes |
| **Total** | **~4.5 hours** |

---

## Git Strategy

```bash
# Create feature branch
git checkout -b refactor/production-architecture

# Commit after each phase
git add -A
git commit -m "refactor: phase 1 - extract types and constants"

# Merge after all phases complete and tests pass
git checkout main
git merge refactor/production-architecture
```
