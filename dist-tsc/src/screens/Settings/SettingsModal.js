import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { loadUserProfile, saveUserProfile } from '../../services/data/userProfileService';
import { useTheme } from '../../theme/ThemeContext';
const THEME_OPTIONS = [
    { id: 'graphite', name: 'Graphite Monochrome (Default)', swatch: ['#E0E0E0', '#A0A0A0', '#707070', '#444444'] },
    { id: 'stealth', name: 'Stealth Tactical (Lowkey Slate)', swatch: ['#7DA396', '#6B8E9C', '#B89C6D', '#BD6B6B'] },
    { id: 'deep_forest', name: 'Deep Forest', swatch: ['#50C878', '#8FBC8F', '#DAA520', '#FF6B6B'] },
    { id: 'dracula', name: 'Dracula', swatch: ['#BD93F9', '#50FA7B', '#8BE9FD', '#FF79C6'] },
    { id: 'monokai', name: 'Monokai Pro', swatch: ['#A6E22E', '#66D9EF', '#FD971F', '#F92672'] },
    { id: 'synthwave', name: 'Synthwave 84', swatch: ['#F92A82', '#00F2FE', '#F39C12', '#BC7FD4'] },
    { id: 'aura', name: 'Aura Dark', swatch: ['#61FFCA', '#82E2FF', '#A277FF', '#FF6767'] },
    { id: 'golden_hour', name: 'Golden Hour (Sun & Sky)', swatch: ['#FFD700', '#64B5F6', '#FF8C00', '#FFF3B0'] },
];
export const SettingsModal = ({ onClose }) => {
    const { theme, activeThemeId, setTheme } = useTheme();
    const [userProfile, setUserProfile] = useState(() => loadUserProfile());
    const [activeTab, setActiveTab] = useState('theme');
    const currentThemeIdx = THEME_OPTIONS.findIndex((t) => t.id === activeThemeId);
    const [selectedThemeIdx, setSelectedThemeIdx] = useState(currentThemeIdx >= 0 ? currentThemeIdx : 0);
    const [prefCursor, setPrefCursor] = useState(0);
    const toggleAutoApprove = () => {
        const next = !userProfile.settings.autoApproveTools;
        setUserProfile((prev) => ({ ...prev, settings: { ...prev.settings, autoApproveTools: next } }));
        saveUserProfile({ settings: { ...userProfile.settings, autoApproveTools: next } });
    };
    const toggleThinkingCollapsed = () => {
        const next = !userProfile.settings.thinkingCollapsed;
        setUserProfile((prev) => ({ ...prev, settings: { ...prev.settings, thinkingCollapsed: next } }));
        saveUserProfile({ settings: { ...userProfile.settings, thinkingCollapsed: next } });
    };
    useInput((char, key) => {
        if (key.tab) {
            setActiveTab((prev) => (prev === 'theme' ? 'preferences' : 'theme'));
            return;
        }
        if (activeTab === 'theme') {
            if (key.upArrow) {
                const nextIdx = Math.max(0, selectedThemeIdx - 1);
                setSelectedThemeIdx(nextIdx);
                setTheme(THEME_OPTIONS[nextIdx].id);
            }
            if (key.downArrow) {
                const nextIdx = Math.min(THEME_OPTIONS.length - 1, selectedThemeIdx + 1);
                setSelectedThemeIdx(nextIdx);
                setTheme(THEME_OPTIONS[nextIdx].id);
            }
        }
        else {
            if (key.upArrow) {
                setPrefCursor((prev) => Math.max(0, prev - 1));
            }
            if (key.downArrow) {
                setPrefCursor((prev) => Math.min(1, prev + 1));
            }
            if (key.return || char === ' ') {
                if (prefCursor === 0)
                    toggleAutoApprove();
                if (prefCursor === 1)
                    toggleThinkingCollapsed();
            }
        }
        if (key.escape || (activeTab === 'theme' && key.return)) {
            onClose();
        }
    });
    return (React.createElement(RoundedBox, { title: "DEVELOPER SETTINGS & CACHE CONTROL", borderColor: theme.colors.border.active, hasShadow: true },
        React.createElement(Box, { flexDirection: "column", paddingX: 2, paddingY: 1, width: "100%" },
            React.createElement(Box, { flexDirection: "row", marginBottom: 1, borderStyle: "single", borderBottom: true, borderTop: false, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                React.createElement(Box, { marginRight: 3 },
                    React.createElement(Text, { color: activeTab === 'theme' ? theme.colors.status.success : theme.colors.text.muted, bold: activeTab === 'theme', underline: activeTab === 'theme' }, "[1] UI Themes")),
                React.createElement(Box, null,
                    React.createElement(Text, { color: activeTab === 'preferences' ? theme.colors.status.success : theme.colors.text.muted, bold: activeTab === 'preferences', underline: activeTab === 'preferences' }, "[2] Developer Session Cache"))),
            activeTab === 'theme' ? (React.createElement(Box, { flexDirection: "column" }, THEME_OPTIONS.map((t, idx) => {
                const isSelected = idx === selectedThemeIdx;
                const isActive = t.id === activeThemeId;
                return (React.createElement(Box, { key: t.id, flexDirection: "row", alignItems: "center", marginY: 0, width: "100%" },
                    React.createElement(Box, { width: 3 },
                        React.createElement(Text, { color: isSelected ? theme.colors.text.emerald : theme.colors.text.dim }, isSelected ? '▸ ' : '  ')),
                    React.createElement(Box, { width: 26, flexShrink: 0 },
                        React.createElement(Text, { color: isSelected ? theme.colors.text.ethereal : theme.colors.text.dim, bold: isSelected }, t.name)),
                    React.createElement(Box, { flexDirection: "row", marginRight: 2 }, t.swatch.map((c, i) => (React.createElement(Text, { key: i, color: c }, "\u2588")))),
                    isActive && (React.createElement(Text, { color: theme.colors.status.success, bold: true }, "[ACTIVE]"))));
            }))) : (React.createElement(Box, { flexDirection: "column" },
                React.createElement(Box, { flexDirection: "row", alignItems: "center", marginY: 1 },
                    React.createElement(Box, { width: 3 },
                        React.createElement(Text, { color: prefCursor === 0 ? theme.colors.text.emerald : theme.colors.text.dim }, prefCursor === 0 ? '▸ ' : '  ')),
                    React.createElement(Box, { width: 30 },
                        React.createElement(Text, { color: prefCursor === 0 ? theme.colors.text.bright : theme.colors.text.dim, bold: prefCursor === 0 }, "Auto-Approve Tool Execution")),
                    React.createElement(Text, { color: userProfile.settings.autoApproveTools ? theme.colors.status.success : theme.colors.status.error, bold: true }, userProfile.settings.autoApproveTools ? '[ENABLED]' : '[DISABLED]')),
                React.createElement(Box, { flexDirection: "row", alignItems: "center", marginY: 1 },
                    React.createElement(Box, { width: 3 },
                        React.createElement(Text, { color: prefCursor === 1 ? theme.colors.text.emerald : theme.colors.text.dim }, prefCursor === 1 ? '▸ ' : '  ')),
                    React.createElement(Box, { width: 30 },
                        React.createElement(Text, { color: prefCursor === 1 ? theme.colors.text.bright : theme.colors.text.dim, bold: prefCursor === 1 }, "Thinking Block Display State")),
                    React.createElement(Text, { color: userProfile.settings.thinkingCollapsed ? theme.colors.status.warning : theme.colors.status.info, bold: true }, userProfile.settings.thinkingCollapsed ? '[COLLAPSED]' : '[EXPANDED]')))),
            React.createElement(Box, { marginTop: 1, paddingTop: 1, borderStyle: "single", borderTop: true, borderBottom: false, borderLeft: false, borderRight: false, borderColor: theme.colors.border.muted },
                React.createElement(Text, { color: theme.colors.text.muted },
                    React.createElement(ModalFooter, { shortcuts: [
                            { key: '[Tab]', label: 'Switch Tab' },
                            { key: '[↑/↓]', label: 'Navigate' },
                            { key: '[Space/Enter]', label: 'Select/Toggle' },
                            { key: '[Esc]', label: 'Exit' },
                        ] }))))));
};
