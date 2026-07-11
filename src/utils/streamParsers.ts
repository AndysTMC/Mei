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

export function getStreamErrorMessage(data: string): string | null {
    try {
        const parsed = JSON.parse(data) as unknown;
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return null;

        const root = parsed as Record<string, unknown>;
        if (typeof root.error === 'string') return root.error;
        if (typeof root.error !== 'object' || root.error === null || Array.isArray(root.error)) return null;

        const error = root.error as Record<string, unknown>;
        if (typeof error.message === 'string' && error.message.trim()) return error.message;
        if (typeof error.type === 'string' && error.type.trim()) return error.type;
    } catch {
        // Non-JSON event data is provider-specific and is handled by the caller.
    }
    return null;
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

export class Utf8StreamDecoder {
    private _pending = new Uint8Array(0);
    private _decoder = new TextDecoder();

    decode(chunk?: Uint8Array): string {
        if (!chunk) {
            const tail = this._pending;
            this._pending = new Uint8Array(0);
            return tail.length > 0 ? this._decoder.decode(tail) : '';
        }

        const bytes = concatBytes(this._pending, chunk);
        const completeLength = getCompleteUtf8PrefixLength(bytes);
        this._pending = bytes.slice(completeLength);
        return completeLength > 0 ? this._decoder.decode(bytes.slice(0, completeLength)) : '';
    }
}

function concatBytes(left: Uint8Array, right: Uint8Array): Uint8Array {
    if (left.length === 0) return right;
    const bytes = new Uint8Array(left.length + right.length);
    bytes.set(left);
    bytes.set(right, left.length);
    return bytes;
}

function getCompleteUtf8PrefixLength(bytes: Uint8Array): number {
    if (bytes.length === 0) return 0;

    let leadIndex = bytes.length - 1;
    while (leadIndex >= 0 && isContinuationByte(bytes[leadIndex])) leadIndex--;
    if (leadIndex < 0) return bytes.length;

    const expectedLength = getUtf8SequenceLength(bytes[leadIndex]);
    const availableLength = bytes.length - leadIndex;
    return expectedLength > availableLength ? leadIndex : bytes.length;
}

function isContinuationByte(byte: number): boolean {
    return (byte & 0xc0) === 0x80;
}

function getUtf8SequenceLength(leadByte: number): number {
    if ((leadByte & 0x80) === 0) return 1;
    if ((leadByte & 0xe0) === 0xc0) return 2;
    if ((leadByte & 0xf0) === 0xe0) return 3;
    if ((leadByte & 0xf8) === 0xf0) return 4;
    return 1;
}
