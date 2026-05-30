import { useEffect, useState } from "react"
import { api, type Invoice } from "@/lib/api"
import { BandeiraBadge, formatDate, InvoiceStatusBadge } from "@/lib/format"
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

  useEffect(() => {
    let active = true
    setInvoices(null)
    api.listInvoices(ucId).then((data) => active && setInvoices(data))
    return () => {
      active = false
    }
  }, [ucId])

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
    <div className="rounded-lg border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Mês</TableHead>
            <TableHead className="text-right">Consumo</TableHead>
            <TableHead className="text-right">Valor</TableHead>
            <TableHead>Bandeira</TableHead>
            <TableHead>Vencimento</TableHead>
            <TableHead className="text-right">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {invoices.map((inv) => (
            <TableRow key={inv.id}>
              <TableCell className="font-medium tabular-nums">{inv.mes_referencia}</TableCell>
              <TableCell className="text-right tabular-nums">{inv.consumo_kwh} kWh</TableCell>
              <TableCell className="text-right tabular-nums">{inv.valor_formatado}</TableCell>
              <TableCell>
                <BandeiraBadge bandeira={inv.bandeira} />
              </TableCell>
              <TableCell className="tabular-nums">{formatDate(inv.vencimento)}</TableCell>
              <TableCell className="text-right">
                <InvoiceStatusBadge status={inv.status} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
