export interface User {
  id: number
  email: string
  is_admin: boolean
  is_active: boolean
  created_at: string
  account: { available: string; frozen: string }
}

export interface PublicPrice {
  variant: Record<string, string>
  unit: 'image' | 'video' | 'second' | 'million_tokens'
  unit_price: string
}

export interface PublicModel {
  id: string
  name: string
  media_type: 'image' | 'video' | 'text'
  capabilities: Record<string, string[] | number[] | string | number | boolean>
  prices: PublicPrice[]
  token_prices?: { input_price: string; output_price: string; cache_read_price: string } | null
  long_context_threshold?: number | null
  long_context_token_prices?: { input_price: string; output_price: string; cache_read_price: string } | null
}

export interface ApiKey {
  id: number
  name: string
  key_prefix: string
  is_active: boolean
  created_at: string
  expires_at: string | null
  last_used_at: string | null
}
