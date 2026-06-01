# ADR-0016 - Cloud provisioning como DECISAO-DE-NAO-FAZER (sem Terraform/IaC real)

- Status: Accepted
- Data: 2026-05-31
- Item do roadmap: R-19 (`docs/11-roadmap-melhorias-agente.md`).
- Relaciona-se com: ADR-0006 (execucao via Docker Compose com sandbox unica — a topologia que
  **substitui** o deploy cloud no escopo do desafio), R-18 (runbook operacional, `docs/operations/runbook.md`,
  onde o caminho de promocao a cloud fica esbocado em prosa, sem IaC).

## Context

A vaga Lead cita "cloud provisioning" e "deploy automatizado" entre as responsabilidades. A
tentacao e adicionar um esqueleto de Terraform/IaC (VPS, `systemd`, modulos de rede) para "marcar
o item". O custo/risco e desproporcional ao **teste tecnico**: provisionar nuvem real exige
credenciais, segredos, custo recorrente e um alvo de deploy que **nao existe** para um desafio; e
um esqueleto IaC nao-aplicavel (que ninguem aplica nem testa) passaria sinal de **incompletude e
gold plating** — o oposto do que `docs/09` pede ("nao gold-plate; escolher nao-fazer e justificar").

O sinal de senioridade **Lead** que a vaga realmente cobra aqui nao e "ter Terraform no repo", e
**decidir conscientemente o que nao construir e justificar o trade-off** (`docs/11 §1.1`, §6.2). O
teto deliberado de cobertura Lead em ~91% (e nao 100%) assume exatamente esta lacuna como
**decisao**, nao como esquecimento.

## Decision

**Nao** implementar cloud provisioning real nem esqueleto de IaC (Terraform/`systemd`/modulos de
nuvem) no escopo desta entrega. Em vez disso:

1. O **alvo de execucao oficial e reproduzivel** e o **Docker Compose** (ADR-0006): um comando
   sobe todo o stack (database, seed, backend, frontend, mcp-server, gateway) e a sandbox isolada
   do agente (Omni/Genie). Isso ja entrega "setup reproduzivel" e "deploy local automatizado", que
   sao o que o desafio avalia.
2. O **CI/CD publico** (GitHub Actions, R-01) cobre o eixo de automacao de qualidade (lint, types,
   testes, eval gate >= 85 bloqueante) — a parte de "pipeline para agentes" que **e** pertinente e
   barata num teste tecnico.
3. O **caminho de promocao a cloud** (o que mudaria para producao real: registry de imagens,
   secrets manager, alvo gerenciado de containers, observabilidade exportada, backup de Postgres)
   fica **descrito em prosa** numa secao do runbook operacional (R-18) — como **roteiro de
   evolucao**, nao como codigo morto.

A decisao e **revisitavel**: havendo um alvo real de deploy (e segredos/custo associados), o
provisionamento entra como ADR proprio que **supersede** esta secao do escopo; ate la, a ausencia
de IaC e **intencional e registrada**.

## Consequences

Positivas:
- Mantem o foco no que o desafio mede (agente + tools + guardrails + qualidade reproduzivel) sem
  custo/risco/segredos de nuvem real.
- Evita **codigo morto** (IaC que ninguem aplica) e o sinal de incompletude que ele carregaria.
- Materializa o sinal Lead correto: **escolher nao-fazer e justificar**, com o trade-off explicito
  e o caminho de promocao documentado (runbook).

Negativas / trade-offs:
- A cobertura nominal Lead fica em **~91%** por opcao — os ~9 pontos restantes sao majoritariamente
  esta dimensao (cloud operacional real) + a dimensao humana (liderar squad, ponto focal
  enterprise), nao demonstravel por artefato.
- Quem espera ver Terraform no repo nao o encontra; mitigado por **esta** ADR + a secao de
  promocao no runbook, que tornam a ausencia uma **decisao legivel**, nao uma falha.

## Alternatives

- **Esqueleto de Terraform/IaC nao-aplicavel** so para "marcar o item": rejeitado — codigo morto,
  sinal de incompletude e gold plating, sem nada rodando de verdade.
- **Provisionar nuvem real (VPS/managed containers) para a entrega**: rejeitado — custo recorrente,
  segredos reais, alvo inexistente para um teste tecnico; risco >> sinal.
- **Omitir o tema por completo** (nem ADR nem runbook): rejeitado — deixaria a lacuna parecer
  esquecimento, justamente o oposto do sinal Lead; a decisao **precisa** estar registrada.
