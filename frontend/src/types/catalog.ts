export interface Provider {
  id: number
  name: string
  adapter_key: string
  base_url: string
  request_config: { timeout_seconds: number; poll_interval_seconds: number }
  is_active: boolean
  has_credentials: boolean
}

export interface ImageCapabilities {
  sizes: string[]
  qualities: string[]
  tiers: string[]
  series: string[]
  backgrounds: string[]
  output_formats: string[]
  max_reference_images: number
  supports_mask: boolean
  defaults: Record<string, string>
}

export interface ImageProfile extends Omit<ImageCapabilities, 'defaults' | 'max_reference_images' | 'supports_mask'> {
  id: string
  family: string
  max_reference_images: number | null
}

export interface ModelPrice {
  id?: number
  variant: Record<string, string>
  sale_unit: 'image'
  sale_unit_price: string
  cost_unit: 'image'
  cost_unit_price: string
  cost_currency: 'CNY' | 'USD'
}

export interface ManagedModel {
  id: number
  public_id: string
  display_name: string
  media_type: 'image'
  provider_id: number
  upstream_model_id: string
  capabilities: ImageCapabilities
  pricing_dimensions: string[]
  prices: ModelPrice[]
  is_active: boolean
}
