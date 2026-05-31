// Cliente tipado da API legada (Luz do Vale), consumida via gateway em /api.

const BASE = "/api"

export interface Customer {
  id: string
  nome: string
  cpf_mascarado: string
  telefone_mascarado: string
  email: string | null
  persona_key: string | null
}

export interface Unit {
  id: string
  numero_uc: string
  logradouro: string | null
  bairro: string
  cidade: string
  uf: string
  classe: string
  subgrupo: string | null
  status: string
}

export interface Contract {
  id: string
  modalidade: string
  data_inicio: string
  status: string
  unidade: Unit
}

export interface Invoice {
  id: string
  uc_id: string
  mes_referencia: string
  consumo_kwh: number
  valor_centavos: number
  valor_formatado: string
  bandeira: string
  vencimento: string
  status: string
  linha_digitavel: string | null
  pix_copia_cola: string | null
}

export interface Outage {
  id: string
  bairro: string
  cidade: string
  uf: string
  tipo: string
  causa: string | null
  inicio: string
  previsao_retorno: string | null
  status: string
}

export interface OutageResult {
  encontrada: boolean
  interrupcao: Outage | null
}

export interface Ticket {
  id: string
  protocolo: string
  titular_id: string
  uc_id: string | null
  tipo: string
  descricao: string | null
  status: string
  sla_horas: number
  canal: string
  aberto_em: string
  atualizado_em: string
}

export interface CreateTicketResponse {
  criado_agora: boolean
  ticket: Ticket
}

export interface Handoff {
  id: string
  chamado_id: string | null
  motivo: string | null
  status: string
  operador: string | null
  criado_em: string
}

export interface Health {
  status: string
  db: string
}

export class ApiError extends Error {
  readonly code: string
  readonly httpStatus: number

  constructor(code: string, message: string, httpStatus: number) {
    super(message)
    this.code = code
    this.httpStatus = httpStatus
  }
}

export interface ProactivePagamento {
  fatura_id: string
  numero_uc: string
  mes_referencia: string
  valor: string
  status: string
}

export interface ProactiveOutage {
  bairro: string
  previsao: string | null
  status: string
}

export interface ProactiveCandidates {
  encontrado: boolean
  motivo?: string
  titular?: string
  telefone?: string
  pagamentos?: ProactivePagamento[]
  outages?: ProactiveOutage[]
}

export interface ProactiveEventResult {
  publicado: boolean
  subject: string
  preview: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  })
  const text = await res.text()
  const body = text ? JSON.parse(text) : null
  if (!res.ok) {
    const code = body?.error?.code ?? "Error"
    const message = body?.error?.message ?? `HTTP ${res.status}`
    throw new ApiError(code, message, res.status)
  }
  return body as T
}

export const api = {
  health: () => request<Health>("/health"),

  findCustomerByPhone: (phone: string) =>
    request<Customer>(`/customers?phone=${encodeURIComponent(phone)}`),

  listContracts: (customerId: string) =>
    request<Contract[]>(`/customers/${customerId}/contracts`),

  listInvoices: (ucId: string) =>
    request<Invoice[]>(`/units/${ucId}/invoices?limit=24`),

  getOutage: (bairro: string) =>
    request<OutageResult>(`/outages?bairro=${encodeURIComponent(bairro)}`),

  listTickets: (customerId: string) =>
    request<Ticket[]>(`/customers/${customerId}/tickets`),

  createTicket: (input: {
    titular_id: string
    uc_id: string | null
    tipo: string
    descricao: string | null
  }) =>
    request<CreateTicketResponse>("/tickets", {
      method: "POST",
      body: JSON.stringify({ ...input, idempotency_key: crypto.randomUUID() }),
    }),

  requestHandoff: (input: { chamado_id: string | null; motivo: string | null }) =>
    request<Handoff>("/handoffs", {
      method: "POST",
      body: JSON.stringify(input),
    }),

  // Notificações proativas (SPEC-009).
  getProactiveCandidates: (phone: string) =>
    request<ProactiveCandidates>(`/proactive/candidates?phone=${encodeURIComponent(phone)}`),

  emitProactiveEvent: (input: {
    phone: string
    tipo: string
    subtipo: string
    dados: Record<string, string>
  }) =>
    request<ProactiveEventResult>("/proactive/events", {
      method: "POST",
      body: JSON.stringify(input),
    }),
}
