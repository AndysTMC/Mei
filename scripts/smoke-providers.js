import { existsSync, readFileSync } from 'node:fs';

loadEnvFile('.env');

const timeoutMs = numberEnv('MEI_LIVE_TIMEOUT_MS', 15000);
const runChat = process.env.MEI_LIVE_CHAT === '1';

const providers = [
    openAiProvider('OpenAI', 'OPENAI', 'https://api.openai.com/v1'),
    anthropicProvider(),
    geminiProvider(),
    openAiProvider('Groq', 'GROQ', 'https://api.groq.com/openai/v1'),
    openAiProvider('Mistral', 'MISTRAL', 'https://api.mistral.ai/v1'),
    openAiProvider('OpenRouter', 'OPENROUTER', 'https://openrouter.ai/api/v1'),
    githubProvider(),
    openCodeProvider('Go', 'OPENCODE_GO', 'https://opencode.ai/zen/go/v1'),
    openCodeProvider('Zen', 'OPENCODE_ZEN', 'https://opencode.ai/zen/v1'),
    optionalOpenAiProvider('llama.cpp', 'LLAMACPP', 'http://127.0.0.1:8080/v1'),
    optionalOpenAiProvider('LM Studio', 'LMSTUDIO', 'http://127.0.0.1:1234/v1'),
    ollamaProvider(),
    optionalOpenAiProvider('Custom', 'CUSTOM', ''),
].filter(Boolean);

let failures = 0;
let skipped = 0;
let passed = 0;

for (const provider of providers) {
    if (!provider.enabled()) {
        skipped++;
        console.log(`SKIP ${provider.name}: ${provider.skipReason}`);
        continue;
    }

    const models = await runCheck(`${provider.name} model list`, provider.listRequest(), provider.parseModels);
    if (models === null) continue;

    if (!runChat) continue;
    const model = provider.model || models[0];
    if (!model) {
        skipped++;
        console.log(`SKIP ${provider.name} chat: no model returned and no model configured`);
        continue;
    }
    await runCheck(`${provider.name} chat (${model})`, provider.chatRequest(model), provider.parseChat);
}

console.log(`Live provider summary: ${passed} passed, ${skipped} skipped, ${failures} failed.`);
if (!runChat) console.log('Chat generation was not run. Set MEI_LIVE_CHAT=1 to enable billable generation checks.');
if (failures > 0) process.exitCode = 1;

async function runCheck(name, request, parse) {
    try {
        const response = await fetch(request.url, {
            method: request.method ?? 'GET',
            headers: request.headers,
            body: request.body === undefined ? undefined : JSON.stringify(request.body),
            signal: AbortSignal.timeout(timeoutMs),
        });
        const text = await response.text();
        if (!response.ok) throw new Error(`HTTP ${response.status}${safeApiError(text)}`);

        let json;
        try {
            json = JSON.parse(text);
        } catch {
            throw new Error('response was not valid JSON');
        }
        const value = parse(json);
        if (!value || (Array.isArray(value) && value.length === 0)) throw new Error('response had no usable data');
        passed++;
        console.log(`PASS ${name}${Array.isArray(value) ? `: ${value.length} model(s)` : ''}`);
        return value;
    } catch (error) {
        failures++;
        console.error(`FAIL ${name}: ${error instanceof Error ? error.message : String(error)}`);
        return null;
    }
}

function openAiProvider(name, prefix, defaultBaseUrl) {
    const apiKey = firstEnv(`${prefix}_API_KEY`, `${prefix}_TOKEN`);
    const baseUrl = stripSlash(process.env[`${prefix}_BASE_URL`] || defaultBaseUrl);
    return {
        name,
        model: process.env[`${prefix}_MODEL`] || '',
        enabled: () => Boolean(apiKey),
        skipReason: `missing ${prefix}_API_KEY`,
        listRequest: () => ({ url: `${baseUrl}/models`, headers: bearer(apiKey) }),
        parseModels: parseOpenAiModels,
        chatRequest: model => jsonRequest(`${baseUrl}/chat/completions`, bearer(apiKey), {
            model,
            messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
            max_tokens: 16,
        }),
        parseChat: parseOpenAiChat,
    };
}

function optionalOpenAiProvider(name, prefix, defaultBaseUrl) {
    const configuredUrl = process.env[`${prefix}_BASE_URL`] || defaultBaseUrl;
    if (!process.env[`${prefix}_BASE_URL`] && (prefix === 'CUSTOM' || !process.env[`${prefix}_LIVE`])) return null;
    const provider = openAiProvider(name, prefix, configuredUrl);
    const apiKey = firstEnv(`${prefix}_API_KEY`, `${prefix}_TOKEN`);
    provider.enabled = () => Boolean(configuredUrl);
    provider.skipReason = `missing ${prefix}_BASE_URL`;
    provider.listRequest = () => ({ url: `${stripSlash(configuredUrl)}/models`, headers: bearer(apiKey) });
    provider.chatRequest = model => jsonRequest(`${stripSlash(configuredUrl)}/chat/completions`, bearer(apiKey), {
        model,
        messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
        max_tokens: 16,
    });
    return provider;
}

