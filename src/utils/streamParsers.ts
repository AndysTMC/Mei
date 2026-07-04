/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

export function findSseSeparator(text: string): number {
    const lf = text.indexOf('\n\n');
    const crlf = text.indexOf('\r\n\r\n');
    if (lf === -1) return crlf;
    if (crlf === -1) return lf;
    return Math.min(lf, crlf);
}

export function getSseSeparatorLength(text: string, separatorIndex: number): number {
    return text.startsWith('\r\n\r\n', separatorIndex) ? 4 : 2;
}

export function parseSseDataBlock(block: string): string[] {
    const dataLines = block
        .split(/\r?\n/)
        .filter(line => line.startsWith('data:'))
        .map(line => line.slice(5).trimStart());
    return dataLines.length > 0 ? [dataLines.join('\n')] : [];
}

export function extractJsonLines(buffer: string): { lines: string[]; rest: string } {
    const lines: string[] = [];
    let start = 0;
    let newlineIndex = buffer.indexOf('\n', start);

    while (newlineIndex !== -1) {
        const line = buffer.slice(start, newlineIndex).trim();
        if (line) lines.push(line);
        start = newlineIndex + 1;
        newlineIndex = buffer.indexOf('\n', start);
    }

    return {
        lines,
        rest: buffer.slice(start),
    };
}
