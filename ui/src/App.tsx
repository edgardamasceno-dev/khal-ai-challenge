import { useEffect, useState } from "react"
import { toast } from "sonner"
import { Search, Zap } from "lucide-react"
import {
  api,
  ApiError,
  type Contract,
  type Customer,
  type Persona,
  type Ticket,
} from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { CustomerWorkspace } from "@/sections/CustomerWorkspace"
import { StatusMenu } from "@/sections/StatusMenu"

export default function App() {
  const [phone, setPhone] = useState("")
  const [loading, setLoading] = useState(false)
  const [customer, setCustomer] = useState<Customer | null>(null)
  const [contracts, setContracts] = useState<Contract[]>([])
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])

  useEffect(() => {
    // SPEC-012: atalhos vêm das personas realmente cadastradas (não hardcoded).
    api.listPersonas().then(setPersonas).catch(() => setPersonas([]))
  }, [])

  async function search(value: string = phone) {
    value = value.trim()
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
          <StatusMenu />
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
                placeholder="Telefone do titular (E.164)"
                className="font-mono"
              />
            </div>
            <Button onClick={() => search()} disabled={loading}>
              <Search /> {loading ? "Buscando…" : "Buscar"}
            </Button>
          </CardContent>
        </Card>

        {personas.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">Personas cadastradas:</span>
            {personas.map((p) => (
              <Badge
                key={p.telefone}
                variant="secondary"
                className="cursor-pointer font-mono text-[11px] hover:bg-secondary/70"
                onClick={() => {
                  setPhone(p.telefone)
                  search(p.telefone)
                }}
              >
                {p.nome.split(" ")[0]} · {p.telefone}
              </Badge>
            ))}
          </div>
        )}

        {customer ? (
          <CustomerWorkspace
            customer={customer}
            contracts={contracts}
            tickets={tickets}
            phone={phone.trim()}
            onTicketsChanged={refreshTickets}
          />
        ) : (
          <EmptyState hasPersonas={personas.length > 0} />
        )}
      </main>
    </div>
  )
}

function EmptyState({ hasPersonas }: { hasPersonas: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed py-20 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <Search className="size-6" />
      </div>
      <p className="text-sm font-medium">Busque um cliente para começar</p>
      <p className="max-w-sm text-sm text-muted-foreground">
        Informe o telefone do titular (E.164){" "}
        {hasPersonas
          ? "ou clique numa das personas cadastradas acima."
          : "para abrir o atendimento."}
      </p>
    </div>
  )
}
