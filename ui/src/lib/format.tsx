import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export function formatDate(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" })
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function initials(nome: string): string {
  return nome
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("")
}

// Tons de severidade ancorados nos tokens --status-* (fonte unica de verdade de cor).
const STATUS_TONE = {
  ok: "border-status-ok/30 bg-status-ok-surface text-status-ok-foreground",
  warn: "border-status-warn/30 bg-status-warn-surface text-status-warn-foreground",
  danger: "border-status-danger/30 bg-status-danger-surface text-status-danger-foreground",
  info: "border-status-info/30 bg-status-info-surface text-status-info-foreground",
} as const

const INVOICE_TONE: Record<string, string> = {
  paga: STATUS_TONE.ok,
  em_aberto: STATUS_TONE.warn,
  vencida: STATUS_TONE.danger,
}

const INVOICE_LABEL: Record<string, string> = {
  paga: "Paga",
  em_aberto: "Em aberto",
  vencida: "Vencida",
}

export function InvoiceStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-medium", INVOICE_TONE[status])}>
      {INVOICE_LABEL[status] ?? status}
    </Badge>
  )
}

const BANDEIRA_TONE: Record<string, string> = {
  verde: STATUS_TONE.ok,
  amarela: STATUS_TONE.warn,
  vermelha_p1: STATUS_TONE.danger,
  vermelha_p2: "border-status-danger/50 bg-status-danger/15 text-status-danger-foreground",
}

const BANDEIRA_LABEL: Record<string, string> = {
  verde: "Verde",
  amarela: "Amarela",
  vermelha_p1: "Vermelha P1",
  vermelha_p2: "Vermelha P2",
}

export function BandeiraBadge({ bandeira }: { bandeira: string }) {
  return (
    <Badge variant="outline" className={cn(BANDEIRA_TONE[bandeira])}>
      {BANDEIRA_LABEL[bandeira] ?? bandeira}
    </Badge>
  )
}

const TICKET_TONE: Record<string, string> = {
  aberto: STATUS_TONE.info,
  em_andamento: STATUS_TONE.warn,
  resolvido: STATUS_TONE.ok,
  escalado: STATUS_TONE.danger,
}

export function TicketStatusBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("capitalize", TICKET_TONE[status])}>
      {status.replace("_", " ")}
    </Badge>
  )
}

export const TICKET_TYPES = [
  { value: "falta_energia", label: "Falta de energia" },
  { value: "religacao", label: "Religação" },
  { value: "segunda_via", label: "Segunda via" },
  { value: "titularidade", label: "Titularidade" },
  { value: "reclamacao", label: "Reclamação" },
]

export function ticketTypeLabel(value: string): string {
  return TICKET_TYPES.find((t) => t.value === value)?.label ?? value
}
