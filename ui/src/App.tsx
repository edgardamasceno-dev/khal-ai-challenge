import { useState } from "react"
import { toast } from "sonner"
import { Search, Zap } from "lucide-react"
import { api, ApiError, type Contract, type Customer, type Ticket } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Card, CardContent } from "@/components/ui/card"
import { CustomerWorkspace } from "@/sections/CustomerWorkspace"
import { HealthBadge } from "@/sections/HealthBadge"

export default function App() {
  const [phone, setPhone] = useState("555199990001")
  const [loading, setLoading] = useState(false)
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [contracts, setContracts] = useState<Contract[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])

  async function search() {
    const value = phone.trim()
    if (!value) return
    setLoading(true)
    try {
      const found = await api.findCustomerByPhone(value)
      const [c, t] = await Promise.all([
        api.listContracts(found.id),
        api.listTickets(found.id),
      ])
      setCustomer(found)
      setContracts(c)
      setTickets(t)
    } catch (e) {
      setCustomer(null)
      setContracts([])
      setTickets([])
      const msg =
        e instanceof ApiError && e.httpStatus === 404
          ? "Nenhum titular para este telefone."
          : e instanceof ApiError
            ? e.message
            : String(e)
      toast.error("Cliente não encontrado", { description: msg })
    } finally {
      setLoading(false)
    }
  }

  async function refreshTickets() {
    if (!customer) return
    setTickets(await api.listTickets(customer.id))
  }

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-6">
          <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Zap className="size-5" />
          </div>
          <div className="mr-auto">
            <h1 className="text-sm leading-tight font-semibold">Luz do Vale</h1>
            <p className="text-xs text-muted-foreground">Console do Operador</p>
          </div>
          <HealthBadge />
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card>
          <CardContent className="flex flex-col gap-2 py-5 sm:flex-row sm:items-end">
            <div className="grid flex-1 gap-1.5">
              <label htmlFor="phone" className="text-sm font-medium">
                Identificar cliente por telefone
              </label>
              <Input
                id="phone"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && search()}
                placeholder="Ex.: 555199990001"
                className="font-mono"
              />
            </div>
            <Button onClick={search} disabled={loading}>
              <Search /> {loading ? "Buscando…" : "Buscar"}
            </Button>
          </CardContent>
        </Card>

        {customer ? (
          <CustomerWorkspace
            customer={customer}
            contracts={contracts}
            tickets={tickets}
            phone={phone.trim()}
            onTicketsChanged={refreshTickets}
          />
        ) : (
          <EmptyState />
        )}
      </main>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed py-20 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Search className="size-6" />
      </div>
      <p className="text-sm font-medium">Busque um cliente para começar</p>
      <p className="max-w-sm text-sm text-muted-foreground">
        Informe o telefone do titular (E.164). Personas de demo: 555199990001 (Ana),
        555199990002 (Carlos), 555199990003 (Joana).
      </p>
    </div>
  )
}
