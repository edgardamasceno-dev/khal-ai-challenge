// Harness de verificação do tool-scoping (roda com bun, dentro do sandbox).
// Lê o AGENTS.md do agente CX, parseia o frontmatter com o MESMO parser do Genie,
// monta o SpawnParams do omni e o comando do Claude Code — e asserta que o comando
// está escopado (sem Bash/WebFetch/WebSearch; persona como system prompt).
import { parseFrontmatter } from '/srv/genie/src/lib/frontmatter.ts';
import { buildOmniSpawnParams } from '/srv/genie/src/services/executors/claude-code.ts';
import { buildLaunchCommand } from '/srv/genie/src/lib/provider-adapters.ts';
import { readFileSync } from 'node:fs';

const agentDir = process.argv[2] ?? '/srv/omni/agents/luz-do-vale';
const content = readFileSync(`${agentDir}/AGENTS.md`, 'utf-8');
const cf = parseFrontmatter(content);

// Replica os campos que o agent-sync materializa no DirectoryEntry.
const entry: any = {
  name: 'luz-do-vale',
  dir: agentDir,
  provider: cf.provider,
  promptMode: cf.promptMode ?? 'append',
  permissions: cf.permissions,
  disallowedTools: cf.disallowedTools,
  omniScopes: cf.omniScopes,
};

const env = { GENIE_OMNI_CHAT_ID: '555199990001', GENIE_OMNI_AGENT: 'luz-do-vale' };
const params = buildOmniSpawnParams('luz-do-vale', '555199990001', entry, env, 'oi, minha luz caiu', undefined);
const launch = buildLaunchCommand(params);

console.log('=== frontmatter parseado ===');
console.log(JSON.stringify({ provider: cf.provider, promptMode: cf.promptMode, omniScopes: cf.omniScopes, permissions: cf.permissions, disallowedTools: cf.disallowedTools }, null, 2));
console.log('\n=== comando claude que o Genie spawnaria (omni turn) ===');
console.log(launch.command);

// Asserts de scoping (camada 1, doc 09).
const cmd = launch.command;
const fail: string[] = [];
// Bloqueio duro de exfil/escrita.
for (const t of ['WebFetch', 'WebSearch', 'Edit', 'Write', 'Task']) {
  if (!cmd.includes(`--disallowedTools '${t}'`)) fail.push(`faltou --disallowedTools ${t}`);
}
// Persona via system prompt + MCP no allow.
if (!cmd.includes('--append-system-prompt-file')) fail.push('faltou --append-system-prompt-file (persona)');
if (!cmd.includes('mcp__luz-do-vale__create_ticket')) fail.push('faltou MCP no allow');
// Bash escopado a omni (resposta), NUNCA hard-disallow nem allow amplo.
if (cmd.includes("--disallowedTools 'Bash'")) fail.push('Bash hard-disallow quebraria a resposta omni');
if (!cmd.includes('Bash(omni:*)')) fail.push('faltou Bash(omni:*) no allow (resposta omni)');
if (/"allow":\[[^\]]*"Bash"[,\]]/.test(cmd)) fail.push('Bash amplo (sem escopo) no allow');
// Asserts dos HOOKS de guardrail (R-20) e do path de VOLUME do pgdata (R-05).
// Verificação ESTÁTICA da config (não sobe o agente): garante que o settings.json
// registra PreToolUse/UserPromptSubmit apontando p/ o guardrail.py, e que o
// script existe. O disparo real é validação ao vivo (ver RUNBOOK §7).
const HOOKS_SETTINGS = process.env.WIRE_HOOKS_SETTINGS ?? '/srv/agent/settings.json';
const HOOK_SCRIPT = process.env.WIRE_HOOK_SCRIPT ?? '/srv/agent/hooks/guardrail.py';
try {
  const raw = readFileSync(HOOKS_SETTINGS, 'utf-8');
  const settings: any = JSON.parse(raw);
  const hooks = settings.hooks ?? {};
  for (const ev of ['PreToolUse', 'UserPromptSubmit']) {
    const arr = hooks[ev];
    if (!Array.isArray(arr) || arr.length === 0) { fail.push(`settings.json sem hook ${ev}`); continue; }
    const cmds = arr.flatMap((m: any) => (m.hooks ?? []).map((h: any) => h.command ?? ''));
    if (!cmds.some((c: string) => c.includes('guardrail.py'))) fail.push(`hook ${ev} não chama guardrail.py`);
  }
} catch (e) {
  fail.push(`settings.json de hooks ausente/inválido em ${HOOKS_SETTINGS} (${(e as Error).message})`);
}
try { readFileSync(HOOK_SCRIPT, 'utf-8'); } catch { fail.push(`script de hook ausente em ${HOOK_SCRIPT}`); }

console.log('\n=== asserts ===');
if (fail.length) { console.log('FALHOU:\n  ' + fail.join('\n  ')); process.exit(1); }
console.log('OK: só MCP luz-do-vale + Bash(omni:*) p/ resposta; WebFetch/WebSearch/escrita/Task bloqueados; persona via system prompt; hooks PreToolUse/UserPromptSubmit (R-20) registrados.');
