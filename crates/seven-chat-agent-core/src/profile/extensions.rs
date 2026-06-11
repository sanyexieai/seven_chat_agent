use std::collections::{HashMap, HashSet};

use crate::profile::registry::find_framework;
use crate::profile::types::{ExtensionFieldSchema, ExtensionsSchema, MemberProfile, ProfileFrameworkCatalog};
use crate::{Error, Result};

/// 校验成员 profile.extensions 是否符合已绑定 framework 的 extensions_schema。
pub fn validate_profile_extensions(
    profile: &MemberProfile,
    catalogs: &[ProfileFrameworkCatalog],
) -> Result<()> {
    if profile.extensions.is_null() {
        return Ok(());
    }
    let Some(obj) = profile.extensions.as_object() else {
        return Err(Error::bad_request("extensions 必须是 JSON 对象"));
    };
    if obj.is_empty() {
        return Ok(());
    }

    let merged = merged_extensions_schema(profile, catalogs);
    if merged.properties.is_empty() {
        return Ok(());
    }

    for (key, value) in obj {
        let Some(spec) = merged.properties.get(key) else {
            return Err(Error::bad_request(format!(
                "extensions 含未声明字段「{key}」"
            )));
        };
        validate_extension_value(key, value, spec)?;
    }
    Ok(())
}

fn merged_extensions_schema(
    profile: &MemberProfile,
    catalogs: &[ProfileFrameworkCatalog],
) -> ExtensionsSchema {
    let mut properties: HashMap<String, ExtensionFieldSchema> = HashMap::new();
    for fb in &profile.frameworks {
        let Some(catalog) = find_framework(catalogs, &fb.id) else {
            continue;
        };
        let Some(schema) = catalog.extensions_schema.as_ref() else {
            continue;
        };
        for (k, v) in &schema.properties {
            properties.entry(k.clone()).or_insert_with(|| v.clone());
        }
    }
    ExtensionsSchema { properties }
}

fn validate_extension_value(
    key: &str,
    value: &serde_json::Value,
    spec: &ExtensionFieldSchema,
) -> Result<()> {
    let ok = match spec.r#type.as_str() {
        "string" => value.is_string(),
        "number" => value.is_number(),
        "boolean" => value.is_boolean(),
        "array" => value.is_array(),
        "object" => value.is_object(),
        _ => true,
    };
    if !ok {
        return Err(Error::bad_request(format!(
            "extensions.{key} 类型应为 {}",
            spec.r#type
        )));
    }
    if !spec.enum_values.is_empty() && !spec.enum_values.contains(value) {
        return Err(Error::bad_request(format!(
            "extensions.{key} 取值不在允许范围内"
        )));
    }
    if let Some(max) = spec.max_length {
        if let Some(s) = value.as_str() {
            if s.chars().count() > max {
                return Err(Error::bad_request(format!(
                    "extensions.{key} 长度不能超过 {max} 字符"
                )));
            }
        }
    }
    Ok(())
}

/// 校验自定义 framework catalog 内 extensions_schema 结构。
pub fn validate_framework_extensions_schema(catalog: &ProfileFrameworkCatalog) -> Result<()> {
    let Some(schema) = catalog.extensions_schema.as_ref() else {
        return Ok(());
    };
    let allowed_types = ["string", "number", "boolean", "array", "object"];
    for (key, spec) in &schema.properties {
        if key.trim().is_empty() {
            return Err(Error::bad_request("extensions_schema 含空字段名"));
        }
        if !allowed_types.contains(&spec.r#type.as_str()) {
            return Err(Error::bad_request(format!(
                "extensions_schema.{key} type 无效：{}",
                spec.r#type
            )));
        }
    }
    Ok(())
}

/// 合并多 framework 允许的 extensions 字段名（供前端提示）。
pub fn allowed_extension_keys(
    profile: &MemberProfile,
    catalogs: &[ProfileFrameworkCatalog],
) -> Vec<String> {
    let mut keys: HashSet<String> = HashSet::new();
    for fb in &profile.frameworks {
        let Some(catalog) = find_framework(catalogs, &fb.id) else {
            continue;
        };
        let Some(schema) = catalog.extensions_schema.as_ref() else {
            continue;
        };
        keys.extend(schema.properties.keys().cloned());
    }
    let mut out: Vec<_> = keys.into_iter().collect();
    out.sort();
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::profile::types::{FrameworkBinding, ProfileTypeDefinition};

    fn catalog_with_schema() -> ProfileFrameworkCatalog {
        ProfileFrameworkCatalog {
            id: "custom".into(),
            name: "Custom".into(),
            version: "1".into(),
            types: vec![ProfileTypeDefinition {
                type_code: "A".into(),
                label_zh: "A".into(),
                axis_defaults: Default::default(),
                default_routing_hints: Default::default(),
                prompt_snippet: String::new(),
            }],
            extensions_schema: Some(ExtensionsSchema {
                properties: HashMap::from([(
                    "team_role".into(),
                    ExtensionFieldSchema {
                        r#type: "string".into(),
                        enum_values: vec![
                            serde_json::json!("lead"),
                            serde_json::json!("support"),
                        ],
                        max_length: None,
                    },
                )]),
            }),
        }
    }

    #[test]
    fn accepts_valid_extension() {
        let catalogs = vec![catalog_with_schema()];
        let profile = MemberProfile {
            frameworks: vec![FrameworkBinding {
                id: "custom".into(),
                type_code: "A".into(),
                source: "test".into(),
                confidence: 1.0,
            }],
            extensions: serde_json::json!({ "team_role": "lead" }),
            ..Default::default()
        };
        assert!(validate_profile_extensions(&profile, &catalogs).is_ok());
    }

    #[test]
    fn rejects_unknown_key() {
        let catalogs = vec![catalog_with_schema()];
        let profile = MemberProfile {
            frameworks: vec![FrameworkBinding {
                id: "custom".into(),
                type_code: "A".into(),
                source: "test".into(),
                confidence: 1.0,
            }],
            extensions: serde_json::json!({ "unknown": 1 }),
            ..Default::default()
        };
        assert!(validate_profile_extensions(&profile, &catalogs).is_err());
    }

    #[test]
    fn rejects_invalid_enum() {
        let catalogs = vec![catalog_with_schema()];
        let profile = MemberProfile {
            frameworks: vec![FrameworkBinding {
                id: "custom".into(),
                type_code: "A".into(),
                source: "test".into(),
                confidence: 1.0,
            }],
            extensions: serde_json::json!({ "team_role": "invalid" }),
            ..Default::default()
        };
        assert!(validate_profile_extensions(&profile, &catalogs).is_err());
    }
}
