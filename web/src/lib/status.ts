import type { DecisionSummary } from "./api";
import type { Tone } from "../components/ui/Badge";

export interface StatusView {
  label: string;
  tone: Tone;
  glyph: "check" | "x" | "dot" | "none";
  pulse?: boolean;
}

/**
 * What to show for a decision row. "approved" records the human decision, but the
 * order can still be blocked or filled afterwards, so once an order row has a real
 * status we show what actually happened to it.
 */
export function statusView(d: DecisionSummary): StatusView {
  if (d.human_decision === "approved" && d.order_status && d.order_status !== "pending") {
    if (d.order_status === "filled") return { label: "Filled", tone: "up", glyph: "check" };
    if (d.order_status === "rejected") return { label: "Blocked", tone: "down", glyph: "x" };
    return { label: "Submitted", tone: "up", glyph: "dot", pulse: true }; // queued / confirmed / partial
  }
  switch (d.human_decision) {
    case "approved": return { label: "Approved", tone: "up", glyph: "check" };
    case "placing": return { label: "Placing", tone: "warn", glyph: "dot", pulse: true };
    case "running": return { label: "Running", tone: "warn", glyph: "dot", pulse: true };
    case "rejected": return { label: "Rejected", tone: "down", glyph: "x" };
    case "failed": return { label: "Failed", tone: "down", glyph: "x" };
    case "pending":
    default:
      return d.passed
        ? { label: "Needs your call", tone: "accent", glyph: "dot" }
        : { label: "Not proposed", tone: "neutral", glyph: "none" };
  }
}

export const TABS = ["queue", "approved", "rejected", "all"] as const;
export type Tab = (typeof TABS)[number];

export const inTab = (d: DecisionSummary, tab: Tab) =>
  tab === "all" ? true
  : tab === "queue" ? (d.human_decision === "pending" && d.passed) || d.human_decision === "running"
  : tab === "approved" ? d.human_decision === "approved" || d.human_decision === "placing"
  : d.human_decision === "rejected" || d.human_decision === "failed";

/** A decision is live while the pipeline runs or an approved order hasn't settled. */
export const isLive = (d: DecisionSummary | undefined) =>
  d != null &&
  (d.human_decision === "running" ||
    d.human_decision === "placing" ||
    (d.human_decision === "approved" &&
      d.order_status != null &&
      !["filled", "rejected"].includes(d.order_status)));
