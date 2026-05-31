import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import {
  BotMessageSquare,
  ChevronDown,
  CircleCheckBig,
  Headphones,
  Inbox,
  Plus,
} from "lucide-react"
import { api, ApiError, type Customer, type Handoff, type Ticket } from "@/lib/api"
import {
  formatDateTime,
  TICKET_TYPES,
  ticketTypeLabel,
  TicketStatusBadge,
} from "@/lib/format"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface Props {
  customer: Customer
  selectedUcId: string | null
  tickets: Ticket[]
  onChanged: () => void
}

export function TicketsSection({ customer, selectedUcId, tickets, onChanged }: Props) {
  const [busy, setBusy] = useState<string | null>(null)

  async function resolve(t: Ticket) {
    setBusy(t.id)
    try {
      await api.resolveTicket(t.protocolo)
      toast.success("Chamado resolvido", {
        description: `Protocolo ${t.protocolo} · cliente avisado no WhatsApp.`,
      })
      onChanged()
    } catch (e) {
      toast.error("Não foi possível encerrar o chamado", {
        description: e instanceof ApiError ? e.message : String(e),
      })
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        <HandoffDialog />
        <CreateTicketDialog customer={customer} ucId={selectedUcId} onCreated={onChanged} />
      </div>

      <HandoffQueue />

      {tickets.length === 0 ? (
        <Empty className="border py-12">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <Inbox />
            </EmptyMedia>
            <EmptyTitle>Nenhum chamado</EmptyTitle>
            <EmptyDescription>Nenhum chamado para este cliente.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      ) : (
        <div className="overflow-hidden rounded-lg border">
          <div className="flex items-center justify-between gap-2 border-b bg-muted/30 px-4 py-2.5">
            <span className="text-sm font-semibold tracking-tight">Chamados</span>
            <Badge variant="secondary" className="tabular-nums">
              {tickets.length}
            </Badge>
          </div>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-xs font-medium text-muted-foreground uppercase">
                  Protocolo
                </TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground uppercase">
                  Tipo
                </TableHead>
                <TableHead className="text-right text-xs font-medium text-muted-foreground uppercase">
                  SLA
                </TableHead>
                <TableHead className="text-xs font-medium text-muted-foreground uppercase">
                  Aberto em
                </TableHead>
                <TableHead className="text-right text-xs font-medium text-muted-foreground uppercase">
                  Status
                </TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {tickets.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <span className="font-mono text-xs font-medium tabular-nums">
                          {t.protocolo}
                        </span>
                      </TooltipTrigger>
                      <TooltipContent>Protocolo do chamado</TooltipContent>
                    </Tooltip>
                  </TableCell>
                  <TableCell>{ticketTypeLabel(t.tipo)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">
                    {t.sla_horas}h
                  </TableCell>
                  <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                    {formatDateTime(t.aberto_em)}
                  </TableCell>
                  <TableCell className="text-right">
                    <TicketStatusBadge status={t.status} />
                  </TableCell>
                  <TableCell className="text-right">
                    {t.status === "aberto" && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-7"
                            disabled={busy !== null}
                            aria-label="Ações do chamado"
                          >
                            <ChevronDown />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onSelect={() => resolve(t)}>
                            <CircleCheckBig /> Encerrar como resolvido
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

function CreateTicketDialog({
  customer,
  ucId,
  onCreated,
}: {
  customer: Customer
  ucId: string | null
  onCreated: () => void
}) {
  const [open, setOpen] = useState(false)
  const [tipo, setTipo] = useState("falta_energia")
  const [descricao, setDescricao] = useState("")
  const [saving, setSaving] = useState(false)

  async function submit() {
    setSaving(true)
    try {
      const res = await api.createTicket({
        titular_id: customer.id,
        uc_id: ucId,
        tipo,
        descricao: descricao.trim() || null,
        notificar: true,
      })
      toast.success(
        res.criado_agora ? "Chamado aberto" : "Chamado já existente (idempotente)",
        {
          description: res.criado_agora
            ? `Protocolo ${res.ticket.protocolo} · SLA ${res.ticket.sla_horas}h · cliente avisado no WhatsApp.`
            : `Protocolo ${res.ticket.protocolo} · SLA ${res.ticket.sla_horas}h`,
        },
      )
      setOpen(false)
      setDescricao("")
      onCreated()
    } catch (e) {
      toast.error("Não foi possível abrir o chamado", {
        description: e instanceof ApiError ? e.message : String(e),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> Abrir chamado
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Abrir chamado</DialogTitle>
          <DialogDescription>
            Confirme os dados antes de registrar — para {customer.nome}.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-1.5">
            <Label>Tipo</Label>
            <Select value={tipo} onValueChange={setTipo}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TICKET_TYPES.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="descricao">Descrição</Label>
            <Textarea
              id="descricao"
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              placeholder="Resumo do problema relatado pelo cliente"
            />
          </div>
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancelar</Button>
          </DialogClose>
          <Button onClick={submit} disabled={saving}>
            Confirmar e abrir
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function HandoffDialog() {
  const [open, setOpen] = useState(false)
  const [motivo, setMotivo] = useState("")
  const [saving, setSaving] = useState(false)

  async function submit() {
    setSaving(true)
    try {
      await api.requestHandoff({ chamado_id: null, motivo: motivo.trim() || null })
      toast.success("Handoff solicitado", { description: "Item adicionado à fila do operador." })
      setOpen(false)
      setMotivo("")
    } catch (e) {
      toast.error("Não foi possível solicitar handoff", {
        description: e instanceof ApiError ? e.message : String(e),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">
          <Headphones /> Handoff
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Solicitar handoff humano</DialogTitle>
          <DialogDescription>Escala o atendimento para um operador.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-1.5 py-2">
          <Label htmlFor="motivo">Motivo</Label>
          <Textarea
            id="motivo"
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Por que está escalando?"
          />
        </div>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancelar</Button>
          </DialogClose>
          <Button onClick={submit} disabled={saving}>
            Solicitar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Fila de atendimento humano: handoffs pendentes + devolver à IA (SPEC-016). */
function HandoffQueue() {
  const [items, setItems] = useState<Handoff[]>([])
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(() => {
    api
      .listHandoffs()
      .then(setItems)
      .catch(() => setItems([]))
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, 15000)
    return () => clearInterval(id)
  }, [load])

  async function resume(h: Handoff) {
    setBusy(h.id)
    try {
      await api.resumeHandoff(h.id)
      toast.success("Atendimento devolvido à IA")
      load()
    } catch {
      toast.error("Não foi possível devolver à IA")
    } finally {
      setBusy(null)
    }
  }

  if (items.length === 0) return null

  return (
    <div className="overflow-hidden rounded-lg border border-status-warn/40 bg-status-warn-surface/50">
      <div className="flex items-center gap-2 border-b border-status-warn/30 px-4 py-2.5 text-sm font-semibold tracking-tight text-status-warn-foreground">
        <Headphones className="size-4 text-status-warn" />
        Atendimento humano
        <Badge
          variant="outline"
          className="ml-auto border-status-warn/30 bg-status-warn-surface text-status-warn-foreground tabular-nums"
        >
          {items.length}
        </Badge>
      </div>
      <ItemGroup className="gap-0 divide-y divide-status-warn/20">
        {items.map((h) => (
          <Item key={h.id} size="sm" className="rounded-none">
            <ItemMedia variant="icon" className="text-status-warn">
              <Headphones />
            </ItemMedia>
            <ItemContent>
              <ItemTitle>{h.motivo ?? "Handoff solicitado"}</ItemTitle>
              <ItemDescription className="font-mono text-xs tabular-nums">
                {formatDateTime(h.criado_em)}
              </ItemDescription>
            </ItemContent>
            <ItemActions>
              <Button
                size="sm"
                variant="outline"
                disabled={busy !== null}
                onClick={() => resume(h)}
              >
                <BotMessageSquare /> Devolver à IA
              </Button>
            </ItemActions>
          </Item>
        ))}
      </ItemGroup>
    </div>
  )
}