function anthropicProvider() {
    const apiKey = firstEnv('ANTHROPIC_API_KEY');
    const baseUrl = stripSlash(process.env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com/v1');
    const headers = () => ({ 'x-api-key': apiKey, 'anthropic-version': '2023-06-01' });
    return {
        name: 'Anthropic',
        model: process.env.ANTHROPIC_MODEL || '',
        enabled: () => Boolean(apiKey),
        skipReason: 'missing ANTHROPIC_API_KEY',
        listRequest: () => ({ url: `${baseUrl}/models?limit=1000`, headers: headers() }),
        parseModels: json => Array.isArray(json?.data) ? json.data.map(item => item?.id).filter(Boolean) : [],
        chatRequest: model => jsonRequest(`${baseUrl}/messages`, headers(), {
            model,
            max_tokens: 16,
            messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
        }),
        parseChat: json => Array.isArray(json?.content) && json.content.some(part => part?.type === 'text' && part.text),
    };
}

function geminiProvider() {
    const apiKey = firstEnv('GEMINI_API_KEY', 'GOOGLE_API_KEY');
    const baseUrl = stripSlash(process.env.GEMINI_BASE_URL || 'https://generativelanguage.googleapis.com/v1beta');
    const headers = () => ({ 'x-goog-api-key': apiKey });
    return {
        name: 'Gemini',
        model: process.env.GEMINI_MODEL || '',
        enabled: () => Boolean(apiKey),
        skipReason: 'missing GEMINI_API_KEY or GOOGLE_API_KEY',
        listRequest: () => ({ url: `${baseUrl}/models?pageSize=1000`, headers: headers() }),
        parseModels: json => Array.isArray(json?.models)
            ? json.models
                .filter(item => !Array.isArray(item?.supportedGenerationMethods) || item.supportedGenerationMethods.includes('generateContent'))
                .map(item => item?.name?.replace(/^models\//, ''))
                .filter(Boolean)
            : [],
        chatRequest: model => jsonRequest(`${baseUrl}/models/${model}:generateContent`, headers(), {
            contents: [{ role: 'user', parts: [{ text: 'Reply with exactly: OK' }] }],
        }),
        parseChat: json => Array.isArray(json?.candidates) && json.candidates.some(candidate =>
            candidate?.content?.parts?.some(part => typeof part?.text === 'string' && part.text.length > 0)),
    };
}

function githubProvider() {
    const apiKey = firstEnv('GITHUB_MODELS_TOKEN', 'GITHUB_TOKEN');
    const headers = () => ({
        ...bearer(apiKey),
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2026-03-10',
    });
    return {
        ...openAiProvider('GitHub Models', 'GITHUB_MODELS', 'https://models.github.ai/inference'),
        model: process.env.GITHUB_MODELS_MODEL || '',
        enabled: () => Boolean(apiKey),
        skipReason: 'missing GITHUB_MODELS_TOKEN or GITHUB_TOKEN',
        listRequest: () => ({ url: 'https://models.github.ai/catalog/models', headers: headers() }),
        parseModels: json => (Array.isArray(json) ? json : json?.models || json?.data || [])
            .map(item => item?.id || item?.name)
            .filter(Boolean),
        chatRequest: model => jsonRequest('https://models.github.ai/inference/chat/completions', headers(), {
            model,
            messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
            max_tokens: 16,
        }),
    };
}

function openCodeProvider(mode, prefix, baseUrl) {
    const apiKey = firstEnv(`${prefix}_API_KEY`, 'OPENCODE_API_KEY', 'OPENCODE_TOKEN');
    const headers = () => ({
        ...bearer(apiKey),
        'HTTP-Referer': 'https://github.com/AndysTMC/Mei',
        'X-Title': 'Mei',
    });
    return {
        ...openAiProvider(`OpenCode ${mode}`, prefix, baseUrl),
        enabled: () => Boolean(apiKey),
        skipReason: `missing ${prefix}_API_KEY or OPENCODE_API_KEY`,
        listRequest: () => ({ url: `${baseUrl}/models`, headers: headers() }),
        chatRequest: model => openCodeChatRequest(baseUrl, mode, model, headers()),
        parseChat: parseOpenCodeChat,
    };
}

function openCodeChatRequest(baseUrl, mode, configuredModel, headers) {
    const model = configuredModel.trim().split('/').at(-1);
    const apiMode = openCodeApiMode(model, mode);
    if (apiMode === 'responses') {
        return jsonRequest(`${baseUrl}/responses`, headers, {
            model,
            store: false,
            input: [{ role: 'user', content: 'Reply with exactly: OK' }],
            max_output_tokens: 16,
        });
    }
    if (apiMode === 'anthropic_messages') {
        return jsonRequest(`${baseUrl}/messages`, {
            ...headers,
            'anthropic-version': '2023-06-01',
        }, {
            model,
            messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
            max_tokens: 16,
        });
    }
    return jsonRequest(`${baseUrl}/chat/completions`, headers, {
        model,
        messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
        max_tokens: 16,
    });
}

function openCodeApiMode(model, mode) {
    const normalized = model.toLowerCase();
    if (/^(?:gpt-|grok-|muse-spark)/.test(normalized)) return 'responses';
    if (mode.toLowerCase() === 'zen' && /^(?:claude-|qwen)/.test(normalized)) return 'anthropic_messages';
    if (mode.toLowerCase() !== 'zen' && /^(?:minimax-|qwen)/.test(normalized)) return 'anthropic_messages';
    return 'chat_completions';
}

function parseOpenCodeChat(json) {
    if (parseOpenAiChat(json)) return true;
    if (Array.isArray(json?.content) && json.content.some(part => typeof part?.text === 'string' && part.text)) {
        return true;
    }
    if (typeof json?.output_text === 'string' && json.output_text) return true;
    return Array.isArray(json?.output) && json.output.some(item =>
        Array.isArray(item?.content) && item.content.some(part =>
            (typeof part?.text === 'string' && part.text.length > 0) ||
            (typeof part?.refusal === 'string' && part.refusal.length > 0)));
}

function ollamaProvider() {
    const baseUrl = stripSlash(process.env.OLLAMA_BASE_URL || 'http://127.0.0.1:11434');
    const apiKey = firstEnv('OLLAMA_API_KEY', 'OLLAMA_TOKEN');
    return {
        name: 'Ollama',
        model: process.env.OLLAMA_MODEL || '',
        enabled: () => process.env.OLLAMA_LIVE === '1' || Boolean(process.env.OLLAMA_BASE_URL),
        skipReason: 'set OLLAMA_LIVE=1 or OLLAMA_BASE_URL to test a running server',
        listRequest: () => ({ url: `${baseUrl}/api/tags`, headers: bearer(apiKey) }),
        parseModels: json => Array.isArray(json?.models) ? json.models.map(item => item?.name || item?.model).filter(Boolean) : [],
        chatRequest: model => jsonRequest(`${baseUrl}/api/chat`, bearer(apiKey), {
            model,
            messages: [{ role: 'user', content: 'Reply with exactly: OK' }],
            stream: false,
        }),
        parseChat: json => typeof json?.message?.content === 'string' && json.message.content.length > 0,
    };
}

function parseOpenAiModels(json) {
    return Array.isArray(json?.data) ? json.data.map(item => item?.id || item?.display_name).filter(Boolean) : [];
}

function parseOpenAiChat(json) {
    return typeof json?.choices?.[0]?.message?.content === 'string' && json.choices[0].message.content.length > 0;
}

function jsonRequest(url, headers, body) {
    return { url, method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body };
}

function bearer(key) {
    return key ? { Authorization: `Bearer ${key}` } : {};
}

function safeApiError(text) {
    try {
        const json = JSON.parse(text);
        const message = json?.error?.message || json?.error || json?.detail;
        return typeof message === 'string' ? `: ${message.slice(0, 300)}` : '';
    } catch {
        return '';
    }
}

function firstEnv(...names) {
    return names.map(name => process.env[name]).find(Boolean) || '';
}

function stripSlash(value) {
    return value.replace(/\/+$/, '');
}

function numberEnv(name, fallback) {
    const value = Number.parseInt(process.env[name] || '', 10);
    return Number.isFinite(value) && value > 0 ? value : fallback;
}

function loadEnvFile(path) {
    if (!existsSync(path)) return;
    for (const rawLine of readFileSync(path, 'utf8').split(/\r?\n/)) {
        const line = rawLine.trim();
        if (!line || line.startsWith('#')) continue;
        const match = line.match(/^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$/);
        if (!match || process.env[match[1]] !== undefined) continue;
        let value = match[2].trim();
        if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
            value = value.slice(1, -1);
        } else {
            value = value.replace(/\s+#.*$/, '').trim();
        }
        process.env[match[1]] = value.replace(/\\n/g, '\n');
    }
}
