import { useEffect, useState } from "react"
import { BellRing, CheckCircle2, CreditCard, Send, Zap } from "lucide-react"
import { toast } from "sonner"
import { api, type ProactiveCandidates } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Item,
  ItemActions,
  ItemContent,
  ItemGroup,
  ItemMedia,
  ItemTitle,
} from "@/components/ui/item"
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from "@/components/ui/empty"

export function ProactiveSection({ phone }: { phone: string }) {
  const [data, setData] = useState<ProactiveCandidates | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)

  async function load() {
    if (!phone) return
    try {
      setData(await api.getProactiveCandidates(phone))
    } catch {
      setData(null)
    }
  }

  useEffect(() => {
    setPreview(null)
    load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phone])

  async function emit(
    key: string,
    tipo: string,
    subtipo: string,
    dados: Record<string, string>,
  ) {
    setBusy(key)
    try {
      const res = await api.emitProactiveEvent({ phone, tipo, subtipo, dados })
      setPreview(res.preview)
      toast.success("Notificação disparada", { description: res.subject })
      // SPEC-010: o disparo muta o estado (fatura paga / status da interrupção).
      // Recarrega os candidatos para refletir o banco (fatura some, toggle inverte).
      await load()
    } catch {
      toast.error("Falha ao disparar a notificação")
    } finally {
      setBusy(null)
    }
  }

  if (data === null) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="space-y-2 rounded-lg border p-4">
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-9 w-full" />
          </div>
        ))}
      </div>
    )
  }

  if (!data.encontrado) {
    return (
      <Empty className="border py-12">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <BellRing />
          </EmptyMedia>
          <EmptyTitle>Sem candidatos</EmptyTitle>
          <EmptyDescription>
            Nenhum evento proativo elegível para este cliente no momento.
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    )
  }

  const pagamentos = data.pagamentos ?? []
  const outages = data.outages ?? []

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Dispare avisos ao cliente sobre pagamento e interrupções.
      </p>

      {preview && (
        <Alert>
          <CheckCircle2 />
          <AlertTitle>Mensagem enviada</AlertTitle>
          <AlertDescription className="whitespace-pre-wrap">{preview}</AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">Baixa de pagamento</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {pagamentos.length === 0 && (
            <p className="text-sm text-muted-foreground">Sem faturas em aberto.</p>
          )}
          <ItemGroup className="gap-2">
            {pagamentos.map((p) => (
              <Item key={p.fatura_id} variant="outline" size="sm">
                <ItemMedia variant="icon" className="text-muted-foreground">
                  <CreditCard />
                </ItemMedia>
                <ItemContent className="gap-0.5">
                  <ItemTitle className="font-mono text-xs tabular-nums">
                    UC {p.numero_uc} · {p.mes_referencia}
                  </ItemTitle>
                  <div className="flex items-center gap-2 text-sm">
                    <strong className="tabular-nums">{p.valor}</strong>
                    <Badge variant="outline">{p.status}</Badge>
                  </div>
                </ItemContent>
                <ItemActions>
                  <Button
                    size="sm"
                    disabled={busy !== null}
                    onClick={() =>
                      emit(p.fatura_id, "pagamento", "confirmado", {
                        fatura_id: p.fatura_id,
                        mes: p.mes_referencia,
                        valor: p.valor,
                      })
                    }
                  >
                    <Send /> Avisar pagamento
                  </Button>
                </ItemActions>
              </Item>
            ))}
          </ItemGroup>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">Status de interrupção</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {outages.length === 0 && (
            <p className="text-sm text-muted-foreground">Nenhum bairro associado ao cliente.</p>
          )}
          <ItemGroup className="gap-2">
            {outages.map((o) => {
              const ativa = o.status === "ativa"
              return (
                <Item
                  key={o.bairro}
                  variant="outline"
                  size="sm"
                  className={cn(ativa && "border-status-danger/40 bg-status-danger-surface/40")}
                >
                  <ItemMedia
                    variant="icon"
                    className={ativa ? "text-status-danger" : "text-muted-foreground"}
                  >
                    <Zap />
                  </ItemMedia>
                  <ItemContent className="flex-row items-center gap-2">
                    <ItemTitle>{o.bairro}</ItemTitle>
                    <Badge variant={ativa ? "destructive" : "outline"}>
                      {ativa ? "interrupção ativa" : "normalizado"}
                    </Badge>
                  </ItemContent>
                  <ItemActions>
                    {ativa ? (
                      <Button
                        size="sm"
                        disabled={busy !== null}
                        onClick={() =>
                          emit(`${o.bairro}-encerrada`, "outage", "encerrada", { bairro: o.bairro })
                        }
                      >
                        <Send /> Avisar normalização
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={busy !== null}
                        onClick={() =>
                          emit(`${o.bairro}-aberta`, "outage", "aberta", { bairro: o.bairro })
                        }
                      >
                        <Send /> Avisar interrupção
                      </Button>
                    )}
                  </ItemActions>
                </Item>
              )
            })}
          </ItemGroup>
        </CardContent>
      </Card>
    </div>
  )
}
