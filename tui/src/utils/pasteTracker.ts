const pasteRegistry = new Map<string, string>();
let pasteCounter = 0;

export function registerLargePaste(rawText: string): string {
  const lines = rawText.replace(/\r\n/g, '\n').split('\n');
  const lineCount = lines.length;

  pasteCounter++;
  const label = lineCount > 1 ? `+${lineCount} lines` : `${rawText.length} chars`;
  const marker = `[Pasted ${label} #${pasteCounter}]`;

  pasteRegistry.set(marker, rawText);
  return marker;
}

export function insertOrMergePaste(
  currentValue: string,
  cursorPos: number,
  cleanPaste: string,
): { nextValue: string; nextCursor: number } {
  const textBefore = currentValue.slice(0, cursorPos);
  const textAfter = currentValue.slice(cursorPos);

  const markerMatch = textBefore.match(/\[Pasted (?:(?:\+\d+ lines)|\d+ chars) #\d+\]$/);

  if (markerMatch) {
    const prevMarker = markerMatch[0];
    const prevRaw = pasteRegistry.get(prevMarker) || '';
    const combinedRaw = prevRaw + cleanPaste;
    const lines = combinedRaw.replace(/\r\n/g, '\n').split('\n');
    const lineCount = lines.length;

    pasteCounter++;
    const label = lineCount > 1 ? `+${lineCount} lines` : `${combinedRaw.length} chars`;
    const newMarker = `[Pasted ${label} #${pasteCounter}]`;
    pasteRegistry.set(newMarker, combinedRaw);

    const baseBefore = textBefore.slice(0, textBefore.length - prevMarker.length);
    const nextValue = baseBefore + newMarker + textAfter;
    const nextCursor = baseBefore.length + newMarker.length;

    return { nextValue, nextCursor };
  }

  if (isLargePaste(cleanPaste)) {
    const newMarker = registerLargePaste(cleanPaste);
    const nextValue = textBefore + newMarker + textAfter;
    const nextCursor = textBefore.length + newMarker.length;
    return { nextValue, nextCursor };
  }

  const nextValue = textBefore + cleanPaste + textAfter;
  const nextCursor = textBefore.length + cleanPaste.length;
  return { nextValue, nextCursor };
}

export function expandPastedMarkers(text: string): string {
  let expanded = text;
  for (const [marker, rawText] of pasteRegistry.entries()) {
    if (expanded.includes(marker)) {
      expanded = expanded.replaceAll(marker, rawText);
    }
  }
  return expanded;
}

export function isLargePaste(text: string): boolean {
  return text.includes('\n') || text.length > 100;
}
