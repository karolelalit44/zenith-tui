import { Box, Text, useInput } from 'ink';
import React, { useState } from 'react';
import { ModalFooter } from '../../components/ui/ModalFooter';
import { RoundedBox } from '../../components/ui/RoundedBox';
import { loadUserProfile, saveUserProfile, type UserProfile } from '../../services/api/userProfileService';
import { useTheme } from '../../theme/ThemeContext';
import { themeOptions } from '../../theme/theme';

interface SettingsModalProps {
  onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ onClose }) => {
  const { theme, activeThemeId, setTheme } = useTheme();
  const [userProfile, setUserProfile] = useState<UserProfile>(() => loadUserProfile());
  const [activeTab, setActiveTab] = useState<'theme' | 'preferences'>('theme');

  const currentThemeIdx = themeOptions.findIndex((t) => t.id === activeThemeId);
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
        setTheme(themeOptions[nextIdx].id);
      }

      if (key.downArrow) {
        const nextIdx = Math.min(themeOptions.length - 1, selectedThemeIdx + 1);
        setSelectedThemeIdx(nextIdx);
        setTheme(themeOptions[nextIdx].id);
      }
    } else {
      if (key.upArrow) {
        setPrefCursor((prev) => Math.max(0, prev - 1));
      }

      if (key.downArrow) {
        setPrefCursor((prev) => Math.min(1, prev + 1));
      }

      if (key.return || char === ' ') {
        if (prefCursor === 0) toggleAutoApprove();
        if (prefCursor === 1) toggleThinkingCollapsed();
      }
    }

    if (key.escape || (activeTab === 'theme' && key.return)) {
      onClose();
    }
  });

  return (
    <RoundedBox title="DEVELOPER SETTINGS & CACHE CONTROL" borderColor={theme.colors.border.active} hasShadow={true}>
      <Box flexDirection="column" paddingX={2} paddingY={1} width="100%">
        {}
        <Box
          flexDirection="row"
          marginBottom={1}
          borderStyle="single"
          borderBottom={true}
          borderTop={false}
          borderLeft={false}
          borderRight={false}
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
            {themeOptions.map((t, idx) => {
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
              <Text
                color={userProfile.settings.autoApproveTools ? theme.colors.status.success : theme.colors.status.error}
                bold
              >
                {userProfile.settings.autoApproveTools ? '[ENABLED]' : '[DISABLED]'}
              </Text>
            </Box>

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
                  Thinking Block Display State
                </Text>
              </Box>
              <Text
                color={userProfile.settings.thinkingCollapsed ? theme.colors.status.warning : theme.colors.status.info}
                bold
              >
                {userProfile.settings.thinkingCollapsed ? '[COLLAPSED]' : '[EXPANDED]'}
              </Text>
            </Box>
          </Box>
        )}

        <Box
          marginTop={1}
          paddingTop={1}
          borderStyle="single"
          borderTop={true}
          borderBottom={false}
          borderLeft={false}
          borderRight={false}
          borderColor={theme.colors.border.muted}
        >
          <Text color={theme.colors.text.muted}>
            <ModalFooter
              shortcuts={[
                { key: '[Tab]', label: 'Switch Tab' },
                { key: '[↑/↓]', label: 'Navigate' },
                { key: '[Space/Enter]', label: 'Select/Toggle' },
                { key: '[Esc]', label: 'Exit' },
              ]}
            />
          </Text>
        </Box>
      </Box>
    </RoundedBox>
  );
};
