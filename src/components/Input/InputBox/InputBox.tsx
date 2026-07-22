import React from 'react';
import { Box, Text, useInput } from 'ink';
import TextInput from 'ink-text-input';
import { useTheme } from '../../../theme/ThemeContext';
import { AutocompleteDropdown } from '../AutocompleteDropdown';
import { SettingsScreen } from '../../../screens/Settings';
import { ThemeScreen } from '../../../screens/Settings/Theme';
import { PluginsScreen } from '../../../screens/Settings/Plugins';
import { ContextModal } from '../../Display/ContextModal';
import { AccountScreen } from '../../../screens/Settings/Account';
import { InputBoxProps } from './types';

export const InputBox: React.FC<InputBoxProps> = ({
  input,
  setInput,
  overlay,
  setOverlay,
  isExecuting,
  executeCommand,
  persona,
  setPersona,
  autoApprove,
  setAutoApprove,
}) => {
  const { theme } = useTheme();

  useInput((char, key) => {
    if (isExecuting) return;
    if (overlay !== 'none' && overlay !== 'autocomplete') return;

    if (char === '/') {
      setOverlay('autocomplete');
    }

    if (key.escape && overlay === 'autocomplete') {
      setOverlay('none');
    }
  });

  const handleSubmit = (val: string) => {
    if (overlay === 'autocomplete') return;

    if (val.trim() === '/settings') {
      setOverlay('settings');
      setInput('');
      return;
    }
    if (val.trim() === '/context') {
      setOverlay('context');
      setInput('');
      return;
    }
    if (val.trim() === '/persona') {
      setOverlay('persona');
      setInput('');
      return;
    }

    setOverlay('none');
    setInput('');
    executeCommand(val);
  };

  const handleAutocompleteSelect = (cmd: string) => {
    if (cmd.startsWith('/plugin')) {
      setOverlay('plugin');
      setInput('');
    } else if (cmd.startsWith('/settings')) {
      setOverlay('settings');
      setInput('');
    } else if (cmd.startsWith('/context')) {
      setOverlay('context');
      setInput('');
    } else if (cmd.startsWith('/persona')) {
      setOverlay('persona');
      setInput('');
    } else {
      setInput(cmd);
      setOverlay('none');
    }
  };

  const triggerPluginMock = (cmd: string) => {
    setOverlay('none');
    setInput('');
    executeCommand(cmd);
  };

  return (
    <Box flexDirection="column" marginTop={1}>
      <Box flexDirection="row">
        <Text color={theme.colors.text.muted}>{'> '}</Text>
        <TextInput value={input} onChange={setInput} onSubmit={handleSubmit} focus={overlay === 'none' || overlay === 'autocomplete'} />
      </Box>

      {overlay === 'autocomplete' && (
        <Box marginTop={1}><AutocompleteDropdown input={input} onSelect={handleAutocompleteSelect} /></Box>
      )}
      {overlay === 'plugin' && (
        <Box marginTop={1}><PluginsScreen onClose={() => setOverlay('none')} onTriggerMock={triggerPluginMock} /></Box>
      )}
      {overlay === 'settings' && (
        <Box marginTop={1}><SettingsScreen
          onClose={() => setOverlay('none')}
          onOpenTheme={() => setOverlay('theme')}
          autoApprove={autoApprove}
          setAutoApprove={setAutoApprove}
        /></Box>
      )}
      {overlay === 'theme' && (
        <Box marginTop={1}><ThemeScreen onClose={() => setOverlay('none')} /></Box>
      )}
      {overlay === 'context' && (
        <Box marginTop={1}><ContextModal onClose={() => setOverlay('none')} /></Box>
      )}
      {overlay === 'persona' && (
        <Box marginTop={1}><AccountScreen currentPersona={persona} onSelect={(p) => setPersona(p)} onClose={() => setOverlay('none')} /></Box>
      )}
    </Box>
  );
};
