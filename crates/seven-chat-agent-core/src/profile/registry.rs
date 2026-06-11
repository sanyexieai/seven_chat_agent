use std::sync::OnceLock;

use crate::profile::types::ProfileFrameworkCatalog;

static BUILTIN: OnceLock<Vec<ProfileFrameworkCatalog>> = OnceLock::new();

pub fn list_frameworks() -> &'static [ProfileFrameworkCatalog] {
    BUILTIN.get_or_init(|| {
        vec![
            load_embedded(include_str!("catalog/mbti_16.json")),
            load_embedded(include_str!("catalog/agent_24.json")),
        ]
    })
}

pub fn get_framework(id: &str) -> Option<&'static ProfileFrameworkCatalog> {
    list_frameworks().iter().find(|f| f.id == id)
}

pub fn find_framework<'a>(
    catalogs: &'a [ProfileFrameworkCatalog],
    id: &str,
) -> Option<&'a ProfileFrameworkCatalog> {
    catalogs.iter().find(|f| f.id == id)
}

pub fn frameworks_version(catalogs: &[ProfileFrameworkCatalog]) -> String {
    catalogs
        .iter()
        .map(|f| format!("{}@{}", f.id, f.version))
        .collect::<Vec<_>>()
        .join("|")
}

pub fn find_type<'a>(
    framework: &'a ProfileFrameworkCatalog,
    type_code: &str,
) -> Option<&'a crate::profile::types::ProfileTypeDefinition> {
    framework
        .types
        .iter()
        .find(|t| t.type_code.eq_ignore_ascii_case(type_code))
}

fn load_embedded(raw: &str) -> ProfileFrameworkCatalog {
    serde_json::from_str(raw).expect("builtin profile framework catalog")
}
