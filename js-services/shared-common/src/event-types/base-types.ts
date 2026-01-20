// Base event interface that all Amplitude events should extend
export interface BaseEventProperties {
  timestamp?: number;
  session_id?: string;
  user_id?: string;
  tenant_id?: string; // Added for multi-tenant support
}
