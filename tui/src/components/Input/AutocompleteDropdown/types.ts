export interface AutocompleteDropdownProps {
  input: string;
  onSelect: (cmd: string) => void;
  onClose: () => void;
  onQueryChange?: (query: string) => void;
}
