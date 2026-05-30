import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

export function HealthBadge() {
  const [ok, setOk] = useState<boolean | null>(null)

  useEffect(() => {
    let active = true
    const ping = () =>
      api
        .health()
        .then((h) => active && setOk(h.status === "ok"))
        .catch(() => active && setOk(false))
    ping()
    const id = setInterval(ping, 15000)
    return () => {
      active = false
      clearInterval(id)
    }
  }, [])

  return (
    <Badge variant="outline" className="gap-1.5">
      <span
        className={cn(
          "size-2 rounded-full",
          ok === null ? "bg-muted-foreground" : ok ? "bg-emerald-500" : "bg-red-500",
        )}
      />
      {ok === null ? "Verificando" : ok ? "API online" : "API offline"}
    </Badge>
  )
}
