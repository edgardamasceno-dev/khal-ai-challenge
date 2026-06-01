# Architecture Decision Records

Decisoes arquiteturais relevantes desta entrega. Cada ADR e imutavel; mudancas viram um novo ADR que supersede o anterior.

| ADR | Titulo | Status |
| --- | --- | --- |
| [0001](./ADR-0001-stack-python-pydantic.md) | Stack Python/Pydantic na camada de ferramentas | Accepted |
| [0002](./ADR-0002-ui-console-operador.md) | UI como console fino de operador | Accepted |
| [0003](./ADR-0003-midia-via-tool-action.md) | Envio de midia (PDF) como acao de ferramenta | Accepted |
| [0004](./ADR-0004-retrieval-lexico-strategy.md) | Retrieval lexico com Strategy plugavel | Accepted |
| [0005](./ADR-0005-eventos-deterministicos-memoria.md) | Eventos deterministicos sem LLM alimentando memoria | Accepted |
| [0006](./ADR-0006-docker-compose-sandbox.md) | Execucao via Docker Compose com sandbox unica | Accepted (credencial: ver 0007) |
| [0007](./ADR-0007-agente-claude-code-auth.md) | Runtime e autenticacao do agente: Claude Code (sem key dedicada) | Accepted |
| [0008](./ADR-0008-seeder-programatico-python.md) | Seeder programatico em Python (personas dinamicas) | Accepted |
| [0009](./ADR-0009-object-storage-faturas.md) | Object storage (MinIO) + render WeasyPrint para faturas | Accepted |
| [0010](./ADR-0010-media-egress-optin.md) | Rota direta de midia opt-in (anexo no WhatsApp vs egress isolado) | Accepted |
| [0011](./ADR-0011-personas-canonicas-deterministicas.md) | Personas canonicas com cenario fixo por nome (overlay deterministico) | Accepted |
| [0012](./ADR-0012-auditoria-observabilidade-tool-call.md) | Auditoria e observabilidade por tool-call MCP (best-effort, PII mascarada) | Accepted |
| [0013](./ADR-0013-fronteira-memoria-transcricao-eventos-sessao.md) | Fronteira de memoria do agente: transcricao (Omni) vs eventos de sistema (`conversation_memory`) vs sessao (Genie) — duas tools read-only | Accepted |

Formato: Context, Decision, Consequences, Alternatives.
