import { Box, Text } from 'ink';
import React, { Component, useMemo } from 'react';
import { ASCII_SPINNER_FRAMES } from '../../../constants/animation';
import { useTickAnimation } from '../../../hooks/useTickAnimation';
import { useTheme } from '../../../theme/ThemeContext';
import { componentRegistry } from './componentRegistry';
const LiveSpinner = React.memo(({ label }) => {
    const spinnerTick = useTickAnimation(100);
    const { theme } = useTheme();
    return (React.createElement(Box, { flexDirection: "column", width: "100%", marginBottom: 1, paddingX: 1 },
        React.createElement(Box, { flexDirection: "row", alignItems: "center", flexWrap: "wrap" },
            React.createElement(Text, { color: theme.colors.status.info, bold: true },
                "[IN PROGRESS]",
                ' '),
            React.createElement(Text, { color: theme.colors.status.success, bold: true },
                ASCII_SPINNER_FRAMES[spinnerTick % ASCII_SPINNER_FRAMES.length],
                ' '),
            React.createElement(Text, { color: theme.colors.text.bright, bold: true }, label),
            React.createElement(Text, { color: theme.colors.text.muted }, " (Press ESC to cancel)"))));
});
class EventErrorBoundary extends Component {
    state = { hasError: false };
    static getDerivedStateFromError() {
        return { hasError: true };
    }
    render() {
        if (this.state.hasError) {
            return (React.createElement(Box, { paddingX: 1, marginBottom: 1 },
                React.createElement(Text, { color: this.props.errorColor },
                    "[Render error in ",
                    this.props.eventKind,
                    " event \u2014 skipped]")));
        }
        return this.props.children;
    }
}
export const ScenarioRenderer = React.memo(({ events, isRunning, isHistorical = false, thinkingCollapsed = false, onRetry, onDismiss }) => {
    const { theme } = useTheme();
    const showLiveIndicator = isRunning && !isHistorical;
    const renderContext = useMemo(() => ({
        thinkingCollapsed,
        isHistorical,
        isRunning,
        onRetry,
        onDismiss,
    }), [thinkingCollapsed, isHistorical, isRunning, onRetry, onDismiss]);
    // Use a limit for dynamic rendering to avoid Ink scrolling bugs.
    // For historical (Static) renders, show all events.
    const dynamicLimit = 20;
    const hasOverflow = !isHistorical && events.length > dynamicLimit;
    const visibleEvents = hasOverflow ? events.slice(-dynamicLimit) : events;
    return (React.createElement(Box, { flexDirection: "column", width: "100%" },
        hasOverflow && (React.createElement(Box, { paddingX: 1, marginBottom: 1 },
            React.createElement(Text, { color: theme.colors.text.muted, italic: true },
                "... ",
                events.length - dynamicLimit,
                " earlier events hidden"))),
        visibleEvents.map((event) => {
            const Component = componentRegistry.getComponent(event.kind);
            return (React.createElement(EventErrorBoundary, { key: event.id, eventKind: event.kind, errorColor: theme.colors.status.warning },
                React.createElement(Component, { event: event, context: renderContext })));
        }),
        showLiveIndicator && React.createElement(LiveSpinner, { label: '' })));
});
