import { useState } from "react"
import { toast } from "sonner"
import { Headphones, Plus } from "lucide-react"
import { api, ApiError, type Customer, type Ticket } from "@/lib/api"
import {
  formatDateTime,
  TICKET_TYPES,
  ticketTypeLabel,
  TicketStatusBadge,
} from "@/lib/format"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
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

interface Props {
  customer: Customer
  selectedUcId: string | null
  tickets: Ticket[]
  onChanged: () => void
}

export function TicketsSection({ customer, selectedUcId, tickets, onChanged }: Props) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        <HandoffDialog />
        <CreateTicketDialog customer={customer} ucId={selectedUcId} onCreated={onChanged} />
      </div>

      {tickets.length === 0 ? (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          Nenhum chamado para este cliente.
        </p>
      ) : (
        <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Protocolo</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead className="text-right">SLA</TableHead>
                <TableHead>Aberto em</TableHead>
                <TableHead className="text-right">Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tickets.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-mono text-xs font-medium">{t.protocolo}</TableCell>
                  <TableCell>{ticketTypeLabel(t.tipo)}</TableCell>
                  <TableCell className="text-right tabular-nums">{t.sla_horas}h</TableCell>
                  <TableCell className="tabular-nums">{formatDateTime(t.aberto_em)}</TableCell>
                  <TableCell className="text-right">
                    <TicketStatusBadge status={t.status} />
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
      })
      toast.success(
        res.criado_agora ? "Chamado aberto" : "Chamado já existente (idempotente)",
        { description: `Protocolo ${res.ticket.protocolo} · SLA ${res.ticket.sla_horas}h` },
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
