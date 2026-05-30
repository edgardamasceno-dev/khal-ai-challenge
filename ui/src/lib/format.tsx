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

const INVOICE_TONE: Record<string, string> = {
  paga: "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
  em_aberto: "border-amber-600/30 bg-amber-600/10 text-amber-700 dark:text-amber-400",
  vencida: "border-red-600/30 bg-red-600/10 text-red-700 dark:text-red-400",
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
  verde: "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
  amarela: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  vermelha_p1: "border-red-600/30 bg-red-600/10 text-red-700 dark:text-red-400",
  vermelha_p2: "border-red-700/40 bg-red-700/15 text-red-800 dark:text-red-300",
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
  aberto: "border-blue-600/30 bg-blue-600/10 text-blue-700 dark:text-blue-400",
  em_andamento: "border-amber-600/30 bg-amber-600/10 text-amber-700 dark:text-amber-400",
  resolvido: "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-400",
  escalado: "border-purple-600/30 bg-purple-600/10 text-purple-700 dark:text-purple-400",
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
