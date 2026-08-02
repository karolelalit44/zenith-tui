# Signoff Checklist — Multi-Agent Orchestration

**Date**: 2026-08-02  
**Version**: 1.0  

---

## Overview

This checklist defines the acceptance criteria for each phase. All items must be verified before marking a phase complete.

---

## Phase 1: Orchestration Contract & Event Schema

### Types & Contracts

- [ ] `TaskSpec` dataclass defined with all required fields
- [ ] `TaskResult` dataclass defined with all required fields
- [ ] `TaskState` enum covers all lifecycle states
- [ ] `CaptainState` enum covers all orchestrator states
- [ ] `RetryPolicy` dataclass with configurable parameters
- [ ] `OrchestrationDecision` enum defined (PROCEED, RETRY, ESCALATE, FAIL)

### Events

- [ ] `OrchestrationEventKind` enum includes all Captain events
- [ ] `OrchestrationEventKind` enum includes all Crew events
- [ ] `OrchestrationEventKind` enum includes all orchestration events
- [ ] Events are serializable to JSON
- [ ] Events are deserializable from JSON

### Persistence

- [ ] Database migration created and tested
- [ ] `tasks` table stores task specifications
- [ ] `checkpoints` table stores recovery state
- [ ] `TaskRepository` CRUD operations work correctly
- [ ] `CheckpointStore` save/load works correctly

### Testing

- [ ] Unit tests for all type validations pass
- [ ] Unit tests for event serialization pass
- [ ] Unit tests for task repository pass
- [ ] All new code has >80% test coverage

### Documentation

- [ ] Type definitions documented with docstrings
- [ ] Event schema documented
- [ ] Database schema documented

---

## Phase 2: Captain Orchestrator Service

### Core Functionality

- [ ] `CaptainOrchestrator` class implemented
- [ ] `handle_request` method processes user requests
- [ ] Request analysis extracts objective correctly
- [ ] Strategy building produces valid execution plan
- [ ] Task decomposition creates valid task specs
- [ ] Agent selection chooses appropriate agent type

### Task Management

- [ ] `TaskGraph` class manages dependencies
- [ ] `ready_tasks` returns unblocked tasks
- [ ] `mark_complete` updates dependent tasks
- [ ] `mark_failed` handles failure propagation

### Context Building

- [ ] `ContextBuilder` creates minimal context
- [ ] Context includes only scoped files
- [ ] Context includes prior findings
- [ ] Context excludes irrelevant information

### Integration

- [ ] `CoordinatorService` delegates to Captain
- [ ] `PromptExecutor` routes through Captain
- [ ] Feature flag allows gradual rollout
- [ ] Existing flows work with Captain disabled

### Testing

- [ ] Unit tests for Captain state transitions pass
- [ ] Unit tests for task decomposition pass
- [ ] Unit tests for decision logic pass
- [ ] Integration test for simple request passes
- [ ] Integration test for retry passes

### Performance

- [ ] No measurable latency increase with Captain disabled
- [ ] Event emission is non-blocking
- [ ] Task graph operations are O(n) or better

---

## Phase 3: Crew Agent Registry & Runtime

### Registry

- [ ] `AgentRegistry` class implemented
- [ ] `register` adds agent types
- [ ] `create` instantiates agents with correct config
- [ ] `list_types` returns all registered types

### Crew Agent Base

- [ ] `CrewAgent` abstract class defined
- [ ] `execute` method signature correct
- [ ] `allowed_tools` returns restricted tool set

### Built-in Agents

- [ ] `ResearchAgent` executes read-only research tasks
- [ ] `AnalysisAgent` executes code analysis tasks
- [ ] `GenerationAgent` executes file creation tasks
- [ ] `ValidationAgent` executes lint/test tasks
- [ ] `GitAgent` executes git operations
- [ ] `TerminalAgent` executes shell commands

### Isolation

- [ ] Each agent runs in isolated session
- [ ] Agent cannot access files outside scope
- [ ] Agent cannot use tools outside allowlist
- [ ] Agent state does not leak to other agents

### Testing

- [ ] Unit tests for registry pass
- [ ] Unit tests for each agent type pass
- [ ] Integration test for delegation pass
- [ ] Integration test for isolation pass

---

## Phase 4: Execution Hardening & Recovery

### Retry Logic

- [ ] Retry policy respects max attempts
- [ ] Exponential backoff implemented correctly
- [ ] Context mutated on each retry
- [ ] Retry count tracked in task metadata

### Failure Isolation

