import type React from 'react';

export interface RoundedBoxProps {
  title?: string;
  borderColor?: string;
  children: React.ReactNode;
  paddingX?: number;
  paddingY?: number;
  hasShadow?: boolean;
}
