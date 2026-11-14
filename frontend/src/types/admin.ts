export interface AdminUserRef {
  id: number
  email: string
  available?: string
}

export interface AdminLastAction {
  action: string
  actor_email: string
  created_at: string
}

export interface AdminTaskRow {
  id: string
  user: AdminUserRef
  model: string
  media_type: 'image' | 'video'
  status: string
  billing_status: string
  frozen_amount: string
  created: number
  updated: number
  waiting_seconds: number
  idle_seconds: number
  upstream_status: string | null
  has_upstream_id: boolean
  has_ready_result: boolean
  review_required: boolean
  resolution: string | null
  allowed_actions: string[]
  last_action: AdminLastAction | null
}

export interface AdminTextRow {
  id: string
  user: AdminUserRef
  model: string
  endpoint: string
  status: string
  created: number
  updated: number
  waiting_seconds: number
  idle_seconds: number
  charge_amount: string | null
  error_message: string | null
  has_late_usage: boolean
  late_usage_at: string | null
  resolution: string | null
  allowed_actions: string[]
  last_action: AdminLastAction | null
}

export interface AdminExceptionSummary {
  tasks: {
    submission_unknown: number
    stuck_queued: number
    stuck_submitting: number
    stuck_processing: number
    stuck_transferring: number
    review_required: number
  }
  text_calls: {
    usage_unknown: number
    stuck_processing: number
    late_usage: number
  }
  oldest_waiting_seconds: number
}

export interface AdminAuditRow {
  id: number
  actor: AdminUserRef
  action: string
  target_type: string
  target_id: string
  amount: string | null
  reason: string
  credit_entry_id: number | null
  created_at: string
}

export interface AdminAuditDetail extends AdminAuditRow {
  before_snapshot: Record<string, unknown>
  after_snapshot: Record<string, unknown>
}
