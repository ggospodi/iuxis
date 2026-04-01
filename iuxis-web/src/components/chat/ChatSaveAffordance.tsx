/**
 * ChatSaveAffordance
 * Shown below an assistant message when save_signal is present.
 * Allows one-click save to knowledge base with optional category override.
 */

import { useState } from "react"

interface SaveSignal {
  text: string
  suggested_category: string
  source: string
}

interface ChatSaveAffordanceProps {
  saveSignal: SaveSignal
  projectId?: number
  onSaved?: (entryId: number) => void
  onDismiss?: () => void
}

const CATEGORIES = [
  "decision", "fact", "risk", "workflow_rule", "project_context",
  "metric", "context", "relationship", "compliance", "preference", "pattern"
]

export function ChatSaveAffordance({
  saveSignal,
  projectId,
  onSaved,
  onDismiss,
}: ChatSaveAffordanceProps) {
  const [category, setCategory] = useState(saveSignal.suggested_category || "fact")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [dismissed, setDismissed] = useState(false)

  if (dismissed) return null
  if (saved) {
    return (
      <div style={{
        background: "rgba(59, 130, 246, 0.08)",
        border: "1px solid rgba(59, 130, 246, 0.2)",
        borderRadius: "6px",
        padding: "8px 12px",
        marginTop: "8px",
        fontSize: "12px",
        color: "#3B82F6",
        display: "flex",
        alignItems: "center",
        gap: "6px"
      }}>
        ✅ Saved to knowledge base as <strong>{category}</strong>
      </div>
    )
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/chat/save-knowledge", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: saveSignal.text,
          category,
          source: "chat",
          project_id: projectId ?? null,
        }),
      })
      const data = await res.json()
      if (data.success) {
        setSaved(true)
        onSaved?.(data.entry_id)
      }
    } catch (e) {
      console.error("Save failed:", e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div style={{
      background: "rgba(139, 92, 246, 0.06)",
      border: "1px solid rgba(139, 92, 246, 0.18)",
      borderRadius: "6px",
      padding: "10px 12px",
      marginTop: "8px",
      fontSize: "12px",
    }}>
      <div style={{
        color: "#8B5CF6",
        fontWeight: 600,
        marginBottom: "8px",
        display: "flex",
        alignItems: "center",
        gap: "6px"
      }}>
        💾 This looks like a decision. Save to knowledge base?
      </div>

      {/* Preview text */}
      <div style={{
        color: "#9CA3AF",
        marginBottom: "10px",
        fontStyle: "italic",
        lineHeight: "1.4",
        overflow: "hidden",
        display: "-webkit-box",
        WebkitLineClamp: 2,
        WebkitBoxOrient: "vertical",
      }}>
        "{saveSignal.text.slice(0, 150)}{saveSignal.text.length > 150 ? "…" : ""}"
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        {/* Category selector */}
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          style={{
            background: "#1A1A2E",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "4px",
            color: "#E5E7EB",
            padding: "4px 8px",
            fontSize: "11px",
            cursor: "pointer",
          }}
        >
          {CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>{cat}</option>
          ))}
        </select>

        {/* Save button */}
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            background: saving ? "rgba(139, 92, 246, 0.3)" : "#8B5CF6",
            border: "none",
            borderRadius: "4px",
            color: "white",
            padding: "4px 12px",
            fontSize: "11px",
            fontWeight: 600,
            cursor: saving ? "not-allowed" : "pointer",
          }}
        >
          {saving ? "Saving…" : "Save"}
        </button>

        {/* Dismiss */}
        <button
          onClick={() => { setDismissed(true); onDismiss?.() }}
          style={{
            background: "transparent",
            border: "none",
            color: "#6B7280",
            fontSize: "11px",
            cursor: "pointer",
            padding: "4px 6px",
          }}
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
