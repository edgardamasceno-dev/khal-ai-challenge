import { useEffect, useState } from "react"
import { Settings } from "lucide-react"
import { api, type ComponentHealth } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"

const TONE: Record<string, string> = {
  ok: "bg-status-ok",
  down: "bg-status-danger",
  unknown: "bg-status-warn",
}
const LABEL: Record<string, string> = { api: "API", whatsapp: "WhatsApp", agente: "Agente" }
const ESTADO: Record<string, string> = {
  ok: "online",
  down: "offline",
  unknown: "indeterminado",
}

/** Indicador com brilho animado (halo `animate-ping` + ponto sólido). */
function Pulse({ status, className }: { status: string; className?: string }) {
  const tone = TONE[status] ?? "bg-muted-foreground"
  return (
    <span className={cn("relative flex size-2.5", className)}>
      {status !== "unknown" && (
        <span
          className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-75", tone)}
        />
      )}
      <span className={cn("relative inline-flex size-2.5 rounded-full", tone)} />
    </span>
  )
}

export function StatusMenu() {
  const [health, setHealth] = useState<{ status: string; components: ComponentHealth[] } | null>(
    null,
  )
  const [settingsOpen, setSettingsOpen] = useState(false)

  useEffect(() => {
    let active = true
    const ping = () =>
      api
        .health()
        .then((h) => active && setHealth(h))
        .catch(() => active && setHealth({ status: "degraded", components: [] }))
    ping()
    const id = setInterval(ping, 15000)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [])

  // Verde só quando tudo ok; vermelho quando algo caiu; âmbar enquanto carrega.
  const overall = health === null ? "unknown" : health.status === "ok" ? "ok" : "down"
  const components = health?.components ?? []

  return (
    <>
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" className="gap-1.5">
            <Pulse status={overall} />
            Status
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-56 p-1.5">
          <div className="px-2 py-1.5 text-[10px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
            Componentes
          </div>
          {components.length === 0 && (
            <div className="px-2 py-1.5 text-sm text-muted-foreground">Verificando…</div>
          )}
          {components.map((c) => (
            <div
              key={c.name}
              className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5 text-sm"
            >
              <span className="flex items-center gap-2 font-medium">
                <Pulse status={c.status} />
                {LABEL[c.name] ?? c.name}
              </span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {ESTADO[c.status] ?? c.status}
              </span>
            </div>
          ))}
          <Separator className="my-1" />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => setSettingsOpen(true)}
            className="w-full justify-start gap-2 font-normal"
          >
            <Settings className="size-4 text-muted-foreground" /> Configurações
          </Button>
        </PopoverContent>
      </Popover>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Configurações</DialogTitle>
          </DialogHeader>
          <div className="min-h-40" />
        </DialogContent>
      </Dialog>
    </>
  )
}
