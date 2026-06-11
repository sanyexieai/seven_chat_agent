mod capability;
mod group_memory;
mod member_group_note;
mod derive;
mod extensions;
mod infer;
mod registry;
pub mod scheduling;
pub mod types;

pub use extensions::{
    allowed_extension_keys, validate_framework_extensions_schema, validate_profile_extensions,
};
pub use capability::{
    archive_excess_group_capability_raw, format_group_capability_excerpt,
    member_recent_capability_hints, record_group_turn_capabilities,
    MEMORY_KIND_GROUP_CAPABILITY, MAX_GROUP_CAPABILITY_RAW_PER_GROUP, SCOPE_GROUP,
};
pub use member_group_note::record_member_group_note;
pub use group_memory::{
    append_group_public_baseline_prompt, consensus_to_markdown, curate_group_public_from_turn,
    fetch_group_public_baseline, fetch_group_public_judge_excerpt, fetch_group_public_relevant,
    fetch_group_public_relevant_with_embedding,
    finalize_group_turn_memory, format_group_public_judge_excerpt, group_public_expires_at,
    merge_coordinator_plan_into_group_public, parse_assignments_from_coordinator_plan,
    refresh_group_public_mid_turn,
    format_group_public_baseline, format_group_public_relevant, heuristic_curate_group_public,
    upsert_group_public_latest, GroupPublicAssignment, GroupPublicConsensus, GroupPublicFailure,
    GROUP_PUBLIC_TITLE_LATEST,
};
pub use derive::{
    build_member_roster, build_member_roster_with_hints, build_persona_block,
    build_persona_block_with, derive_axes,
    derive_routing_hints, derive_routing_hints_with, framework_labels, framework_labels_with,
    normalize_profile_for_save, normalize_profile_for_save_with, resolve_effective_profile,
    resolve_effective_profile_with, derive_axes_with,
};
pub use infer::{infer_member_profile, ProfileInferResult};
pub use scheduling::{merge_task_assignments, pick_coordinator, self_nomination_candidates};
pub use registry::{find_framework, find_type, frameworks_version, get_framework, list_frameworks};
pub use types::{
    EffectiveMemberProfile, ExtensionFieldSchema, ExtensionsSchema, FrameworkBinding,
    MemberProfile, MemberProfileOverlay, MemberProfileSummary, ProfileAxes,
    ProfileFrameworkCatalog, ProfileTypeDefinition,
};
