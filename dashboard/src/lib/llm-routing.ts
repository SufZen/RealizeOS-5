/**
 * The LLM routing settings (`GET/PUT /api/llm/routing`): the shapes the
 * server returns, and the pure helpers the settings form and the setup
 * wizard use to read and write them.
 */
import { api } from '@/lib/api'

export const TIERS = ['fast', 'standard', 'deep'] as const
export type Tier = (typeof TIERS)[number]

/** One model a provider offers (`ModelInfo`); only the fields the form uses. */
export interface ModelInfo {
  model_id: string
  display_name?: string
  tier?: string
}

export interface RoutingProvider {
  name: string
  available: boolean
  models: ModelInfo[]
  /** Model id → why it stopped answering ("not found" means retired). */
  model_errors?: Record<string, string>
}

export interface RoutingRule {
  tier?: string
  provider?: string | null
  /** The resolved model id. */
  model: string
  description: string
}

export interface TierInfo {
  provider: string | null
  model: string | null
  /** `env` when LLM_MODEL_<TIER> is set, else `default`. */
  source: 'env' | 'default'
}

/** The values as configured (empty string / list = unset). Pre-fills the form. */
export interface RoutingSettings {
  primary: string
  tiers: Record<Tier, string>
  fallback: string[]
}

export interface RoutingData {
  routing_rules: Record<string, RoutingRule>
  tiers: Record<Tier, TierInfo>
  providers: RoutingProvider[]
  /** Effective primary: the first available provider in the chain. */
  primary: string | null
  fallback: string[]
  settings: RoutingSettings
}

/** Body of `PUT /api/llm/routing`. Every field is optional; only sent ones change. */
export interface RoutingUpdate {
  primary?: string
  tiers?: Partial<Record<Tier, string>>
  fallback?: string[]
}

export interface RoutingForm {
  primary: string
  tiers: Record<Tier, string>
  /** Comma-separated provider names, in order. */
  fallback: string
}

/** Names the server accepts, folded to the registry's name for the same provider. */
const ALIASES: Record<string, string> = {
  anthropic: 'claude',
  google: 'gemini',
  google_ai: 'gemini',
}

/** The routing name for a provider as written (`anthropic` → `claude`). */
export function canonicalProvider(name: string | null | undefined): string {
  const lower = (name ?? '').trim().toLowerCase()
  return ALIASES[lower] ?? lower
}

/** A setup-wizard provider id as the routing API names it. */
export function routingNameForSetupId(id: string): string {
  return canonicalProvider(id)
}

export function parseFallback(text: string): string[] {
  return text
    .split(',')
    .map((p) => p.trim().toLowerCase())
    .filter(Boolean)
}

/** The form's starting values, from the settings as configured. */
export function formFromSettings(settings: RoutingSettings | undefined): RoutingForm {
  return {
    primary: canonicalProvider(settings?.primary),
    tiers: {
      fast: settings?.tiers?.fast ?? '',
      standard: settings?.tiers?.standard ?? '',
      deep: settings?.tiers?.deep ?? '',
    },
    fallback: (settings?.fallback ?? []).join(', '),
  }
}

/**
 * What to send: only the fields that differ from the saved settings, so
 * saving never pins a model the person left on its default. An emptied
 * field is sent as "" (or []) and unsets it. Null when nothing changed.
 */
export function routingUpdate(
  form: RoutingForm,
  settings: RoutingSettings | undefined,
): RoutingUpdate | null {
  const saved = formFromSettings(settings)
  const update: RoutingUpdate = {}
  if (form.primary !== saved.primary) update.primary = form.primary
  const tiers: Partial<Record<Tier, string>> = {}
  for (const tier of TIERS) {
    const value = form.tiers[tier].trim()
    if (value !== saved.tiers[tier].trim()) tiers[tier] = value
  }
  if (Object.keys(tiers).length) update.tiers = tiers
  const fallback = parseFallback(form.fallback)
  if (fallback.join(',') !== parseFallback(saved.fallback).join(',')) update.fallback = fallback
  return Object.keys(update).length ? update : null
}

/** Model ids to suggest, from providers that answer; each once, in provider order. */
export function modelSuggestions(providers: RoutingProvider[]): string[] {
  const seen = new Set<string>()
  for (const p of providers) {
    if (!p.available) continue
    for (const m of p.models ?? []) if (m?.model_id) seen.add(m.model_id)
  }
  return [...seen]
}

/** Configured models that stopped answering. */
export function deadModels(providers: RoutingProvider[]): { provider: string; model: string }[] {
  return providers.flatMap((p) =>
    Object.keys(p.model_errors ?? {}).map((model) => ({ provider: p.name, model })),
  )
}

/** Save routing settings; resolves to the rebuilt routing payload. */
export function saveRouting(
  update: RoutingUpdate,
  put: <T>(path: string, body?: unknown) => Promise<T> = api.put,
): Promise<RoutingData> {
  return put<RoutingData>('/llm/routing', update)
}
