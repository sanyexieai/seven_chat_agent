export type InitiativeLevel = "proactive" | "balanced" | "passive";
export type CoordinationLevel = "coordinator" | "contributor" | "none";

export interface RoutingHints {
  initiative?: InitiativeLevel;
  coordination?: CoordinationLevel;
  respond_to_mention?: boolean;
  self_nominate?: boolean | null;
  campaign_eligible?: boolean | null;
  fallback_pick_eligible?: boolean | null;
  peer_vote_eligible?: boolean;
}

export interface FrameworkBinding {
  id: string;
  type_code: string;
  source?: string;
  confidence?: number;
}

export interface MemberProfile {
  schema_version?: number;
  frameworks?: FrameworkBinding[];
  routing_hints?: RoutingHints;
  use_derived_routing?: boolean;
  extensions?: Record<string, unknown>;
}

export interface MemberProfileOverlay {
  routing_hints?: Partial<RoutingHints>;
  disabled_frameworks?: string[];
}

export interface MemberProfileSummary {
  friend_id: string;
  initiative: InitiativeLevel;
  coordination: CoordinationLevel;
  framework_labels?: string[];
}

export interface ProfileTypeDefinition {
  type_code: string;
  label_zh: string;
  default_routing_hints?: RoutingHints;
  prompt_snippet?: string;
}

export interface ProfileFrameworkCatalog {
  id: string;
  name: string;
  version: string;
  types: ProfileTypeDefinition[];
  extensions_schema?: ExtensionsSchema | null;
}

export interface ExtensionFieldSchema {
  type: string;
  enum?: unknown[];
  max_length?: number;
}

export interface ExtensionsSchema {
  properties?: Record<string, ExtensionFieldSchema>;
}
