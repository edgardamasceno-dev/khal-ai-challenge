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
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
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
          <div className="flex size-9 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm shadow-primary/30">
            <Zap className="size-5" />
          </div>
          <div className="mr-auto leading-none">
            <p className="text-[10px] font-medium tracking-[0.18em] text-muted-foreground uppercase">
              Console do Operador
            </p>
            <h1 className="text-lg font-semibold tracking-tight">Luz do Vale</h1>
          </div>
          <StatusMenu />
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-6 py-8">
        <Card>
          <CardContent className="flex flex-col gap-2 py-5 sm:flex-row sm:items-end">
            <div className="grid flex-1 gap-1.5">
              <Label htmlFor="phone">
                Identificar cliente por telefone
              </Label>
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
          <TooltipProvider delayDuration={200}>
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">Personas cadastradas:</span>
              {personas.map((p) => (
                <Tooltip key={p.telefone}>
                  <TooltipTrigger asChild>
                    <Badge asChild variant="secondary" className="font-mono text-[11px] tabular-nums">
                      <button
                        type="button"
                        className="cursor-pointer hover:bg-secondary/70"
                        onClick={() => {
                          setPhone(p.telefone)
                          search(p.telefone)
                        }}
                      >
                        {p.nome.split(" ")[0]} · {p.telefone}
                      </button>
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent>
                    <span className="font-sans">{p.nome}</span>
                    {p.persona_key && (
                      <span className="font-mono text-muted-foreground">{p.persona_key}</span>
                    )}
                  </TooltipContent>
                </Tooltip>
              ))}
            </div>
          </TooltipProvider>
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
    <Empty className="rounded-xl border py-20">
      <EmptyHeader>
        <EmptyMedia variant="icon" className="size-12 rounded-full">
          <Search className="size-6" />
        </EmptyMedia>
        <EmptyTitle>Busque um cliente para começar</EmptyTitle>
        <EmptyDescription>
          Informe o telefone do titular (E.164){" "}
          {hasPersonas
            ? "ou clique numa das personas cadastradas acima."
            : "para abrir o atendimento."}
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
