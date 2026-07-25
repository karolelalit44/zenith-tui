import { highlight } from 'cli-highlight';

const LANG_MAP: Record<string, string> = {
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

export function highlightCode(code: string, lang?: string): string {
  if (!code) return '';
  const language = lang ? LANG_MAP[lang.toLowerCase()] || lang.toLowerCase() : 'text';

  try {
    return highlight(code, {
      language,
      ignoreIllegals: true,
    });
  } catch (_err) {
    return code;
  }
}
