import { useEffect, useState } from "react"
import { AlertTriangle, CheckCircle2, MapPinned, Search } from "lucide-react"
import { api, type OutageResult } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Skeleton } from "@/components/ui/skeleton"
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty"

export function OutageSection({ defaultBairro }: { defaultBairro: string }) {
  const [bairro, setBairro] = useState(defaultBairro)
  const [result, setResult] = useState<OutageResult | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setBairro(defaultBairro)
    setResult(null)
  }, [defaultBairro])

  async function check() {
    if (!bairro.trim()) return
    setLoading(true)
    try {
      setResult(await api.getOutage(bairro.trim()))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-2">
        <div className="grid flex-1 gap-1.5">
          <Label htmlFor="bairro">Bairro</Label>
          <Input
            id="bairro"
            value={bairro}
            onChange={(e) => setBairro(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && check()}
            placeholder="Ex.: Jardim das Flores"
          />
        </div>
        <Button onClick={check} disabled={loading}>
          <Search /> Consultar
        </Button>
      </div>

      {loading && (
        <div className="space-y-2 rounded-lg border p-4">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-1/2" />
        </div>
      )}

      {!loading && result?.encontrada && result.interrupcao && (
        <Alert
          variant="destructive"
          className="border-status-danger/50 bg-status-danger-surface shadow-sm [&>svg]:text-status-danger"
        >
          <AlertTriangle className="size-5" />
          <AlertTitle className="text-base font-semibold text-status-danger-foreground">
            Interrupção ativa em {result.interrupcao.bairro}
          </AlertTitle>
          <AlertDescription className="text-status-danger-foreground/90">
            <span className="capitalize">{result.interrupcao.tipo.replace("_", " ")}</span>
            {result.interrupcao.causa ? ` — ${result.interrupcao.causa}.` : "."}
            {result.interrupcao.previsao_retorno && (
              <> Previsão de retorno: {formatDateTime(result.interrupcao.previsao_retorno)}.</>
            )}
          </AlertDescription>
        </Alert>
      )}

      {!loading && result && !result.encontrada && (
        <Alert className="border-status-ok/30 bg-status-ok-surface [&>svg]:text-status-ok">
          <CheckCircle2 />
          <AlertTitle className="text-status-ok-foreground">Sem interrupções ativas</AlertTitle>
          <AlertDescription>
            Nenhuma interrupção registrada para "{bairro}". Ofereça abrir um chamado se necessário.
          </AlertDescription>
        </Alert>
      )}

      {!loading && !result && (
        <Empty className="border py-12">
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <MapPinned />
            </EmptyMedia>
            <EmptyTitle>Consulte um bairro</EmptyTitle>
            <EmptyDescription>
              Informe o bairro do cliente para verificar interrupções ativas na região.
            </EmptyDescription>
          </EmptyHeader>
        </Empty>
      )}
    </div>
  )
}
