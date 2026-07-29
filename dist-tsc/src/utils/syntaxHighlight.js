import { DEFAULT_THEME, highlight } from 'cli-highlight';
const LANG_MAP = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    py: 'python',
    rs: 'rust',
    sh: 'bash',
    bash: 'bash',
    yml: 'yaml',
    md: 'markdown',
};
const KNOWN_LANGUAGES = new Set(Object.values(LANG_MAP));
const customTheme = {
    ...DEFAULT_THEME,
    string: (str) => `\x1b[36m${str}\x1b[0m`,
    quote: (str) => `\x1b[36m${str}\x1b[0m`,
};
export function highlightCode(code, lang) {
    if (!code)
        return '';
    const language = lang ? LANG_MAP[lang.toLowerCase()] || lang.toLowerCase() : 'text';
    if (language !== 'text' && !KNOWN_LANGUAGES.has(language)) {
        return code;
    }
    try {
        return highlight(code, {
            language,
            ignoreIllegals: true,
            theme: customTheme,
        });
    }
    catch {
        return code;
    }
}