- [ ] Agent failure does not crash orchestrator
- [ ] Failure in one agent does not affect others
- [ ] Failure is logged with full context
- [ ] Failure is reported to user appropriately

### Recovery

- [ ] Checkpoint saved after plan creation
- [ ] Checkpoint saved after each task completion
- [ ] Recovery loads correct state
- [ ] Recovery skips completed tasks
- [ ] Recovery continues from last checkpoint

### Cancellation

- [ ] In-flight task can be cancelled
- [ ] Pending tasks can be cancelled
- [ ] Partial results preserved on cancellation
- [ ] User notified of cancellation status

### Testing

- [ ] Unit tests for retry logic pass
- [ ] Unit tests for checkpoint pass
- [ ] Integration test for failure → retry → success passes
- [ ] Integration test for checkpoint → resume passes
- [ ] Integration test for cancellation passes

---

## Phase 5: TUI Dashboard & Agent Cards

### Types & Hooks

- [ ] TypeScript types match backend types
- [ ] `useOrchestration` hook subscribes to events
- [ ] Hook updates state on new events
- [ ] Hook provides timeline data

### Captain Dashboard

- [ ] Dashboard displays current objective
- [ ] Dashboard displays strategy
- [ ] Dashboard displays progress bar
- [ ] Dashboard displays agent counts
- [ ] Dashboard displays current decision

### Crew Agent Cards

- [ ] Card displays agent name and type
- [ ] Card displays current task
- [ ] Card displays status indicator
- [ ] Card displays progress
- [ ] Card displays duration
- [ ] Card displays output summary
- [ ] Card displays errors
- [ ] Card is expandable

### Timeline

- [ ] Timeline displays events chronologically
- [ ] Timeline shows timestamps
- [ ] Timeline shows status icons
- [ ] Timeline events are collapsible

### Activity Panel

- [ ] Panel displays task delegations
- [ ] Panel displays tool invocations
- [ ] Panel displays validation steps
- [ ] Panel displays decision logs
- [ ] Panel is expandable/collapsible

### Integration

- [ ] Dashboard integrated into main layout
- [ ] Cards update in real-time
- [ ] Timeline updates in real-time
- [ ] All components render without errors

### Testing

- [ ] Component tests for dashboard pass
- [ ] Component tests for cards pass
- [ ] Component tests for timeline pass
- [ ] Integration test for event stream → UI update passes

---

## Phase 6: Calm & Detailed Mode

### Mode Toggle

- [ ] Toggle implemented in UI
- [ ] Mode persisted in session
- [ ] Mode switch is instant

### Calm Mode

- [ ] Dashboard hidden in calm mode
- [ ] Agent cards hidden in calm mode
- [ ] Timeline hidden in calm mode
- [ ] Only conversation visible
- [ ] High-level progress indicator visible

### Detailed Mode

- [ ] All orchestration elements visible
- [ ] Real-time updates working
- [ ] Expandable panels working

### Testing

- [ ] Mode toggle test passes
- [ ] Calm mode renders correctly
- [ ] Detailed mode renders correctly

---

## Phase 7: Validation & Signoff

### End-to-End Scenarios

- [ ] Plan mode flow works correctly
- [ ] Build mode flow works correctly
- [ ] Retry scenario works correctly
- [ ] Cancellation scenario works correctly
- [ ] Recovery scenario works correctly
- [ ] Multi-agent scenario works correctly

### Performance

- [ ] Token overhead is acceptable (<10% increase)
- [ ] Event latency is acceptable (<100ms)
- [ ] No blocking in async paths
- [ ] Memory usage is stable

### Regression

- [ ] All existing tests pass
- [ ] Agent loop behavior unchanged (without Captain)
- [ ] Existing sessions work correctly

### Documentation

- [ ] README updated with architecture
- [ ] Developer guide created
- [ ] User guide created

### Final Signoff

- [ ] All previous checklist items complete
- [ ] Code review approved
- [ ] Performance review approved
- [ ] Documentation review approved
- [ ] Product signoff received

---

## Signoff Record

| Phase | Reviewer | Date | Status |
|-------|----------|------|--------|
| Phase 1 | | | Pending |
| Phase 2 | | | Pending |
| Phase 3 | | | Pending |
| Phase 4 | | | Pending |
| Phase 5 | | | Pending |
| Phase 6 | | | Pending |
| Phase 7 | | | Pending |

---

## Notes

- Each phase must be signed off before proceeding to the next
- Any failed items must be addressed before signoff
- Signoff requires all tests passing and documentation complete
