import { Box, Text, useInput } from 'ink';
import React, { Component, useState } from 'react';
import { useTheme } from '../theme/ThemeContext';
import { RoundedBox } from './ui/RoundedBox';
const ErrorFallback = ({ error, errorInfo, onRetry }) => {
    const { theme } = useTheme();
    const [showDetails, setShowDetails] = useState(false);
    useInput((_char, key) => {
        if (key.escape) {
            onRetry();
        }
        if (key.tab) {
            setShowDetails((prev) => !prev);
        }
    });
    return (React.createElement(RoundedBox, { title: "RUNTIME ERROR", borderColor: theme.colors.status.error, hasShadow: true },
        React.createElement(Box, { flexDirection: "column", paddingX: 2, paddingY: 1, width: "100%" },
            React.createElement(Box, { marginBottom: 1 },
                React.createElement(Text, { color: theme.colors.status.error, bold: true },
                    "[ERROR] ",
                    error.message || 'An unexpected error occurred')),
            showDetails && errorInfo && (React.createElement(Box, { marginBottom: 1, paddingX: 1, borderStyle: "single", borderColor: theme.colors.border.muted },
                React.createElement(Text, { color: theme.colors.text.muted, wrap: "wrap" }, errorInfo.componentStack || 'No stack trace available'))),
            React.createElement(Box, { marginTop: 1, paddingTop: 1, borderStyle: "single", borderTop: true, borderColor: theme.colors.border.muted },
                React.createElement(Text, { color: theme.colors.text.muted },
                    React.createElement(Text, { color: theme.colors.status.info, bold: true }, "[Esc]"),
                    ' ',
                    "Retry",
                    ' · ',
                    React.createElement(Text, { color: theme.colors.status.info, bold: true }, "[Tab]"),
                    ' ',
                    showDetails ? 'Hide' : 'Show',
                    " Details")))));
};
export class ErrorBoundary extends Component {
    state = { hasError: false };
    static getDerivedStateFromError(error) {
        return { hasError: true, error };
    }
    componentDidCatch(error, info) {
        console.error(error, info.componentStack);
        this.setState({ errorInfo: info });
    }
    handleRetry = () => {
        this.setState({ hasError: false, error: undefined, errorInfo: undefined });
    };
    render() {
        if (this.state.hasError && this.state.error) {
            return React.createElement(ErrorFallback, { error: this.state.error, errorInfo: this.state.errorInfo, onRetry: this.handleRetry });
        }
        return this.props.children;
    }
}
