import { Box } from 'ink';
import React from 'react';
import { ContextModal } from '../screens/Context/ContextModal';
import { HelpModal } from '../screens/Help/HelpModal';
import { ModeSelectScreen } from '../screens/ModeSelect';
import { SettingsModal } from '../screens/Settings/SettingsModal';
import { SetupWizard } from '../screens/SetupWizard';
import UsageModal from '../screens/Usage/UsageModal';
export const OverlayRouter = ({ overlay, isOverlayOpen, selectedMode, totalTokens, events, startupState, onSelectMode, onClose, onComplete, }) => {
    if (!isOverlayOpen)
        return null;
    return (React.createElement(React.Fragment, null,
        overlay === 'mode' && (React.createElement(Box, { flexDirection: "column", marginTop: 1, width: "100%" },
            React.createElement(ModeSelectScreen, { currentMode: selectedMode, onSelect: onSelectMode, onClose: onClose }))),
        overlay === 'help' && (React.createElement(Box, { flexDirection: "column", marginTop: 1, width: "100%" },
            React.createElement(HelpModal, { onClose: onClose }))),
        overlay === 'settings' && (React.createElement(Box, { flexDirection: "column", marginTop: 1, width: "100%" },
            React.createElement(SettingsModal, { onClose: onClose }))),
        overlay === 'context' && (React.createElement(Box, { flexDirection: "column", marginTop: 1, width: "100%" },
            React.createElement(ContextModal, { totalTokens: totalTokens, runningEvents: events, onClose: onClose }))),
        overlay === 'provider' && (React.createElement(Box, { flexDirection: "column", marginTop: 1, width: "100%" },
            React.createElement(SetupWizard, { startupState: startupState, onComplete: onComplete, mode: "reconfigure" }))),
        overlay === 'usage' && (React.createElement(Box, { flexDirection: "column", marginTop: 1, width: "100%" },
            React.createElement(UsageModal, { onClose: onClose })))));
};
