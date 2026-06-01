import { useEffect, useState } from "react"
import { CreditCard, Mail, MapPin, Phone, Zap } from "lucide-react"
import type { Contract, Customer, Ticket } from "@/lib/api"
import { initials } from "@/lib/format"
import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import {
  Item,
  ItemContent,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
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
  const selectedInativa = selected?.status === "inativa"

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <Card className="h-fit lg:sticky lg:top-20">
        <CardHeader className="flex-row items-center gap-3 space-y-0 pb-3">
          <Avatar className="size-11 ring-1 ring-primary/15">
            <AvatarFallback className="bg-primary/10 text-primary font-semibold">
              {initials(customer.nome)}
            </AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="text-[10px] font-medium tracking-[0.16em] text-muted-foreground uppercase">
              Titular
            </p>
            <CardTitle className="truncate text-base leading-tight">{customer.nome}</CardTitle>
            {customer.persona_key && (
              <Badge variant="secondary" className="mt-1 font-mono text-[10px] tabular-nums">
                {customer.persona_key}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <ItemGroup className="gap-0">
            <DossierRow icon={CreditCard} label="CPF" value={customer.cpf_mascarado} mono />
            <ItemSeparatorLine />
            <DossierRow
              icon={Phone}
              label="Telefone"
              value={customer.telefone_mascarado}
              mono
            />
            {customer.email && (
              <>
                <ItemSeparatorLine />
                <DossierRow icon={Mail} label="E-mail" value={customer.email} />
              </>
            )}
            <ItemSeparatorLine />
            <DossierRow
              icon={Zap}
              label="Unidades consumidoras"
              value={String(contracts.length)}
              mono
            />
          </ItemGroup>
        </CardContent>
      </Card>

      <div className="space-y-4">
        {contracts.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {contracts.map((c) => {
              const ativa = c.unidade.id === selectedUcId
              const inativa = c.unidade.status === "inativa"
              return (
                <Button
                  key={c.unidade.id}
                  variant={ativa ? "default" : "outline"}
                  size="sm"
                  onClick={() => setSelectedUcId(c.unidade.id)}
                  className={cn(
                    "h-auto py-2",
                    inativa && !ativa && "border-status-danger/40 text-status-danger-foreground",
                  )}
                >
                  <div className="text-left">
                    <div className="font-mono text-xs tabular-nums">UC {c.unidade.numero_uc}</div>
                    <div className="text-[11px] opacity-80">{c.unidade.bairro}</div>
                  </div>
                </Button>
              )
            })}
          </div>
        )}

        <Tabs defaultValue="faturas">
          <TabsList>
            <TabsTrigger value="faturas">
              Unidade &amp; Faturas
              {selectedInativa && (
                <span
                  aria-hidden
                  className="ml-1.5 inline-block size-1.5 rounded-full bg-status-danger"
                />
              )}
            </TabsTrigger>
            <TabsTrigger value="interrupcoes">Interrupções</TabsTrigger>
            <TabsTrigger value="chamados">
              Chamados
              {tickets.length > 0 && (
                <Badge variant="secondary" className="ml-1.5 tabular-nums">
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
                    <MapPin className="size-4 shrink-0" />
                    {selected.logradouro ? `${selected.logradouro}, ` : ""}
                    {selected.bairro} — {selected.cidade}/{selected.uf}
                  </span>
                  <span className="capitalize">{selected.classe}</span>
                  {selected.subgrupo && (
                    <span className="font-mono text-xs">Subgrupo {selected.subgrupo}</span>
                  )}
                  <Badge
                    variant="outline"
                    className={cn(
                      "ml-auto capitalize",
                      selected.status === "ativa"
                        ? "border-status-ok/30 bg-status-ok-surface text-status-ok-foreground"
                        : "border-status-danger/30 bg-status-danger-surface text-status-danger-foreground",
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

function ItemSeparatorLine() {
  return <Separator className="opacity-60" />
}

function DossierRow({
  icon: Icon,
  label,
  value,
  mono,
}: {
  icon: typeof Mail
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <Item size="sm" className="px-0">
      <ItemMedia variant="icon" className="text-muted-foreground">
        <Icon />
      </ItemMedia>
      <ItemContent className="flex-row items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{label}</span>
        <ItemTitle className={cn("min-w-0 truncate", mono && "font-mono tabular-nums")}>
          {value}
        </ItemTitle>
      </ItemContent>
    </Item>
  )
}
