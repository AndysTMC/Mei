/**
 * SPDX-License-Identifier: GPL-3.0-only
 */

export const MAX_HTTP_RESPONSE_BYTES = 8 * 1024 * 1024;

export class ResponseSizeGuard {
    private _receivedBytes = 0;

    constructor(private readonly _limitBytes = MAX_HTTP_RESPONSE_BYTES) {}

    get receivedBytes(): number {
        return this._receivedBytes;
    }

    add(byteLength: number): void {
        if (!Number.isFinite(byteLength) || byteLength < 0) {
            throw new Error('Response byte count must be a non-negative finite number');
        }

        this._receivedBytes += byteLength;
        if (this._receivedBytes > this._limitBytes) {
            const limit = this._limitBytes % (1024 * 1024) === 0
                ? `${this._limitBytes / (1024 * 1024)} MiB`
                : `${this._limitBytes} byte`;
            throw new Error(`Response exceeded ${limit} safety limit`);
        }
    }
}
