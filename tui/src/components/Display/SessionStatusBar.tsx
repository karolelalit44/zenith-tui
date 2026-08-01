import React from 'react';
import type { TokenUsageStats } from '../../services/api/TokenUsageService';
import type { ScenarioMode } from '../../types';

interface SessionStatusBarProps {
  mode: ScenarioMode;
  totalTokens: number;
  maxTokens?: number;
  isRunning?: boolean;
  isOverlayOpen?: boolean;
  hasEvents?: boolean;
  modelName?: string;
  workspaceName?: string;
  gitBranch?: string;
  tokenUsageStats?: TokenUsageStats | null;
}

export const SessionStatusBar: React.FC<SessionStatusBarProps> = () => null;
