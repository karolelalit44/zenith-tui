import chalk from 'chalk';

// Cool Shade Dracula/Synthwave Palette
const COLORS = {
  keyword: '#FF79C6', // Electric Magenta
  type: '#8BE9FD', // Neon Cyan
  string: '#50FA7B', // Bright Emerald Green
  decorator: '#FFB86C', // Bright Gold/Orange
  number: '#F1FA8C', // Bright Yellow
  comment: '#6272A4', // Muted Lavender Gray
  operator: '#FF79C6', // Pink operator
  plain: '#F8F8F2', // Off-white
};

const KEYWORDS = new Set([
  'import',
  'from',
  'export',
  'default',
  'const',
  'let',
  'var',
  'function',
  'class',
  'return',
  'if',
  'else',
  'switch',
  'case',
  'for',
  'while',
  'do',
  'try',
  'catch',
  'async',
  'await',
  'def',
  'pass',
  'raise',
  'in',
  'is',
  'not',
  'and',
  'or',
  'public',
  'private',
  'protected',
  'extends',
  'implements',
  'interface',
  'type',
]);

const BUILTIN_TYPES = new Set([
  'FastAPI',
  'BaseModel',
  'APIRouter',
  'HTTPException',
  'Optional',
  'List',
  'Dict',
  'User',
  'React',
  'FC',
  'useState',
  'useEffect',
  'useCallback',
  'useMemo',
  'str',
  'int',
  'float',
  'bool',
  'list',
  'dict',
  'set',
  'tuple',
  'string',
  'number',
  'boolean',
  'void',
  'any',
  'unknown',
  'never',
]);

const LITERALS = new Set(['true', 'false', 'True', 'False', 'None', 'null', 'undefined']);

export function highlightCode(code: string, _lang?: string): string {
  if (!code) return '';

  // Handle single-line comments first
  if (code.trim().startsWith('#') || code.trim().startsWith('//')) {
    return chalk.hex(COLORS.comment).italic(code);
  }

  // Tokenize string literals, decorators, keywords, and identifiers
  const tokenRegex = /(".*?"|'.*?'|`.*?`|@\w+(?:\.\w+)*|\b\d+\b|\b[A-Za-z_]\w*\b|[^\s\w])/g;

  return code.replace(tokenRegex, (match) => {
    // Strings
    if (match.startsWith('"') || match.startsWith("'") || match.startsWith('`')) {
      return chalk.hex(COLORS.string)(match);
    }
    // Decorators
    if (match.startsWith('@')) {
      return chalk.hex(COLORS.decorator).bold(match);
    }
    // Numbers
    if (/^\d+$/.test(match)) {
      return chalk.hex(COLORS.number)(match);
    }
    // Keywords
    if (KEYWORDS.has(match)) {
      return chalk.hex(COLORS.keyword).bold(match);
    }
    // Types & Builtins
    if (BUILTIN_TYPES.has(match)) {
      return chalk.hex(COLORS.type).bold(match);
    }
    // Literals
    if (LITERALS.has(match)) {
      return chalk.hex(COLORS.number).bold(match);
    }

    return chalk.hex(COLORS.plain)(match);
  });
}
