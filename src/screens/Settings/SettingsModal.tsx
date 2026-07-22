import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { loadUserProfile, saveUserProfile, type UserProfile } from '../../services/data/userProfileService';
import { useTheme } from '../../theme/ThemeContext';

interface SettingsModalProps {
  onClose: () => void;
}

interface ThemeOption {
  id: string;
  name: string;
  swatch: string[];
}

const THEME_OPTIONS: ThemeOption[] = [
  { id: 'graphite', name: 'Graphite Monochrome (Default)', swatch: ['#E0E0E0', '#A0A0A0', '#707070', '#444444'] },
  { id: 'stealth', name: 'Stealth Tactical (Lowkey Slate)', swatch: ['#7DA396', '#6B8E9C', '#B89C6D', '#BD6B6B'] },
  { id: 'deep_forest', name: 'Deep Forest', swatch: ['#50C878', '#8FBC8F', '#DAA520', '#FF6B6B'] },
  { id: 'dracula', name: 'Dracula', swatch: ['#BD93F9', '#50FA7B', '#8BE9FD', '#FF79C6'] },
  { id: 'monokai', name: 'Monokai Pro', swatch: ['#A6E22E', '#66D9EF', '#FD971F', '#F92672'] },
  { id: 'synthwave', name: 'Synthwave 84', swatch: ['#F92A82', '#00F2FE', '#F39C12', '#BC7FD4'] },
  { id: 'aura', name: 'Aura Dark', swatch: ['#61FFCA', '#82E2FF', '#A277FF', '#FF6767'] },
];

