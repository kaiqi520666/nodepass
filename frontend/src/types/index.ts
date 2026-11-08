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
  unit: 'image' | 'video' | 'second'
  unit_price: string
}

export interface PublicModel {
  id: string
  name: string
  media_type: 'image' | 'video'
  capabilities: Record<string, string[] | number[] | string | number | boolean>
  prices: PublicPrice[]
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
