import { highlight } from 'cli-highlight';

const LANGUAGE_MAP: Record<string, string> = {
  py: 'python',
  python: 'python',
  ts: 'typescript',
  tsx: 'typescript',
  js: 'javascript',
  jsx: 'javascript',
  json: 'json',
  sh: 'bash',
  bash: 'bash',
  dockerfile: 'dockerfile',
  docker: 'dockerfile',
  html: 'html',
  css: 'css',
  sql: 'sql',
  yaml: 'yaml',
  yml: 'yaml',
};

export function highlightCode(code: string, langOrExt?: string): string {
  if (!code) return '';

  const normalizedLang = langOrExt
    ? LANGUAGE_MAP[langOrExt.toLowerCase()] || langOrExt.toLowerCase()
    : 'typescript';

  try {
    return highlight(code, {
      language: normalizedLang,
      ignoreIllegals: true,
    });
  } catch (_err) {
    return code;
  }
}
