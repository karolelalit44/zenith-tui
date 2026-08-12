import React, { useCallback, useMemo } from 'react';
import { formatKeyBind } from '../../config/keybind';
import { type CommandDef, type CommandRunContext, commandRegistry } from '../../services/api/CommandRegistry';
import { SearchList, type SearchListOption } from '../ui/SearchList';

interface CommandPaletteProps {
  ctx: CommandRunContext;
  onClose: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ ctx, onClose }) => {
  const options = useMemo<SearchListOption<CommandDef>[]>(
    () =>
      commandRegistry
        .filter((c) => !c.hidden)
        .map((c) => ({
          title: c.title,
          value: c,
          description: c.description,
          category: c.category,
          gutter: c.keybind ? formatKeyBind(c.keybind) : undefined,
        })),
    [],
  );

  const handleSelect = useCallback(
    (option: SearchListOption<CommandDef>) => {
      option.value.run(ctx);
      onClose();
    },
    [ctx, onClose],
  );

  return (
    <SearchList
      title="COMMAND PALETTE"
      options={options}
      onSelect={handleSelect}
      onClose={onClose}
      filterPlaceholder="Type to filter commands…"
      placeholder="↑/↓ navigate · Enter run · Esc close"
    />
  );
};
