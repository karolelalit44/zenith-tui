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
       console.clear();
       setHistory([]);
       setIsExecuting(false);
       return;
    }
    
    // Zenith Simulation Engine: Stochastic Latency & Branching
    const delay = (ms: number, variance = 0.3) => {
      const varied = ms * (1 - variance + Math.random() * variance * 2);
      return new Promise(r => setTimeout(r, varied));
    };

    if (input.trim().startsWith('/add-dir')) {
       setLoadingText('Scanning file system...');
       await delay(800);
       setHistory(prev => [...prev, { type: 'text', text: 'Directory context synchronized successfully.' }]);
       setIsExecuting(false);
       return;
    }

    if (input.trim() === '/plugin') {
       setLoadingText('Fetching registry...');
       await delay(1200);
       setHistory(prev => [...prev, { type: 'text', text: 'Plugin integration verified.' }]);
       setIsExecuting(false);
       return;
    }

    if (input.trim() === '/settings') {
      setIsExecuting(false);
      return;
    }

    if (input.trim() === '/build') {
      setLoadingText('Initializing build system...');
      await delay(800);
      setHistory(prev => [...prev, { type: 'text', text: '  ✔ Resolving dependencies (142ms)' }]);
      
      setLoadingText('Compiling TypeScript...');
      await delay(1200);
      setHistory(prev => [...prev, { type: 'text', text: '  ✔ Compiling TypeScript (1.1s)' }]);
      
      setLoadingText('Minifying assets...');
      await delay(900);
      setHistory(prev => [...prev, { type: 'text', text: '  ✔ Minifying assets (405ms)' }]);
      
      setHistory(prev => [...prev, { type: 'text', text: '✨ Build successful in 1.6s' }]);
      setIsExecuting(false);
      return;
    }

    // Default LLM Flow Simulation
    setLoadingText('Thinking...');
    await delay(600, 0.5);
    setHistory(prev => [...prev, { type: 'text', text: 'Analyzing architectural constraints and determining tool trajectory.' }]);
    
    setLoadingText('Using tool...');
    await delay(1400, 0.4);
    
    const mockDiff: DiffLine[] = [
      { type: 'context', number: 1, segments: [{ text: '  function ZenithEngine() {' }] },
      { type: 'remove', number: 2, segments: [{ text: '    const state = ', isHighlightedWord: false }, { text: '"mock"', isHighlightedWord: true }, { text: ';' }] },
      { type: 'add', number: 2, segments: [{ text: '    const state = ', isHighlightedWord: false }, { text: '"simulated"', isHighlightedWord: true }, { text: ';' }] },
      { type: 'context', number: 3, segments: [{ text: '  }' }] },
    ];
    
    setHistory(prev => [...prev, { 
       type: 'tool', 
       name: 'Update', 
       args: 'src/engine.ts', 
       resultTitle: 'File patched automatically.', 
       diff: mockDiff 
    }]);
    
    setIsExecuting(false);
  };

  return { history, isExecuting, loadingText, executeCommand };
}
