import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { BotMessageSquare, ChevronUp, Hand, Send } from "lucide-react"
import { api, type ChatMessage } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const PAGE = 10
const POLL_MS = 5000

function hora(iso: string) {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
}

export function ChatSection({ phone }: { phone: string }) {
  // msgs em ordem cronológica (índice 0 = mais antiga carregada).
  const [msgs, setMsgs] = useState<ChatMessage[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [temMais, setTemMais] = useState(false)
  const [pausado, setPausado] = useState(false)
  const [texto, setTexto] = useState("")
  const [busy, setBusy] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)

  const scrollRef = useRef<HTMLDivElement>(null)
  const seen = useRef<Set<string>>(new Set())

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [])

  // Carga inicial + troca de cliente.
  useEffect(() => {
    let active = true
    seen.current = new Set()
    setMsgs([])
    setCursor(null)
    setTemMais(false)
    Promise.all([api.chatMessages(phone, PAGE), api.chatStatus(phone)])
      .then(([t, s]) => {
        if (!active) return
        const crono = [...t.mensagens].reverse() // Omni vem desc -> cronológico
        crono.forEach((m) => seen.current.add(m.id))
        setMsgs(crono)
        setCursor(t.cursor)
        setTemMais(t.tem_mais)
        setPausado(s.pausado)
        requestAnimationFrame(scrollToBottom)
      })
      .catch(() => active && setMsgs([]))
    return () => {
      active = false
    }
  }, [phone, scrollToBottom])

  // Auto-refresh: novas mensagens (append) + status, preservando as páginas carregadas.
  useEffect(() => {
    const id = setInterval(() => {
      Promise.all([api.chatMessages(phone, PAGE), api.chatStatus(phone)])
        .then(([t, s]) => {
          setPausado(s.pausado)
          const novas = [...t.mensagens].reverse().filter((m) => !seen.current.has(m.id))
          if (novas.length) {
            novas.forEach((m) => seen.current.add(m.id))
            setMsgs((prev) => [...prev, ...novas])
            requestAnimationFrame(scrollToBottom)
          }
        })
        .catch(() => {})
    }, POLL_MS)
    return () => clearInterval(id)
  }, [phone, scrollToBottom])

  async function mostrarMais() {
    if (!cursor) return
    setLoadingMore(true)
    const el = scrollRef.current
    const antes = el?.scrollHeight ?? 0
    try {
      const t = await api.chatMessages(phone, PAGE, cursor)
      const crono = [...t.mensagens].reverse().filter((m) => !seen.current.has(m.id))
      crono.forEach((m) => seen.current.add(m.id))
      setMsgs((prev) => [...crono, ...prev]) // prepend (mais antigas no topo)
      setCursor(t.cursor)
      setTemMais(t.tem_mais)
      requestAnimationFrame(() => {
        const e = scrollRef.current
        if (e) e.scrollTop = e.scrollHeight - antes // preserva a posição
      })
    } finally {
      setLoadingMore(false)
    }
  }

  async function toggleControle() {
    setBusy(true)
    try {
      const s = pausado ? await api.chatRelease(phone) : await api.chatTakeover(phone)
      setPausado(s.pausado)
      toast.success(s.pausado ? "Você assumiu o atendimento" : "Atendimento devolvido à IA")
    } catch {
      toast.error("Não foi possível alterar o controle")
    } finally {
      setBusy(false)
    }
  }

  async function enviar() {
    const t = texto.trim()
    if (!t) return
    setBusy(true)
    try {
      await api.chatSend(phone, t)
      setTexto("")
      // o auto-refresh traz a mensagem enviada; força um refresh imediato
      const r = await api.chatMessages(phone, PAGE)
      const novas = [...r.mensagens].reverse().filter((m) => !seen.current.has(m.id))
      novas.forEach((m) => seen.current.add(m.id))
      if (novas.length) setMsgs((prev) => [...prev, ...novas])
      requestAnimationFrame(scrollToBottom)
    } catch {
      toast.error("Não foi possível enviar a mensagem")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-[32rem] flex-col rounded-lg border">
      <div className="flex items-center justify-between gap-2 border-b px-4 py-2">
        <Badge variant={pausado ? "destructive" : "secondary"}>
          {pausado ? "Você está no controle" : "IA ativa"}
        </Badge>
        <Button size="sm" variant="outline" disabled={busy} onClick={toggleControle}>
          {pausado ? (
            <>
              <BotMessageSquare /> Devolver à IA
            </>
          ) : (
            <>
              <Hand /> Assumir controle
            </>
          )}
        </Button>
      </div>

      <div ref={scrollRef} className="flex-1 space-y-2 overflow-y-auto bg-muted/20 p-4">
        {temMais && (
          <div className="flex justify-center">
            <Button size="sm" variant="ghost" disabled={loadingMore} onClick={mostrarMais}>
              <ChevronUp /> {loadingMore ? "Carregando…" : "Mostrar mais"}
            </Button>
          </div>
        )}
        {msgs.length === 0 && (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Sem mensagens nesta conversa.
          </p>
        )}
        {msgs.map((m) => (
          <div
            key={m.id}
            className={cn("flex", m.do_cliente ? "justify-start" : "justify-end")}
          >
            <div
              className={cn(
                "max-w-[78%] rounded-lg px-3 py-1.5 text-sm whitespace-pre-wrap",
                m.do_cliente
                  ? "bg-background border"
                  : "bg-primary text-primary-foreground",
              )}
            >
              {m.texto}
              <span
                className={cn(
                  "mt-0.5 block text-[10px]",
                  m.do_cliente ? "text-muted-foreground" : "text-primary-foreground/70",
                )}
              >
                {hora(m.em)}
              </span>
            </div>
          </div>
        ))}
      </div>

      <div className="border-t p-2">
        {pausado ? (
          <div className="flex gap-2">
            <Input
              value={texto}
              onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && enviar()}
              placeholder="Responder ao cliente…"
              disabled={busy}
            />
            <Button onClick={enviar} disabled={busy || !texto.trim()}>
              <Send /> Enviar
            </Button>
          </div>
        ) : (
          <p className="px-2 py-1.5 text-center text-xs text-muted-foreground">
            A IA está respondendo. Assuma o controle para digitar.
          </p>
        )}
      </div>
    </div>
  )
}
