I've now completed a thorough analysis of the entire codebase. Here is the comprehensive audit report:
Comprehensive Frontend Architecture, UI & Code Quality Audit
Zenith Frontend TUI — Principal Engineer Report
Executive Summary
Zenith is a React-based Terminal User Interface (TUI) built with Ink (https://github.com/vadimdemedes/ink) that simulates an AI coding assistant. It features 8 color themes, 6 AI provider configurations, scenario-based mock event rendering, slash command system, file picker, and multiple modal screens.
Overall Assessment: The project demonstrates solid architectural intent with a clear separation of concerns (components, services, hooks, types, theme), a well-designed component registry pattern, and a clean provider service layer. However, it has significant production readiness gaps: all data is mock/static, tests reference stale output expectations, there are 3 failing tests, formatting issues across all files, duplicated logic, missing error boundaries, and numerous hardcoded values that should be extracted. The application is a well-structured prototype/demo, not yet production-ready.
Severity: High Priority — Functional prototype with solid foundation but critical gaps before production.
1. UI Bugs
#	Location	Description
1	App.tsx:127	No scroll management — long conversation history may overflow terminal
2	WelcomeScreen.tsx:76	Empty <Box> with no content renders a blank line (line 76-77 between provider row and workspace row)
3	SessionStatusBar.tsx:59	Hardcoded ASCII separator line '────────────...' doesn't adapt to terminal width
4	FilePickerModal.tsx:52	Uses '/' as path separator — breaks on Windows where \ is native
5	FileList.tsx:59	Default date 'Jul 22, 2026' shown when no modifiedDate — always shows current date
6	RoundedBox.tsx:42	@ts-expect-error used for position="absolute" — Ink may not fully support absolute positioning
7	GenericProviderConfigForm.tsx:59-73	Manual backspace character handling in text fields — doesn't handle clipboard paste, selection, or multi-byte chars
8	HelpModal.tsx:123	Text says zenith_plans/ directory but this may not exist
9	ScenarioRenderer.tsx:64	key={event.id} but event.id from templateLoader.ts is a global incrementing counter — IDs can collide across scenarios
10	thinkingBlock.tsx:38	void revealTimer is a no-op statement that serves no purpose
2. UX Issues
#	Issue	Description
1	No confirmation before /clear	/clear immediately wipes all conversation history without confirmation
2	No command alias feedback	Typing /plugins silently redirects to /plugin — user may be confused
3	No visual distinction between live and historical scenarios	Completed scenarios look identical to running ones in the scrollback
4	Autocomplete resets on every keystroke	activeIndex in AutocompleteDropdown.tsx:9 resets to 0 on re-render because it's not tied to filtered results length
5	File picker search is character-by-character	Typing fast fills search without debounce — acceptable for TUI but no visual "type to search" prompt visible during navigation
6	History navigation shows stale data	useAutocomplete.ts stores history in local state — lost on remount; also history is unbounded (max 5 is only for sessions, not prompts)
7	No loading state for provider config save	GenericProviderConfigForm.tsx:127 shows success message synchronously — feels instant, no save confirmation animation
8	No keyboard shortcut to go back from file picker to input	Left arrow at root path closes picker — no indication this will happen
9	Context Modal uses mock file data	ContextModal.tsx:27 shows hardcoded workspace files, not actual project files
10	Missing /help command in autocomplete filter	CommandService.getCommandHints() filters out /theme, /plugins, /providers but /help IS included — consistency issue in alias handling
3. Frontend Bugs
#	Location	Description
1	App.test.tsx:14,75,94	3 tests FAIL — tests expect 'Mode:' text in output but PromptHeader renders [{mode}] not Mode: {mode}
2	templateLoader.ts:3-4	Global idCounter persists across tests and scenarios — IDs are not unique across app lifecycle
3	useConversation.ts:33	totalTokens uses useMemo(() => turns.filter(t => t.isComplete).length * 1247, [turns]) — array reference changes on every state update even when contents are the same, causing unnecessary recomputation
4	useScenario.ts:15-18	Module-level singleton _cachedDefault — the default provider is created once and never garbage collected, even if no scenarios run
5	userProfileService.ts:118-119,138-139,197-198	Errors silently swallowed with catch (_err) { // Fall back to default profile } — user never knows if their config failed to load
6	ScenarioRepository.ts:46	'api key' keyword triggers error scenario — this would trigger on any prompt mentioning "API key" even in valid contexts like "how to use api key"
7	engine.ts:29-31	Final completion fires 500ms after last event — if user aborts during this window, onComplete still fires (aborted flag only checked in event callback, not final timeout)
8	jsonEventNormalizer.ts:22-27	Mutates incoming event object by setting rawObj.id — side effect on passed-in data
9	fileExplorerService.ts:11-149	WORKSPACE_FILES references files that don't exist in actual project (e.g., src/components/Input/InputBox.tsx, src/index.ts instead of src/index.tsx) — stale mock data
10	WelcomeScreen.tsx:76	Empty <Box> element renders blank line in output
4. Architecture Issues
#	Issue	Location
1	App.tsx is a God Component	App.tsx (247 lines) handles routing, state, command dispatch, overlay management, keyboard shortcuts, and layout rendering all in one component
2	No Router/Navigation abstraction	Overlay system uses string comparison (overlay === 'mode') with 10+ conditional renders in App.tsx
3	Duplicated state management	useModeSelector.ts is a dead/hook — superseded by useOverlayManager.ts but still exists in codebase
4	No context-based state sharing	usePersona, useConversation, useScenario all manage independent state that should be coordinated (e.g., persona + mode should persist across sessions)
5	Mixed service patterns	Some services are classes (CommandService, ProviderService), some are plain functions (getScenarioForPrompt), some are module-level singletons (commandService, providerService)
6	Flat folder structure for screens	All 10 screens are at same level under screens/ with no feature grouping
7	Scenario data and logic co-located	10+ scenario files contain both data templates AND business logic for scenario matching
8	No barrel exports for hooks	hooks/ has no index.ts barrel — each hook imported individually
9	components/Display/data/ contains mock data used by components	contextData.ts and addDirData.ts embed static data inside component folders
10	services/scenario/matcher.ts re-exports from services/data/	matcher.ts is just export { getScenarioForPrompt } from '../data/ScenarioRepository' — confusing indirection
5. Component Issues
#	Issue	Components
1	Duplicated spinner frames	SPINNER_FRAMES defined in 6+ locations: app.ts, ScenarioRenderer.tsx, DeploymentCard.tsx, BuildStepCard.tsx, ProgressBar.tsx, WaitingIndicator.tsx
2	Duplicated border characters	Box border chars in both constants/ui.ts:3-10 AND RoundedBox.tsx:21-28
3	Duplicated progress bar logic	SessionStatusBar.tsx:51-54 and ContextModal.tsx:23-25 both implement identical gauge/bar rendering
4	No shared "ModalFooter" component	Every modal (Help, Settings, Providers, Agents, Plugins, etc.) duplicates the same footer pattern: border + shortcut hints
5	No shared "ListSelector" component	ModeSelectScreen, PersonaSelectModal, SettingsModal all implement identical up/down/select/close pattern
6	ScenarioRenderer.tsx has nested event components that bypass registry	useInput for Shift+T is inside ScenarioRenderer, not in individual components — keyboard handling leaks across all events
7	ThinkingBlock.tsx manages its own animation state	Each ThinkingBlock independently runs setTimeout chains — multiple thinking blocks would animate concurrently
8	GenericProviderConfigForm is 299 lines	Single component handles: form fields, model catalog scrolling, keyboard navigation, save logic, section tabs
9	TreeLog component is unused in production	Only used in tests — not referenced by any screen or component
10	Divider component is unused	Not imported by any component
6. Hardcoded Data Report
Category: Static Business Data in UI
Location	Hardcoded Value
PluginsModal.tsx:10-14	3 hardcoded plugin definitions
AgentsModal.tsx:10-29	3 hardcoded agent definitions
SessionRepository.ts:7-11	3 hardcoded initial sessions
fileExplorerService.ts:11-149	20+ hardcoded workspace files with fake sizes
contextData.ts:8-33	Mock file tree with fake sizes
addDirData.ts:7-16	Hardcoded metrics (1,204 files, 32 deps)
welcomeData.ts:3-11	Static welcome labels
constants/app.ts:4	ENGINE_MODEL = 'Sonnet 4.5'
constants/app.ts:6-11	Hardcoded greeting messages with username
constants/statusDefaults.ts:7-8	maxTokens: 200000, workspaceName: 'zenith-frontend-tui'
Category: Version Strings (Duplicated)
Location	Value
package.json:3	"version": "1.0.0"
constants/app.ts:1	APP_VERSION = '1.0.0'
constants/uiContent.ts:5	version: '1.0.0'
welcomeData.ts:5	version: 'v1.0.0'
HelpModal.tsx:144	'Zenith TUI v1.0.0'
PluginsModal.tsx:11-13	'v1.4.0', 'v2.1.0', 'v1.0.0'
Recommendation: Use APP_VERSION from constants/app.ts everywhere. Derive from package.json at build time if possible.
Category: Syntax Highlighting
Location	Issue
syntaxHighlight.ts:4-13	8 hardcoded Dracula-palette colors — not theme-aware
syntaxHighlight.ts:15-86	70+ hardcoded keywords/types — language-specific, should be configurable
Recommendation: Make syntax colors derive from active theme. Move keyword sets to language-specific config files.
7. Missing Industry Standards
Standard	Status
Error Boundaries	Not implemented
Environment Configuration	No .env support, no env-specific config
Logging System	console.log used nowhere, no logger
Internationalization (i18n)	All strings hardcoded in English
Accessibility (a11y)	No ARIA considerations for TUI
Testing: Component Tests	Only 2 component tests (App.test.tsx, TreeLog.test.tsx)
Testing: Hook Tests	Zero hook tests
Testing: Integration Tests	E2E scenario tests exist but are brittle (timing-dependent)
Code Splitting	Not applicable (TUI) but all scenarios loaded eagerly
Performance: Memoization	Some components use React.memo, most don't
Type Safety	noExplicitAny: "off" in biome.json
Validation	No runtime validation of user_profile.json schema
Dependency Injection	Services use module-level singletons
Configuration Validation	Provider config not validated against schema at load time
8. Technical Debt
#	Debt	Location
1	3 Failing Tests	App.test.tsx:14,75,94
2	40 Biome Format Errors	All files with \r\n line endings
3	useModeSelector.ts is dead code	hooks/useModeSelector.ts
4	TreeLog component is unused	components/Display/TreeLog/
5	Divider component is unused	components/ui/Divider/
6	components/Display/data/ unused	contextData.ts, addDirData.ts
7	services/scenario/matcher.ts is trivial re-export	Single-line re-export file
8	Legacy dual-profile format	userProfileService.ts maintains both flat and nested UserProfile fields
9	@ts-expect-error in RoundedBox	RoundedBox.tsx:42
10	Mock data in fileExplorerService.ts	References files that don't exist
11	Duplicate scenario files	build/buildScenario.ts AND buildScenario.ts exist at different paths
12	Scenario interface missing required id field	types/scenario.ts:222 — id is optional in Scenario type
9. Performance Issues
#	Issue	Location
1	turns array creates new reference on every completion	useConversation.ts:57-61
2	No memoization on most scenario components	ProgressBar, MessageBlock, WaitingIndicator, etc.
3	useTickAnimation runs even when not visible	Called in ProgressBar, WaitingIndicator, DeploymentCard simultaneously
4	Syntax highlighting re-parses on every render	FileDiffCard.tsx:48 calls highlightCode() on every render
5	Module-level singleton services read disk on every call	userProfileService.ts:81-124 — loadUserProfile() reads file from disk each time
6	getActiveGitBranch() runs synchronously	SessionStatusBar.tsx:31 — execSync blocks rendering
7	Large scenario event arrays	Some scenarios have 20+ events stored in state
10. Testing Audit
Area	Coverage
App.test.tsx	9 tests, 3 FAILING
commandService.test.ts	3 tests passing
engine.test.ts	17 tests passing
modelList.test.ts	2 tests passing
provider.test.ts	4 tests passing
startup.test.ts	1 test passing
TreeLog.test.tsx	1 test passing
Hook tests	0 tests
Component tests	2 tests (App + TreeLog)
Screen tests	0 tests
Service tests	4 test files
Keyboard shortcut tests	0 tests
Edge case tests	0 tests
Recommended Test Architecture:
1. Fix the 3 failing App.test.tsx tests first
2. Add hook tests for useConversation, useOverlayManager, useScenario, useAutocomplete
3. Add component tests for key UI components (ScenarioRenderer, WelcomeScreen, each modal)
4. Add integration tests for full command flows (/mode, /clear, /compact)
5. Add error scenario tests (provider errors, permission errors)
6. Target 80%+ coverage threshold (currently 60%)
Prioritized Roadmap
Critical (Must fix before any release)
#	Item	Current
1	Fix 3 failing tests	Tests expect 'Mode:'
2	Fix line endings	\r\n in all files
3	Fix global ID counter	templateLoader.ts:3-4
4	Add Error Boundary	No error handling
High Priority (Significant quality impact)
#	Item	Current
5	Deduplicate spinner frames	6+ copies
6	Deduplicate progress bar rendering	2 implementations
7	Extract ModalFooter component	10 screens copy footer
8	Extract ListSelector component	5 screens copy nav list
9	Fix App.tsx god component	247 lines, 10+ concerns
10	Remove dead code	useModeSelector, TreeLog, Divider, matcher.ts
11	Make syntax highlighting theme-aware	Hardcoded Dracula colors
12	Fix fileExplorerService.ts stale mock data	References non-existent files
Medium Priority (Important improvements)
#	Item	Current
13	Single source for version string	5+ duplicated version values
14	Extract hardcoded UI strings	60+ inline strings
15	Add useMemo/useCallback to components	Most components render without memoization
16	Cache file system reads	loadUserProfile() reads disk every call
17	Add environment config	No .env support
18	Add hook unit tests	0 tests for 10 hooks
19	Fix jsonEventNormalizer.ts mutation	Mutates incoming event object
20	Migrate userProfileService to nested-only format	Dual flat/nested fields
Low Priority (Nice-to-have)
#	Item	Current
21	Add component tests for modals	0 modal tests
22	Add /clear confirmation	Immediately wipes history
23	Add terminal height awareness	Fixed layout
24	Add i18n support	All English hardcoded
25	Add structured logging	No logging
26	Add CI pipeline	No CI config
Summary Statistics
Metric
Source files
Lines of code (approx.)
Tests
Test coverage
Biome errors
Hardcoded values
Unused files
Duplicated patterns
Failing tests
Components
Hooks
Screens/modals
▣  Plan · Big Pickle · 14m 31s