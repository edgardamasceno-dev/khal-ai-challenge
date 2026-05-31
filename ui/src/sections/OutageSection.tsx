import { useEffect, useState } from "react"
import { AlertTriangle, CheckCircle2, Search } from "lucide-react"
import { api, type OutageResult } from "@/lib/api"
import { formatDateTime } from "@/lib/format"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

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

      {result?.encontrada && result.interrupcao && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Interrupção ativa em {result.interrupcao.bairro}</AlertTitle>
          <AlertDescription>
            <span className="capitalize">{result.interrupcao.tipo.replace("_", " ")}</span>
            {result.interrupcao.causa ? ` — ${result.interrupcao.causa}.` : "."}
            {result.interrupcao.previsao_retorno && (
              <> Previsão de retorno: {formatDateTime(result.interrupcao.previsao_retorno)}.</>
            )}
          </AlertDescription>
        </Alert>
      )}

      {result && !result.encontrada && (
        <Alert>
          <CheckCircle2 />
          <AlertTitle>Sem interrupções ativas</AlertTitle>
          <AlertDescription>
            Nenhuma interrupção registrada para "{bairro}". Ofereça abrir um chamado se necessário.
          </AlertDescription>
        </Alert>
      )}
    </div>
  )
}
