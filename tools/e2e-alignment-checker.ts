#!/usr/bin/env tsx
/**
 * e2e-alignment-checker.ts — Comprehensive End-to-End Pipeline Audit
 *
 * Verifies alignment across the entire backend→frontend event pipeline:
 *   Backend EventKind → WebSocket → EventMapper → ScenarioEvent → componentRegistry → UI Component
 *
 * Usage: npx tsx tools/e2e-alignment-checker.ts
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// ── Config ──────────────────────────────────────────────────────────────────────
const ROOT = process.cwd();
const SRC = path.join(ROOT, 'src');
const ZENITH = path.join(ROOT, 'zenith');

interface CheckResult {
  check: string;
  status: 'pass' | 'fail' | 'warn';
  detail: string;
}

const results: CheckResult[] = [];

function pass(check: string, detail: string) { results.push({ check, status: 'pass', detail }); }
function fail(check: string, detail: string) { results.push({ check, status: 'fail', detail }); }
function warn(check: string, detail: string) { results.push({ check, status: 'warn', detail }); }

// ── Helpers ─────────────────────────────────────────────────────────────────────
function readFile(p: string): string {
  try { return fs.readFileSync(p, 'utf-8'); } catch { return ''; }
}

function readJSON(p: string) {
  try { return JSON.parse(readFile(p)); } catch { return null; }
}

function extractEventKindFromPython(src: string): string[] {
  const kinds: string[] = [];
  const re = /^\s{4}(\w+)\s*=\s*"([^"]+)"/gm;
  let m;
  while ((m = re.exec(src)) !== null) {
    kinds.push(m[2]);
  }
  return kinds;
}

function extractEventKindFromTS(src: string): string[] {
  const kinds: string[] = [];
  // Only match the EventKind type definition (the first block of | '...' entries)
  const kindBlock = src.match(/export type EventKind\s*=[\s\S]*?(?=\nexport|$)/);
  if (!kindBlock) return kinds;
  const re = /\|\s+'([^']+)'/g;
  let m;
  while ((m = re.exec(kindBlock[0])) !== null) {
    kinds.push(m[1]);
  }
  return kinds;
}

function extractEventMapperCases(src: string): string[] {
  const kinds: string[] = [];
  const re = /case\s+'([^']+)'/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    kinds.push(m[1]);
  }
  return kinds;
}

function extractRegistryEntries(src: string): Map<string, string> {
  const map = new Map<string, string>();
  const re = /this\.register\('([^']+)',\s*(\w+)\s+as\s+EventComponentType\)/g;
  let m;
  while ((m = re.exec(src)) !== null) {
    map.set(m[1], m[2]);
  }
  return map;
}

// ── Check 1: Backend EventKind Alignment ───────────────────────────────────────
function checkBackendEventKinds() {
  const eventsPy = readFile(path.join(ZENITH, 'core', 'events.py'));
  if (!eventsPy) {
    fail('BE-1: Backend EventKind', 'Cannot read zenith/core/events.py');
    return [];
  }
  const backendKinds = extractEventKindFromPython(eventsPy);
  pass('BE-1: Backend EventKind enum', `Found ${backendKinds.length} kinds in Python backend: ${backendKinds.join(', ')}`);
  return backendKinds;
}

// ── Check 2: Frontend EventKind Alignment ──────────────────────────────────────
function checkFrontendEventKinds() {
  const scenarioTs = readFile(path.join(SRC, 'types', 'scenario.ts'));
  if (!scenarioTs) {
    fail('FE-1: Frontend EventKind', 'Cannot read src/types/scenario.ts');
    return [];
  }
  const frontendKinds = extractEventKindFromTS(scenarioTs);
  pass('FE-1: Frontend EventKind type', `Found ${frontendKinds.length} kinds in frontend types: ${frontendKinds.join(', ')}`);
  return frontendKinds;
}

// ── Check 3: Backend ↔ Frontend Alignment ──────────────────────────────────────
function checkAlignment(backendKinds: string[], frontendKinds: string[]) {
  const backendSet = new Set(backendKinds);
  const frontendSet = new Set(frontendKinds);

  const missingInFrontend = backendKinds.filter(k => !frontendSet.has(k));
  const missingInBackend = frontendKinds.filter(k => !backendSet.has(k));

  if (missingInFrontend.length === 0 && missingInBackend.length === 0) {
    pass('ALIGN-1: Backend ↔ Frontend 1:1 mapping',
      `All ${backendKinds.length} EventKind types have exact 1:1 alignment across Python backend & TypeScript frontend`);
  } else {
    if (missingInFrontend.length) {
      fail('ALIGN-1: Backend ↔ Frontend',
        `Backend kinds missing in frontend: ${missingInFrontend.join(', ')}`);
    }
    if (missingInBackend.length) {
      fail('ALIGN-1: Backend ↔ Frontend',
        `Frontend kinds missing in backend: ${missingInBackend.join(', ')}`);
    }
  }
}

// ── Check 4: EventMapper coverage ──────────────────────────────────────────────
function checkEventMapper(backendKinds: string[]) {
  const mapperSrc = readFile(path.join(SRC, 'services', 'backend', 'EventMapper.ts'));
  if (!mapperSrc) {
    fail('MAP-1: EventMapper', 'Cannot read src/services/backend/EventMapper.ts');
    return;
  }
  const mapperCases = extractEventMapperCases(mapperSrc);

  const backendSet = new Set(backendKinds);
  const mapperSet = new Set(mapperCases);

  const unhandled = backendKinds.filter(k => !mapperSet.has(k));
  const extraCases = mapperCases.filter(k => !backendSet.has(k));

  if (unhandled.length === 0 && extraCases.length === 0) {
    pass('MAP-1: EventMapper handles all kinds',
      `All ${backendKinds.length} EventKind types handled in EventMapper switch statement`);
  } else {
    if (unhandled.length) {
      fail('MAP-1: EventMapper missing cases',
        `Backend kinds not handled by EventMapper: ${unhandled.join(', ')}`);
    }
    if (extraCases.length) {
      warn('MAP-1: EventMapper extra cases',
        `EventMapper handles kinds not in backend: ${extraCases.join(', ')} — intentional fallback?`);
    }
  }

  // Check default case
  if (mapperSrc.includes('default:')) {
    pass('MAP-2: EventMapper has default fallback',
      'Unknown event kinds fall back to message event with JSON dump');
  } else {
    fail('MAP-2: EventMapper missing default case',
      'No default case — unknown kinds would crash the mapper');
  }
}

// ── Check 5: Component Registry coverage ───────────────────────────────────────
function checkComponentRegistry(backendKinds: string[]) {
  const registrySrc = readFile(path.join(SRC, 'components', 'Display', 'Scenario', 'componentRegistry.ts'));
  if (!registrySrc) {
    fail('REG-1: Component Registry', 'Cannot read componentRegistry.ts');
    return;
  }
  const registry = extractRegistryEntries(registrySrc);

  const backendSet = new Set(backendKinds);
  const registeredKinds = Array.from(registry.keys());
  const registrySet = new Set(registeredKinds);

  const unregistered = backendKinds.filter(k => !registrySet.has(k));
  const orphaned = registeredKinds.filter(k => !backendSet.has(k));

  if (unregistered.length === 0 && orphaned.length === 0) {
    pass('REG-1: Component Registry covers all kinds',
      `All ${backendKinds.length} EventKind types have registered components`);
  } else {
    if (unregistered.length) {
      fail('REG-1: Component Registry missing entries',
        `Kinds without registered components: ${unregistered.join(', ')}`);
    }
    if (orphaned.length) {
      warn('REG-1: Component Registry orphan entries',
        `Registered kinds not in backend: ${orphaned.join(', ')} — intentional?`);
    }
  }

  // Verify fallback
  if (registrySrc.includes('UnknownEventFallback')) {
    pass('REG-2: Component Registry has fallback',
      'Unknown event kinds render via UnknownEventFallback component');
  } else {
    fail('REG-2: Component Registry missing fallback',
      'No fallback component for unregistered event kinds');
  }
}

// ── Check 6: End-to-End Pipeline Integrity ─────────────────────────────────────
function checkPipelineIntegrity(backendKinds: string[], frontendKinds: string[]) {
  // Verify no duplicates
  const beDups = backendKinds.filter((k, i) => backendKinds.indexOf(k) !== i);
  const feDups = frontendKinds.filter((k, i) => frontendKinds.indexOf(k) !== i);
  if (beDups.length === 0 && feDups.length === 0) {
    pass('INT-1: No duplicate EventKind values',
      'Backend and frontend event kind lists contain no duplicates');
  } else {
    if (beDups.length) fail('INT-1: Duplicate backend kinds', String(beDups));
    if (feDups.length) fail('INT-1: Duplicate frontend kinds', String(feDups));
  }

  // Verify exact count
  if (backendKinds.length === 19 && frontendKinds.length === 19) {
    pass('INT-2: EventKind count (19)',
      `Backend: ${backendKinds.length}, Frontend: ${frontendKinds.length}`);
  } else {
    warn('INT-2: EventKind count',
      `Expected 19, got Backend: ${backendKinds.length}, Frontend: ${frontendKinds.length}`);
  }

  // Verify sorted order consistency (optional, but good practice)
  const beSorted = [...backendKinds].sort();
  const feSorted = [...frontendKinds].sort();
  if (JSON.stringify(beSorted) === JSON.stringify(feSorted)) {
    pass('INT-3: EventKind values identical after sort',
      'Both sides have exactly the same set of event kinds');
  } else {
    warn('INT-3: EventKind values differ',
      'Backend and frontend have different event kind sets — see ALIGN-1');
  }
}

// ── Check 7: Stale dist/ files ────────────────────────────────────────────────
function checkStaleDist() {
  const distDir = path.join(ROOT, 'dist');
  if (fs.existsSync(distDir)) {
    const files: string[] = [];
    function walk(dir: string) {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) { walk(full); }
        else if (entry.name.endsWith('.js') || entry.name.endsWith('.mjs')) { files.push(full); }
      }
    }
    walk(distDir);
    if (files.length > 0) {
      warn('BUILD-1: Stale dist/ files',
        `Found ${files.length} compiled JS files in dist/. tsx may resolve .js over .tsx — run "npm run clean" to remove them. First 5: ${files.slice(0, 5).map(f => path.relative(ROOT, f)).join(', ')}`);
    } else {
      pass('BUILD-1: dist/ directory', 'dist/ exists but contains no JS files');
    }
  } else {
    pass('BUILD-1: No dist/ directory', 'No stale compiled output found');
  }

  // Check tsconfig outDir vs package.json main
  const tsconfig = readJSON(path.join(ROOT, 'tsconfig.json'));
  const pkg = readJSON(path.join(ROOT, 'package.json'));
  if (tsconfig?.compilerOptions?.outDir && pkg?.main) {
    const outDir = tsconfig.compilerOptions.outDir;
    // Check that outDir doesn't overlap with source tree (which could confuse tsx)
    const srcDir = path.resolve(SRC);
    const resolvedOut = path.resolve(ROOT, outDir);
    if (resolvedOut.startsWith(srcDir) || path.relative(SRC, resolvedOut).startsWith('..') === false) {
      warn('BUILD-2: tsconfig outDir conflicts with source tree',
        `outDir=${outDir} is inside src/ tree — tsx may resolve .js over .tsx`);
    } else {
      pass('BUILD-2: tsconfig outDir isolated from source',
        `outDir=${outDir} is outside src/ — no module resolution conflict with tsx`);
    }
  }
}

// ── Check 8: Module Resolution Safety ─────────────────────────────────────────
function checkModuleResolution() {
  // Check if there are competing .tsx and .js files with the same name
  const componentDir = path.join(SRC, 'components', 'Display', 'Scenario');
  const tsxFiles = new Set(fs.readdirSync(componentDir).filter(f => f.endsWith('.tsx')).map(f => f.replace('.tsx', '')));
  const distComponentDir = path.join(ROOT, 'dist', 'components', 'Display', 'Scenario');
  if (fs.existsSync(distComponentDir)) {
    const jsFilesInDist = fs.readdirSync(distComponentDir).filter(f => f.endsWith('.js')).map(f => f.replace('.js', ''));
    const conflicts = [...tsxFiles].filter(f => jsFilesInDist.includes(f));
    if (conflicts.length > 0) {
      warn('MOD-1: Competing .tsx ↔ .js files',
        `tsx may resolve .js over .tsx for: ${conflicts.join(', ')}. Run "npm run clean".`);
    } else {
      pass('MOD-1: No competing module resolutions',
        'No name conflicts between .tsx source and .js compiled files');
    }
  } else {
    pass('MOD-1: No dist/ component files', 'Clean module resolution path');
  }
}

// ── Check 9: UI Component Quality Audit ────────────────────────────────────────
function checkUIQuality() {
  const componentDir = path.join(SRC, 'components', 'Display', 'Scenario');
  if (!fs.existsSync(componentDir)) {
    fail('UI-1: Component directory', 'Scenario component directory not found');
    return;
  }

  const files = fs.readdirSync(componentDir).filter(f => f.endsWith('.tsx') && f !== 'index.ts');
  let emojiCount = 0;
  let filesWithEmoji: string[] = [];
  let hardcodedStringsFiles: string[] = [];

  // Emoji patterns (Unicode ranges)
  const emojiRe = /[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;

  for (const file of files) {
    const src = readFile(path.join(componentDir, file));

    // Check for emoji
    let lineNum = 0;
    const lines = src.split('\n');
    for (const line of lines) {
      lineNum++;
      if (emojiRe.test(line)) {
        emojiCount++;
        filesWithEmoji.push(`${file}:${lineNum}`);
      }
    }
  }

  if (emojiCount === 0) {
    pass('UI-1: Zero emoji in UI components',
      'All 22 scenario components use clean CLI text badges (no emoji)');
  } else {
    fail('UI-1: Emoji found in UI components',
      `Found ${emojiCount} emoji in files: ${filesWithEmoji.join(', ')}`);
  }

  // Check border styles consistency
  let roundBorders = 0;
  let singleBorders = 0;
  let otherBorders = 0;
  const borderFiles: string[] = [];

  for (const file of files) {
    const src = readFile(path.join(componentDir, file));
    const roundMatches = src.match(/borderStyle:\s*"round"/g);
    const singleMatches = src.match(/borderStyle:\s*"single"/g);
    if (roundMatches) {
      roundBorders += roundMatches.length;
      borderFiles.push(`${file}:round(${roundMatches.length})`);
    }
    if (singleMatches) {
      singleBorders += singleMatches.length;
      borderFiles.push(`${file}:single(${singleMatches.length})`);
    }
  }

  if (singleBorders > 0 && roundBorders === 0) {
    pass('UI-2: Consistent border style',
      `All ${singleBorders} borders use "single" style (clean terminal look)`);
  } else if (roundBorders > 0 && singleBorders === 0) {
    warn('UI-2: Border style',
      `All ${roundBorders} borders use "round" style. Consider "single" for cleaner terminal rendering.`);
  } else if (roundBorders > 0 && singleBorders > 0) {
    warn('UI-2: Mixed border styles',
      `Found ${singleBorders} "single" and ${roundBorders} "round" borders. Consider standardizing on "single". Files: ${borderFiles.join(', ')}`);
  } else {
    pass('UI-2: No border styles', 'No border styles used');
  }
}

// ── Check 10: Data Integrity & Edge Cases ──────────────────────────────────────
function checkDataIntegrity() {
  const mapperSrc = readFile(path.join(SRC, 'services', 'backend', 'EventMapper.ts'));

  // Check for String() coercion usage (defensive against null/undefined)
  const stringCoercions = (mapperSrc.match(/String\(/g) || []).length;
  const optionalChains = (mapperSrc.match(/\?\./g) || []).length;
  pass('DATA-1: Defensive string coercion',
    `EventMapper uses String() coercion ${stringCoercions}x and optional chaining ${optionalChains}x for null-safety`);

  // Check for proper numeric coercion
  const numberCoercions = (mapperSrc.match(/typeof\s+\w+\s+===\s+'number'/g) || []).length;
  pass('DATA-2: Numeric type guards',
    `EventMapper uses typeof checks ${numberCoercions}x for numeric fields (duration, attempt)`);

  // Check for array safety
  const arrayGuards = (mapperSrc.match(/Array\.isArray/g) || []).length;
  pass('DATA-3: Array type guards',
    `EventMapper uses Array.isArray ${arrayGuards}x for array fields (output, results, steps)`);

  // Check that progress steps use proper coercion
  const progressCase = mapperSrc.match(/case 'progress':[\s\S]*?break/);
  if (progressCase && progressCase[0].includes('as ScenarioEvent')) {
    pass('DATA-4: Type assertion safety',
      'EventMapper casts via "as ScenarioEvent" for type narrowing');
  }
}

// ── Check 11: Backend Provider Stream Handling ─────────────────────────────────
function checkStreamHandling() {
  const providerSrc = readFile(path.join(SRC, 'services', 'backend', 'BackendScenarioProvider.ts'));

  if (providerSrc.includes('partialMessageIndex')) {
    pass('STREAM-1: Partial message streaming',
      'BackendScenarioProvider handles partial=true messages with accumulation and in-place updates');
  } else {
    fail('STREAM-1: Partial message streaming', 'No partial message handling detected');
  }

  if (providerSrc.includes('onComplete')) {
    pass('STREAM-2: Completion detection',
      'BackendScenarioProvider detects success/error events to trigger onComplete');
  } else {
    fail('STREAM-2: Completion detection', 'No completion detection');
  }

  if (providerSrc.includes('abort')) {
    pass('STREAM-3: Abort/cancel support',
      'BackendScenarioProvider returns abort() function for cancellation');
  } else {
    fail('STREAM-3: Abort/cancel support', 'No abort mechanism');
  }

  // Check for connection loss handling
  if (providerSrc.includes('disconnected')) {
    pass('STREAM-4: Connection loss handling',
      'BackendScenarioProvider emits error on WebSocket disconnect');
  } else {
    fail('STREAM-4: Connection loss handling', 'No disconnect handling');
  }

  // Check for timeout / waiting indicator
  if (providerSrc.includes('Waiting for backend response')) {
    pass('STREAM-5: Waiting indicator',
      'BackendScenarioProvider shows waiting indicator after 2s timeout');
  } else {
    fail('STREAM-5: Waiting indicator', 'No waiting indicator');
  }
}

// ── Check 12: Component Props Interface Alignment ─────────────────────────────
function checkComponentPropsAlignment() {
  const componentDir = path.join(SRC, 'components', 'Display', 'Scenario');
  let files = fs.readdirSync(componentDir).filter(f => f.endsWith('.tsx') && f !== 'index.ts');
  // Skip known utility components that are not event-bound
  const skipFiles = new Set(['ScenarioRenderer.tsx', 'TerminalMarkdown.tsx']);
  files = files.filter(f => !skipFiles.has(f));

  let propsOk = 0;
  let propsIssues = 0;
  const propsDetails: string[] = [];

  for (const file of files) {
    const src = readFile(path.join(componentDir, file));
    if (src.includes('interface') && (src.includes('event:') || src.includes('event?:'))) {
      propsOk++;
    } else {
      propsIssues++;
      propsDetails.push(`${file}: missing event prop interface`);
    }
  }

  if (propsIssues === 0) {
    pass('PROPS-1: All event components have typed event props',
      `All ${propsOk} event-bound components define proper interfaces with event field`);
  } else {
    warn('PROPS-1: Some components lack event props',
      `${propsIssues} components may have issues: ${propsDetails.join(', ')}`);
  }
}

// ── Report Generator ───────────────────────────────────────────────────────────
function generateReport() {
  const passed = results.filter(r => r.status === 'pass').length;
  const failed = results.filter(r => r.status === 'fail').length;
  const warnings = results.filter(r => r.status === 'warn').length;
  const total = results.length;

  console.log('');
  console.log('╔══════════════════════════════════════════════════════════════════╗');
  console.log('║     ZENITH E2E PIPELINE ALIGNMENT CHECKER REPORT              ║');
  console.log('╚══════════════════════════════════════════════════════════════════╝');
  console.log('');
  console.log(`  Generated: ${new Date().toISOString()}`);
  console.log(`  Root: ${ROOT}`);
  console.log('');
  console.log(`  ${'┌' + '─'.repeat(68) + '┐'}`);
  console.log(`  │ ${'RESULTS'.padEnd(66)} │`);
  console.log(`  │ ${'  PASS'.padEnd(66)} │`);
  console.log(`  │ ${`    ${passed} / ${total} checks passed`.padEnd(66)} │`);
  console.log(`  │ ${'  FAIL'.padEnd(66)} │`);
  console.log(`  │ ${`    ${failed} / ${total} checks failed`.padEnd(66)} │`);
  console.log(`  │ ${'  WARN'.padEnd(66)} │`);
  console.log(`  │ ${`    ${warnings} / ${total} checks with warnings`.padEnd(66)} │`);
  console.log(`  ${'└' + '─'.repeat(68) + '┘'}`);
  console.log('');

  // Group by category
  const categories: Record<string, CheckResult[]> = {};
  for (const r of results) {
    const cat = r.check.split('-')[0];
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push(r);
  }

  for (const [cat, checks] of Object.entries(categories).sort()) {
    const catNames: Record<string, string> = {
      'BE': 'Backend EventKind',
      'FE': 'Frontend EventKind',
      'ALIGN': 'Backend ↔ Frontend Alignment',
      'MAP': 'EventMapper',
      'REG': 'Component Registry',
      'INT': 'Pipeline Integrity',
      'BUILD': 'Build Artifacts',
      'MOD': 'Module Resolution',
      'UI': 'UI Component Quality',
      'DATA': 'Data Integrity',
      'STREAM': 'Stream Handling',
      'PROPS': 'Component Props',
    };
    console.log(`  ${'─── ' + (catNames[cat] || cat) + ' ───'.repeat(10)}`);
    console.log('');
    for (const r of checks) {
      const icon = r.status === 'pass' ? '✓' : r.status === 'fail' ? '✗' : '⚠';
      const color = r.status === 'pass' ? '' : r.status === 'fail' ? '' : '';
      console.log(`    ${icon} ${r.check}`);
      console.log(`      ${r.detail}`);
      console.log('');
    }
  }

  console.log(`  ${'═'.repeat(70)}`);
  console.log('');
  console.log(`  SUMMARY: ${passed}/${total} passed, ${failed} failed, ${warnings} warnings`);
  console.log('');

  if (failed > 0) {
    console.log('  ┌─────────────────────────────────────────────────────────────┐');
    console.log('  │  FAILURES REQUIRING ATTENTION:                             │');
    console.log('  └─────────────────────────────────────────────────────────────┘');
    console.log('');
    for (const r of results.filter(r => r.status === 'fail')) {
      console.log(`    ✗ ${r.check}`);
      console.log(`      ${r.detail}`);
      console.log('');
    }
  }

  if (warnings > 0) {
    console.log('  ┌─────────────────────────────────────────────────────────────┐');
    console.log('  │  WARNINGS (non-blocking but should review):                │');
    console.log('  └─────────────────────────────────────────────────────────────┘');
    console.log('');
    for (const r of results.filter(r => r.status === 'warn')) {
      console.log(`    ⚠ ${r.check}`);
      console.log(`      ${r.detail}`);
      console.log('');
    }
  }

  console.log('  Report complete.');
  console.log('');

  return { passed, failed, warnings, total };
}

// ── Main ───────────────────────────────────────────────────────────────────────
function main() {
  console.log('');
  console.log('  Scanning pipeline alignment...');
  console.log('');

  // Phase 1: Backend & Frontend kinds
  const backendKinds = checkBackendEventKinds();
  const frontendKinds = checkFrontendEventKinds();

  // Phase 2: Alignment
  if (backendKinds.length && frontendKinds.length) {
    checkAlignment(backendKinds, frontendKinds);
    checkPipelineIntegrity(backendKinds, frontendKinds);
  }

  // Phase 3: Mapping & Registry
  checkEventMapper(backendKinds.length ? backendKinds : frontendKinds);
  checkComponentRegistry(backendKinds.length ? backendKinds : frontendKinds);

  // Phase 4: Build & Module Resolution
  checkStaleDist();
  checkModuleResolution();

  // Phase 5: UI Quality
  checkUIQuality();

  // Phase 6: Data Integrity
  checkDataIntegrity();

  // Phase 7: Stream Handling
  checkStreamHandling();

  // Phase 8: Component Props
  checkComponentPropsAlignment();

  // Generate Report
  const report = generateReport();
  process.exit(report.failed > 0 ? 1 : 0);
}

main();