export const SettingsModal: React.FC<SettingsModalProps> = ({ onClose }) => {
  const { theme, activeThemeId, setTheme } = useTheme();
  const [userProfile, setUserProfile] = useState<UserProfile>(() => loadUserProfile());
  const [activeTab, setActiveTab] = useState<'theme' | 'preferences'>('theme');

  const currentThemeIdx = THEME_OPTIONS.findIndex((t) => t.id === activeThemeId);
  const [selectedThemeIdx, setSelectedThemeIdx] = useState(currentThemeIdx >= 0 ? currentThemeIdx : 0);
  const [prefCursor, setPrefCursor] = useState(0);

  const toggleAutoApprove = () => {
    const updated = !userProfile.autoApproveTools;
    setUserProfile((prev) => ({ ...prev, autoApproveTools: updated }));
    saveUserProfile({ autoApproveTools: updated });
  };

  const toggleCompactView = () => {
    const updated = !userProfile.compactView;
    setUserProfile((prev) => ({ ...prev, compactView: updated }));
    saveUserProfile({ compactView: updated });
  };

  const toggleThinkingCollapsed = () => {
    const updated = !userProfile.thinkingCollapsed;
    setUserProfile((prev) => ({ ...prev, thinkingCollapsed: updated }));
    saveUserProfile({ thinkingCollapsed: updated });
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
    } else {
      if (key.upArrow) {
        setPrefCursor((prev) => Math.max(0, prev - 1));
      }

      if (key.downArrow) {
        setPrefCursor((prev) => Math.min(2, prev + 1));
      }

      if (key.return || char === ' ') {
        if (prefCursor === 0) toggleAutoApprove();
        if (prefCursor === 1) toggleCompactView();
        if (prefCursor === 2) toggleThinkingCollapsed();
      }
    }

    if (key.escape || (activeTab === 'theme' && key.return)) {
      onClose();
    }
  });

  return (
    <RoundedBox title="DEVELOPER SETTINGS & CACHE CONTROL" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        {/* Navigation Tabs */}
        <Box
          flexDirection="row"
          marginBottom={1}
          borderStyle="single"
          borderBottom={true}
          borderColor={theme.colors.border.muted}
        >
          <Box marginRight={3}>
            <Text
              color={activeTab === 'theme' ? theme.colors.status.success : theme.colors.text.muted}
              bold={activeTab === 'theme'}
              underline={activeTab === 'theme'}
            >
              [1] UI Themes
            </Text>
          </Box>
          <Box>
            <Text
              color={activeTab === 'preferences' ? theme.colors.status.success : theme.colors.text.muted}
              bold={activeTab === 'preferences'}
              underline={activeTab === 'preferences'}
            >
              [2] Developer Session Cache
            </Text>
          </Box>
        </Box>

        {activeTab === 'theme' ? (
          <Box flexDirection="column">
            {THEME_OPTIONS.map((t, idx) => {
              const isSelected = idx === selectedThemeIdx;
              const isActive = t.id === activeThemeId;

              return (
                <Box key={t.id} flexDirection="row" alignItems="center" marginY={0} width="100%">
                  <Box width={3}>
                    <Text color={isSelected ? theme.colors.text.emerald : theme.colors.text.dim}>
                      {isSelected ? '▸ ' : '  '}
                    </Text>
                  </Box>

                  <Box width={26} flexShrink={0}>
                    <Text color={isSelected ? theme.colors.text.ethereal : theme.colors.text.dim} bold={isSelected}>
                      {t.name}
                    </Text>
                  </Box>

                  <Box flexDirection="row" marginRight={2}>
                    {t.swatch.map((c, i) => (
                      <Text key={i} color={c}>
                        █
                      </Text>
                    ))}
                  </Box>

                  {isActive && (
                    <Text color={theme.colors.status.success} bold>
                      [ACTIVE]
                    </Text>
                  )}
                </Box>
              );
            })}
          </Box>
        ) : (
          <Box flexDirection="column">
            {/* Preference Option 1: Auto Approve Tools */}
            <Box flexDirection="row" alignItems="center" marginY={1}>
              <Box width={3}>
                <Text color={prefCursor === 0 ? theme.colors.text.emerald : theme.colors.text.dim}>
                  {prefCursor === 0 ? '▸ ' : '  '}
                </Text>
              </Box>
              <Box width={30}>
                <Text
                  color={prefCursor === 0 ? theme.colors.text.bright : theme.colors.text.dim}
                  bold={prefCursor === 0}
                >
                  Auto-Approve Tool Execution
                </Text>
              </Box>
              <Text color={userProfile.autoApproveTools ? theme.colors.status.success : theme.colors.status.error} bold>
                {userProfile.autoApproveTools ? '[ENABLED]' : '[DISABLED]'}
              </Text>
            </Box>

            {/* Preference Option 2: Compact View Density */}
            <Box flexDirection="row" alignItems="center" marginY={1}>
              <Box width={3}>
                <Text color={prefCursor === 1 ? theme.colors.text.emerald : theme.colors.text.dim}>
                  {prefCursor === 1 ? '▸ ' : '  '}
                </Text>
              </Box>
              <Box width={30}>
                <Text
                  color={prefCursor === 1 ? theme.colors.text.bright : theme.colors.text.dim}
                  bold={prefCursor === 1}
                >
                  Compact Interface Density
                </Text>
              </Box>
              <Text color={userProfile.compactView ? theme.colors.status.success : theme.colors.text.muted} bold>
                {userProfile.compactView ? '[ENABLED]' : '[DISABLED]'}
              </Text>
            </Box>

            {/* Preference Option 3: Thinking Chain-of-Thought Collapse */}
            <Box flexDirection="row" alignItems="center" marginY={1}>
              <Box width={3}>
                <Text color={prefCursor === 2 ? theme.colors.text.emerald : theme.colors.text.dim}>
                  {prefCursor === 2 ? '▸ ' : '  '}
                </Text>
              </Box>
              <Box width={30}>
                <Text
                  color={prefCursor === 2 ? theme.colors.text.bright : theme.colors.text.dim}
                  bold={prefCursor === 2}
                >
                  Thinking Block Display State
                </Text>
              </Box>
              <Text color={userProfile.thinkingCollapsed ? theme.colors.status.warning : theme.colors.status.info} bold>
                {userProfile.thinkingCollapsed ? '[COLLAPSED]' : '[EXPANDED]'}
              </Text>
            </Box>
          </Box>
        )}

        {/* Modal Controls Footer */}
        <Box marginTop={1} paddingTop={1} borderStyle="single" borderTop={true} borderColor={theme.colors.border.muted}>
          <Text color={theme.colors.text.muted}>
            <Text color={theme.colors.text.emerald}>[Tab]</Text> Switch Tab ·{' '}
            <Text color={theme.colors.text.emerald}>[↑/↓]</Text> Navigate ·{' '}
            <Text color={theme.colors.text.emerald}>[Space/Enter]</Text> Select/Toggle ·{' '}
            <Text color={theme.colors.text.emerald}>[Esc]</Text> Exit
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
