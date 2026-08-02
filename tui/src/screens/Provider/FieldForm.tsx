import { Box, Text, useInput } from 'ink';
import React, { useCallback, useState } from 'react';
import { useTheme } from '../../theme/ThemeContext';

export interface FormField {
  key: string;
  label: string;
  type: 'password' | 'text' | 'number' | 'select';
  placeholder?: string;
  required?: boolean;
  defaultValue?: string | number;
  description?: string;
  options?: { label: string; value: string }[];
}

interface FieldFormProps {
  title: string;
  fields: FormField[];
  onSubmit: (values: Record<string, string>) => void;
  onCancel: () => void;
  hint?: string;
}

/** Multi-field dialog form. Up/Down/Tab move focus; typing edits the focused
 * field; Enter submits; Esc cancels. */
export const FieldForm: React.FC<FieldFormProps> = ({ title, fields, onSubmit, onCancel, hint }) => {
  const { theme } = useTheme();
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(fields.map((field) => [field.key, String(field.defaultValue ?? '')])),
  );
  const [cursors, setCursors] = useState<Record<string, number>>(() =>
    Object.fromEntries(fields.map((field) => [field.key, String(field.defaultValue ?? '').length])),
  );
  const [focused, setFocused] = useState(0);

  const editField = useCallback(
    (
      char: string,
      key: {
        leftArrow?: boolean;
        rightArrow?: boolean;
        home?: boolean;
        end?: boolean;
        delete?: boolean;
        backspace?: boolean;
      },
      fieldKey: string,
    ) => {
      const value = values[fieldKey] ?? '';
      const cursor = cursors[fieldKey] ?? value.length;
      if (key.leftArrow) {
        setCursors((c) => ({ ...c, [fieldKey]: Math.max(0, cursor - 1) }));
        return;
      }
      if (key.rightArrow) {
        setCursors((c) => ({ ...c, [fieldKey]: Math.min(value.length, cursor + 1) }));
        return;
      }
      if (key.home) {
        setCursors((c) => ({ ...c, [fieldKey]: 0 }));
        return;
      }
      if (key.end) {
        setCursors((c) => ({ ...c, [fieldKey]: value.length }));
        return;
      }
      if (key.delete) {
        if (cursor >= value.length) return;
        const chars = [...value];
        chars.splice(cursor, 1);
        setValues((v) => ({ ...v, [fieldKey]: chars.join('') }));
        return;
      }
      if (key.backspace) {
        if (cursor <= 0) return;
        const chars = [...value];
        chars.splice(cursor - 1, 1);
        setValues((v) => ({ ...v, [fieldKey]: chars.join('') }));
        setCursors((c) => ({ ...c, [fieldKey]: Math.max(0, cursor - 1) }));
        return;
      }
      if (!char) return;
      const chars = [...value];
      chars.splice(cursor, 0, char);
      setValues((v) => ({ ...v, [fieldKey]: chars.join('') }));
      setCursors((c) => ({ ...c, [fieldKey]: cursor + [...char].length }));
    },
    [values, cursors],
  );

  const confirm = useCallback(() => {
    const missingIdx = fields.findIndex((field) => field.required && !(values[field.key] ?? '').trim());
    if (missingIdx >= 0) {
      setFocused(missingIdx);
      return;
    }
    onSubmit(values);
  }, [fields, values, onSubmit]);

  useInput((char, key) => {
    if (key.escape) {
      onCancel();
      return;
    }
    if (key.upArrow) {
      setFocused((f) => Math.max(0, f - 1));
      return;
    }
    if (key.downArrow || key.tab) {
      setFocused((f) => Math.min(fields.length - 1, f + 1));
      return;
    }
    if (key.return) {
      confirm();
      return;
    }
    const field = fields[focused];
    if (field) editField(char, key, field.key);
  });

  return (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" justifyContent="space-between" paddingLeft={2} paddingRight={2}>
        <Text color={theme.colors.text.ethereal} bold>
          {title}
        </Text>
        <Text color={theme.colors.text.muted}>esc</Text>
      </Box>
      <Box flexDirection="column" marginTop={1} gap={1}>
        {fields.map((field, idx) => {
          const isFocused = idx === focused;
          const value = values[field.key] ?? '';
          const cursor = cursors[field.key] ?? value.length;
          const displayValue = field.type === 'password' ? '•'.repeat(value.length) : value;
          return (
            <Box key={field.key} flexDirection="column" paddingLeft={2} paddingRight={2}>
              <Box flexDirection="row">
                <Text color={isFocused ? theme.colors.status.success : theme.colors.text.muted} bold={isFocused}>
                  {isFocused ? '▸ ' : '  '}
                  {field.label}
                  {field.required ? ' *' : ''}
                </Text>
              </Box>
              <Box paddingLeft={2} flexDirection="row">
                <Text color={theme.colors.text.ethereal}>
                  {displayValue.slice(0, cursor)}
                  <Text color={theme.colors.status.accent} inverse>
                    {displayValue[cursor] ?? ' '}
                  </Text>
                  {displayValue.slice(cursor + 1)}
                  {displayValue.length === 0 && <Text color={theme.colors.text.dim}>{field.placeholder ?? ''}</Text>}
                </Text>
              </Box>
              {field.description && (
                <Box paddingLeft={2}>
                  <Text color={theme.colors.text.dim} italic>
                    {field.description}
                  </Text>
                </Box>
              )}
            </Box>
          );
        })}
      </Box>
      <Box
        flexDirection="row"
        justifyContent="space-between"
        marginTop={1}
        paddingLeft={2}
        paddingRight={2}
        paddingBottom={1}
      >
        <Text color={theme.colors.text.muted} italic>
          {hint ?? '↑↓ — Field  |  Enter — Submit'}
        </Text>
        <Text color={theme.colors.text.muted}>
          <Text color={theme.colors.status.success}>⏎</Text> submit
        </Text>
      </Box>
    </Box>
  );
};
