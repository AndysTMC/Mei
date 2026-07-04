const checks = [
    {
        name: 'Gemini models',
        env: ['GEMINI_API_KEY', 'GOOGLE_API_KEY'],
        url: 'https://generativelanguage.googleapis.com/v1beta/models',
        headers: key => ({ 'x-goog-api-key': key }),
        parse: json => Array.isArray(json.models) ? json.models.length : 0,
    },
    {
        name: 'GitHub Models catalog',
        env: ['GITHUB_MODELS_TOKEN', 'GITHUB_TOKEN'],
        url: 'https://models.github.ai/catalog/models',
        headers: key => ({
            Authorization: `Bearer ${key}`,
            Accept: 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2026-03-10',
        }),
        parse: json => Array.isArray(json) ? json.length : Array.isArray(json.models) ? json.models.length : 0,
    },
    {
        name: 'OpenCode Go models',
        env: ['OPENCODE_API_KEY', 'OPENCODE_TOKEN'],
        url: 'https://opencode.ai/zen/go/v1/models',
        headers: key => ({ Authorization: `Bearer ${key}` }),
        parse: json => Array.isArray(json.data) ? json.data.length : 0,
    },
    {
        name: 'OpenCode Zen models',
        env: ['OPENCODE_API_KEY', 'OPENCODE_TOKEN'],
        url: 'https://opencode.ai/zen/v1/models',
        headers: key => ({ Authorization: `Bearer ${key}` }),
        parse: json => Array.isArray(json.data) ? json.data.length : 0,
    },
];

let failures = 0;
let skipped = 0;

for (const check of checks) {
    const envName = check.env.find(name => process.env[name]);
    if (!envName) {
        skipped++;
        console.log(`SKIP ${check.name}: missing one of ${check.env.join(', ')}`);
        continue;
    }

    try {
        const response = await fetch(check.url, {
            headers: check.headers(process.env[envName]),
        });
        const text = await response.text();
        if (!response.ok) {
            failures++;
            console.error(`FAIL ${check.name}: HTTP ${response.status}`);
            continue;
        }

        let count = 0;
        try {
            count = check.parse(JSON.parse(text));
        } catch {
            failures++;
            console.error(`FAIL ${check.name}: response was not valid JSON`);
            continue;
        }
        console.log(`PASS ${check.name}: ${count} model(s) returned`);
    } catch (error) {
        failures++;
        console.error(`FAIL ${check.name}: ${error instanceof Error ? error.message : String(error)}`);
    }
}

if (failures > 0) {
    process.exit(1);
}

if (skipped === checks.length) {
    console.log('No provider credentials were present; live provider smoke checks were skipped.');
}
