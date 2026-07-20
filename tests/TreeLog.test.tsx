import React from 'react';
import { expect, test } from 'vitest';
import { render } from 'ink-testing-library';
import { TreeLog } from '../src/components/TreeLog';

test('TreeLog renders tool call and nested result', () => {
  const { lastFrame } = render(
    <TreeLog toolName="Update" args="file.php" resultTitle="Updated 1 file" />
  );
  
  const frame = lastFrame();
  
  // Verify main log line
  expect(frame).toContain('● Update(file.php)');
  
  // Verify tree indentation (note the extra space from padding)
  expect(frame).toContain('└  Updated 1 file');
});
