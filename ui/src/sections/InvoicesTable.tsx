import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { api, type Invoice } from "@/lib/api"
import { BandeiraBadge, formatDate, InvoiceStatusBadge } from "@/lib/format"
import { cn } from "@/lib/utils"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Skeleton } from "@/components/ui/skeleton"

export function InvoicesTable({ ucId }: { ucId: string }) {
  const [invoices, setInvoices] = useState<Invoice[] | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setInvoices(await api.listInvoices(ucId))
  }, [ucId])

  useEffect(() => {
    let active = true
    setInvoices(null)
    api.listInvoices(ucId).then((data) => active && setInvoices(data))
    return () => {
      active = false
    }
  }, [ucId])

  async function changeStatus(inv: Invoice, status: "em_aberto" | "vencida") {
    if (status === inv.status) return
    setBusy(inv.id)
    try {
      await api.updateInvoiceStatus(inv.id, status)
      // SPEC-011: a mutação persiste no banco; 'vencida' também notifica o cliente.
      toast.success(
        status === "vencida"
          ? "Fatura marcada como vencida — aviso disparado ao cliente"
          : "Fatura marcada como em aberto",
      )
      await load()
    } catch {
      toast.error("Não foi possível alterar o status da fatura")
    } finally {
      setBusy(null)
    }
  }

  if (invoices === null) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/30">
            <TableHead>Mês</TableHead>
            <TableHead className="text-right">Consumo</TableHead>
            <TableHead className="text-right">Valor</TableHead>
            <TableHead>Bandeira</TableHead>
            <TableHead>Vencimento</TableHead>
            <TableHead className="text-right">Status</TableHead>
            <TableHead className="border-l text-right">Ajustar</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoices.map((inv) => {
            const vencida = inv.status === "vencida"
            return (
              <TableRow key={inv.id} className={cn(vencida && "bg-status-danger-surface/40")}>
                <TableCell className="font-mono text-xs font-medium tabular-nums">
                  {inv.mes_referencia}
                </TableCell>
                <TableCell className="text-right font-mono text-xs tabular-nums text-muted-foreground">
                  {inv.consumo_kwh} kWh
                </TableCell>
                <TableCell className="text-right font-medium tabular-nums">
                  {inv.valor_formatado}
                </TableCell>
                <TableCell>
                  <BandeiraBadge bandeira={inv.bandeira} />
                </TableCell>
                <TableCell
                  className={cn(
                    "font-mono text-xs tabular-nums",
                    vencida && "font-semibold text-status-danger-foreground",
                  )}
                >
                  {formatDate(inv.vencimento)}
                </TableCell>
                <TableCell className="text-right">
                  <InvoiceStatusBadge status={inv.status} />
                </TableCell>
                <TableCell className="border-l bg-muted/20 text-right">
                  <Select
                    value={inv.status}
                    disabled={busy !== null}
                    onValueChange={(v) => changeStatus(inv, v as "em_aberto" | "vencida")}
                  >
                    <SelectTrigger size="sm" className="ml-auto w-[140px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="em_aberto">Em aberto</SelectItem>
                      <SelectItem value="vencida">Vencida</SelectItem>
                      {inv.status === "paga" && (
                        <SelectItem value="paga" disabled>
                          Paga
                        </SelectItem>
                      )}
                    </SelectContent>
                  </Select>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}
