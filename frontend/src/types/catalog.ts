export interface Provider {
  id: number
  name: string
  adapter_key: string
  base_url: string
  request_config: { timeout_seconds: number; poll_interval_seconds: number; task_timeout_seconds: number }
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
  max_reference_images: number
}

export interface ModelPrice {
  id?: number
  variant: Record<string, string>
  sale_unit: 'image' | 'video' | 'second'
  sale_unit_price: string
  cost_unit: 'image' | 'video' | 'second'
  cost_unit_price: string
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

export interface VideoCapabilities {
  family: string
  version: string
  resolutions: string[]
  aspect_ratios: string[]
  min_seconds: string
  max_seconds: string
  max_reference_images: number
  max_reference_videos: number
  max_reference_audios: number
  supports_first_frame: boolean
  supports_last_frame: boolean
  defaults: Record<string, string>
}

export interface ManagedVideoModel extends Omit<ManagedModel, 'media_type' | 'capabilities'> {
  media_type: 'video'
  capabilities: VideoCapabilities
}

export interface TokenPrice {
  input_price: string
  output_price: string
  cache_read_price: string
  cost_multiplier: string
  sale_multiplier: string
  long_context_threshold: number
  long_context_input_multiplier: string
  long_context_output_multiplier: string
}

export interface ManagedTextModel extends Omit<ManagedModel, 'media_type' | 'capabilities'> {
  media_type: 'text'
  capabilities: { family: string; input_modalities: string[] }
  token_price: TokenPrice
}

export type ManagedCatalogModel = ManagedModel | ManagedVideoModel | ManagedTextModel
