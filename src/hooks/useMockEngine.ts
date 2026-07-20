import { useState } from 'react';
import { DiffLine } from '../components/WordDiffViewer';

export type LogItem =
  | { type: 'user'; text: string }
  | { type: 'text'; text: string }
  | { type: 'tool'; name: string; args: string; resultTitle: string; diff?: DiffLine[] };

export function useMockEngine() {
  const [history, setHistory] = useState<LogItem[]>([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [loadingText, setLoadingText] = useState('');

  const executeCommand = async (input: string) => {
    setIsExecuting(true);
    setHistory(prev => [...prev, { type: 'user', text: input }]);
    
    if (input.trim() === '/clear') {
       setHistory([]);
       setIsExecuting(false);
       return;
    }
    
    if (input.trim().startsWith('/add-dir')) {
       setLoadingText('Adding directory...');
       await new Promise(r => setTimeout(r, 1000));
       setHistory(prev => [...prev, { type: 'text', text: 'Directory added to workspace context.' }]);
       setIsExecuting(false);
       return;
    }

    if (input.trim() === '/plugin') {
       setLoadingText('Loading plugins...');
       await new Promise(r => setTimeout(r, 1000));
       setHistory(prev => [...prev, { type: 'text', text: 'Plugin mock execution completed successfully.' }]);
       setIsExecuting(false);
       return;
    }

    // Default generic flow
    setLoadingText('Thinking...');
    await new Promise(r => setTimeout(r, 1000));
    setHistory(prev => [...prev, { type: 'text', text: 'I am analyzing your request and applying the fix.' }]);
    
    setLoadingText('Using tool...');
    await new Promise(r => setTimeout(r, 1500));
    
    const mockDiff: DiffLine[] = [
      { type: 'context', number: 1, segments: [{ text: '  function example() {' }] },
      { type: 'remove', number: 2, segments: [{ text: '    return ', isHighlightedWord: false }, { text: 'false', isHighlightedWord: true }, { text: ';' }] },
      { type: 'add', number: 2, segments: [{ text: '    return ', isHighlightedWord: false }, { text: 'true', isHighlightedWord: true }, { text: ';' }] },
      { type: 'context', number: 3, segments: [{ text: '  }' }] },
    ];
    
    setHistory(prev => [...prev, { 
       type: 'tool', 
       name: 'Update', 
       args: 'src/example.ts', 
       resultTitle: 'Updated file correctly.', 
       diff: mockDiff 
    }]);
    
    setIsExecuting(false);
  };

  return { history, isExecuting, loadingText, executeCommand };
}
