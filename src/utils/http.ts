import Soup from 'gi://Soup?version=3.0';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

/**
 * Sends a POST request with a JSON body and returns the parsed JSON response.
 */
export function postJson(
    session: Soup.Session,
    url: string,
    body: object,
    headers: Record<string, string>,
    cancellable: Gio.Cancellable
): Promise<any> {
    return new Promise((resolve, reject) => {
        const msg = Soup.Message.new('POST', url);
        if (!msg) {
            reject(new Error(`Invalid URL: ${url}`));
            return;
        }

        const jsonStr = JSON.stringify(body);
        const bytes = new GLib.Bytes(new TextEncoder().encode(jsonStr));
        msg.set_request_body_from_bytes('application/json', bytes);

        for (const [key, value] of Object.entries(headers)) {
            msg.get_request_headers().append(key, value);
        }

        session.send_and_read_async(
            msg,
            GLib.PRIORITY_DEFAULT,
            cancellable,
            ((_session: any, result: any) => {
                try {
                    const respBytes = session.send_and_read_finish(result);
                    const text = new TextDecoder().decode(respBytes.get_data()!);
                    const json = JSON.parse(text);
                    resolve(json);
                } catch (e) {
                    reject(e);
                }
            }) as any
        );
    });
}
