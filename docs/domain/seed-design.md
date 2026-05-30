# Design do seed

Objetivo: massa ficticia mas realista, **determinística** e re-executavel, que sustente todas as jornadas (`personas-journeys.md`) e os cenarios de eval.

## Principios

- Determinismo: `SEED_RANDOM_SEED` (default 42) fixa o RNG. Mesma entrada, mesmo banco.
- Re-executavel (idempotente): rodar o seed de novo nao duplica; faz upsert por chave natural (CPF, numero_uc, protocolo).
- Sem PII real: CPFs gerados com digito verificador valido porem ficticios; telefones vem do `.env`.
- Horizonte: `SEED_HISTORY_MONTHS` (default 24).

## Telefones e personas

O seed le do `.env`:

```text
DEMO_PHONE_PRIMARY  -> ana.souza
DEMO_PHONE_EVAL_1   -> carlos.lima
DEMO_PHONE_EVAL_2   -> joana.pereira
DEMO_DEFAULT_PERSONA -> ana.souza
```

Se uma variavel estiver vazia, a persona recebe um telefone placeholder no formato E.164 (ex.: 555199990001) marcado como nao-demonstravel, e o seed segue. Voce pluga os numeros reais quando souber, sem mexer no codigo.

## CPF ficticio valido

Geramos 9 digitos base a partir do RNG e calculamos os 2 digitos verificadores pelo algoritmo oficial (modulo 11). Resultado: passa em validacao de formato/digito, mas e ficticio e rotulado como teste. Nunca usar CPF de pessoa real.

## Conteudo gerado por persona

- **Titular** + contatos + `persona_key`.
- **UC(s)**: Ana 1, Carlos 2, Joana 1. Bairro de Ana = "Jardim das Flores".
- **Leituras + Faturas**: uma por mes de referencia (24 meses), com:
  - **sazonalidade**: consumo maior no verao (dez-mar) por ar-condicionado;
  - **bandeira** correlacionada (vermelha em meses secos/quentes);
  - **status**: meses antigos `paga`, mes atual de Ana `em_aberto`, um mes `vencida`;
  - `linha_digitavel` e `pix_copia_cola` ficticios.
- **Pagamentos**: um por fatura paga, com `idempotency_key`.
- **Interrupcoes**: 1 **ativa** no bairro de Ana (nao_programada, com previsao de retorno) + 1-2 historicas encerradas.
- **Chamados**: 1-2 resolvidos no historico + 1 aberto (para J4); SLA por tipo.
- **Religacao**: Joana com fatura que gerou corte e posterior religacao.

## Volume aproximado

~3 titulares, ~4 UCs, ~96 faturas (4 UCs x 24m), ~80 pagamentos, ~3 interrupcoes, ~5 chamados. Suficiente para demo e evals sem inflar o banco.

## Execucao

```bash
make db-up
make seed     # python -m scripts.seed (le .env)
```

Saida esperada: resumo por tabela (linhas inseridas/atualizadas) e os telefones efetivamente mapeados (mascarados em log).

## Relacao com evals

Os evals usam telefones controlados: um conhecido (persona do seed) e um deliberadamente **fora do seed** para o caso "cliente desconhecido". O fallback de persona default e comportamento de **demo**, nao de eval (`UNKNOWN_PHONE_BEHAVIOR`).
