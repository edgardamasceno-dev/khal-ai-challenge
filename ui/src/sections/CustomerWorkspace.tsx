import { useEffect, useState } from "react"
import { Mail, MapPin, Zap } from "lucide-react"
import type { Contract, Customer, Ticket } from "@/lib/api"
import { initials } from "@/lib/format"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { ChatSection } from "./ChatSection"
import { InvoicesTable } from "./InvoicesTable"
import { OutageSection } from "./OutageSection"
import { ProactiveSection } from "./ProactiveSection"
import { TicketsSection } from "./TicketsSection"

interface Props {
  customer: Customer
  contracts: Contract[]
  tickets: Ticket[]
  phone: string
  onTicketsChanged: () => void
}

export function CustomerWorkspace({ customer, contracts, tickets, phone, onTicketsChanged }: Props) {
  const [selectedUcId, setSelectedUcId] = useState<string | null>(
    contracts[0]?.unidade.id ?? null,
  )

  useEffect(() => {
    setSelectedUcId(contracts[0]?.unidade.id ?? null)
  }, [contracts])

  const selected = contracts.find((c) => c.unidade.id === selectedUcId)?.unidade ?? null

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <Card className="h-fit">
        <CardHeader className="flex-row items-center gap-3 space-y-0">
          <Avatar className="size-11">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold">
              {initials(customer.nome)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <CardTitle className="truncate">{customer.nome}</CardTitle>
            {customer.persona_key && (
              <Badge variant="secondary" className="mt-1 font-mono text-[10px]">
                {customer.persona_key}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Row label="CPF" value={customer.cpf_mascarado} mono />
          <Row label="Telefone" value={customer.telefone_mascarado} mono />
          {customer.email && (
            <div className="flex items-center gap-2 text-muted-foreground">
              <Mail className="size-4 shrink-0" />
              <span className="truncate">{customer.email}</span>
            </div>
          )}
          <Separator />
          <div className="flex items-center gap-2 text-muted-foreground">
            <Zap className="size-4 shrink-0" />
            {contracts.length} unidade{contracts.length === 1 ? "" : "s"} consumidora
            {contracts.length === 1 ? "" : "s"}
          </div>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {contracts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {contracts.map((c) => (
              <Button
                key={c.unidade.id}
                variant={c.unidade.id === selectedUcId ? "default" : "outline"}
                size="sm"
                onClick={() => setSelectedUcId(c.unidade.id)}
                className="h-auto py-2"
              >
                <div className="text-left">
                  <div className="font-mono text-xs">UC {c.unidade.numero_uc}</div>
                  <div className="text-[11px] opacity-80">{c.unidade.bairro}</div>
                </div>
              </Button>
            ))}
          </div>
        )}

        <Tabs defaultValue="faturas">
          <TabsList>
            <TabsTrigger value="faturas">Unidade &amp; Faturas</TabsTrigger>
            <TabsTrigger value="interrupcoes">Interrupções</TabsTrigger>
            <TabsTrigger value="chamados">
              Chamados
              {tickets.length > 0 && (
                <Badge variant="secondary" className="ml-1.5">
                  {tickets.length}
                </Badge>
              )}
            </TabsTrigger>
            <TabsTrigger value="chat">Chat</TabsTrigger>
            <TabsTrigger value="proativos">Proativos</TabsTrigger>
          </TabsList>

          <TabsContent value="faturas" className="space-y-4 pt-2">
            {selected && (
              <Card>
                <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-1 py-4 text-sm">
                  <span className="flex items-center gap-1.5 text-muted-foreground">
                    <MapPin className="size-4" />
                    {selected.logradouro ? `${selected.logradouro}, ` : ""}
                    {selected.bairro} — {selected.cidade}/{selected.uf}
                  </span>
                  <span className="capitalize">{selected.classe}</span>
                  {selected.subgrupo && <span>Subgrupo {selected.subgrupo}</span>}
                  <Badge
                    variant="outline"
                    className={cn(
                      "ml-auto capitalize",
                      selected.status === "ativa"
                        ? "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-400"
                        : "border-red-600/30 bg-red-600/10 text-red-700 dark:text-red-400",
                    )}
                  >
                    {selected.status}
                  </Badge>
                </CardContent>
              </Card>
            )}
            {selectedUcId && <InvoicesTable ucId={selectedUcId} />}
          </TabsContent>

          <TabsContent value="interrupcoes" className="pt-2">
            <OutageSection defaultBairro={selected?.bairro ?? ""} />
          </TabsContent>

          <TabsContent value="chamados" className="pt-2">
            <TicketsSection
              customer={customer}
              selectedUcId={selectedUcId}
              tickets={tickets}
              onChanged={onTicketsChanged}
            />
          </TabsContent>

          <TabsContent value="chat" className="pt-2">
            <ChatSection phone={phone} />
          </TabsContent>

          <TabsContent value="proativos" className="pt-2">
            <ProactiveSection phone={phone} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono" : ""}>{value}</span>
    </div>
  )
}
