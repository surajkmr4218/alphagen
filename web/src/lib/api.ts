import { useAuth } from "@clerk/react";
import { useQuery } from "@tanstack/react-query";

const BASE = import.meta.env.VITE_API_BASE_URL as string;

// Typed API failure carrying the parsed body so handlers read structured details
export class ApiError extends Error {
  status: number;
  body: unknown;
  constructor(status: number, body: unknown) {
    super(`${status} ${typeof body === "string" ? body : JSON.stringify(body)}`);
    this.status = status;
    this.body = body;
  }
}

export function useApi() {
  const { getToken } = useAuth();
  return async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = await getToken();   // re-mint per call; tokens are ~60s
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
        ...(init.headers ?? {})
        },
    });
    if (!res.ok) {
      const text = await res.text();
      let body: unknown = text;
      try { body = JSON.parse(text); } catch { /* non-JSON error body stays a string */ }
      throw new ApiError(res.status, body);
    }
    return res.json() as Promise<T>;
  };
}

export interface Me {
  clerk_user_id: string;
  role: "owner" | "public";
  execution_enabled: boolean;
  robinhood_linked: boolean;
}

export function useMe() {
  const api = useApi();
  return useQuery({ 
    queryKey: ["me"], 
    queryFn: () => api<Me>("/me") 
  });  
}

/*
* Dashboard payloads - every trail field can be null.
*/

export interface DecisionSummary {
  decision_id: string;
  ticker: string;
  passed: boolean;
  human_decision: "pending" | "approved" | "rejected" | "running" | "failed";
  created_at: string;
  size_usd?: number | null;            
  order_status?: string | null;
  entry?: number | null;             
  current_price?: number | null;
  unrealized_pnl_pct?: number | null;   
}

export interface AccountSnapshot {
  total_equity: number | null;
  cash: number | null;
  buying_power: number | null;
  stale: boolean;                      
}

export interface NewRunResponse {
  decision_id: string;
  ticker: string;
  status: "running";
}

export interface RunStatus {
  decision_id: string;
  status: "running" | "failed" | "pending-approval" | "complete";
  reason?: string | null;
  human_decision?: string;
}

export interface Hypothesis {
  direction?: string;
  order_type?: string;
  limit_price?: number | null;
  size_usd?: number;
  confidence?: number;
  rationale?: string;
}

export interface GuardrailResult {
  rule: string;
  passed: boolean;
  severity: string;
  reason: string;
}

export interface Trail {
  ticker: string;
  triggering_diff: { 
    section: string; 
    semantic_drift: number; 
    added: string[]; 
    removed: string[] 
  } | null;
  cited_passages: { 
    accession: string; 
    section: string; 
    text: string 
  }[] | null;
  signals: Record<string, unknown> | null;
  hypothesis: Hypothesis | null;
  critic_verdict: { 
    verdict?: string; 
    reasons?: string[] 
  } | null;
  guardrail: { 
    passed?: boolean; 
    results?: GuardrailResult[] 
  } | null;
  order: { 
    status: string; 
    reason?: string | null; 
    quantity?: number | null; 
    limit_price?: number | null; 
    broker_order_id?: string | null 
  } | null;
}

export interface QueueItem {
  decision_id: string;
  ticker: string;
  hypothesis: Hypothesis;
  critic_verdict: { 
    verdict?: string; 
    reasons?: string[] 
  } | null;
  guardrail: { passed?: boolean } | null;
}

export interface EvalSummary {
  n_resolved: number;
  n_pending: number;
  hit_rate: number | null;
  avg_return: number | null;
  avg_excess_vs_spy: number | null;
}

