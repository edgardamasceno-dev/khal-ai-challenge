import { useEffect, useState } from "react"
import { BellRing, CheckCircle2, Send, Zap } from "lucide-react"
import { toast } from "sonner"
import { api, type ProactiveCandidates } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

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
    } catch {
      toast.error("Falha ao disparar a notificação")
    } finally {
      setBusy(null)
    }
  }

  if (!data?.encontrado) {
    return (
      <Alert>
        <BellRing />
        <AlertTitle>Sem candidatos</AlertTitle>
        <AlertDescription>
          Nenhum evento proativo elegível para este cliente no momento.
        </AlertDescription>
      </Alert>
    )
  }

  const pagamentos = data.pagamentos ?? []
  const outages = data.outages ?? []

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        Dispare avisos <strong>determinísticos</strong> (sem IA) ao cliente — registrados na
        memória do agente (ADR-0005).
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
          {pagamentos.map((p) => (
            <div key={p.fatura_id} className="flex items-center justify-between gap-2">
              <div className="text-sm">
                UC {p.numero_uc} · {p.mes_referencia} · <strong>{p.valor}</strong>{" "}
                <Badge variant="outline">{p.status}</Badge>
              </div>
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
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="py-3">
          <CardTitle className="text-sm">Status de interrupção</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {outages.length === 0 && (
            <p className="text-sm text-muted-foreground">Sem interrupção ativa no bairro.</p>
          )}
          {outages.map((o) => (
            <div key={o.bairro} className="flex items-center justify-between gap-2">
              <div className="text-sm">
                <Zap className="inline size-3.5" /> {o.bairro}{" "}
                <Badge variant="outline">{o.status}</Badge>
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy !== null}
                  onClick={() =>
                    emit(`${o.bairro}-aberta`, "outage", "aberta", {
                      bairro: o.bairro,
                      previsao: o.previsao ?? "",
                    })
                  }
                >
                  Avisar interrupção
                </Button>
                <Button
                  size="sm"
                  disabled={busy !== null}
                  onClick={() =>
                    emit(`${o.bairro}-encerrada`, "outage", "encerrada", { bairro: o.bairro })
                  }
                >
                  Avisar normalização
                </Button>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
