import { ConfirmationCard } from './ConfirmationCard';
import { ErrorBlock } from './ErrorBlock';
import { MessageBlock } from './MessageBlock';
import { ProgressBar } from './ProgressBar';
import { SuccessCard } from './SuccessCard';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolCallCard } from './ToolCallCard';
import { ToolResultCard } from './ToolResultCard';
import { UnknownEventFallback } from './UnknownEventFallback';
import { WarningBlock } from './WarningBlock';
class ComponentRegistry {
    registry = new Map();
    constructor() {
        this.registerDefaults();
    }
    registerDefaults() {
        this.register('thinking', ThinkingBlock);
        this.register('message', MessageBlock);
        this.register('tool_call', ToolCallCard);
        this.register('tool_result', ToolResultCard);
        this.register('error', ErrorBlock);
        this.register('warning', WarningBlock);
        this.register('success', SuccessCard);
        this.register('progress', ProgressBar);
        this.register('confirmation_request', ConfirmationCard);
    }
    register(kind, component) {
        this.registry.set(kind, component);
    }
    getComponent(kind) {
        return this.registry.get(kind) || UnknownEventFallback;
    }
}
export const componentRegistry = new ComponentRegistry();
