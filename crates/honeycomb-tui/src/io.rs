use anyhow::Result;
use serde_json::Value;

pub async fn export_config(server: &str, out_path: &str) -> Result<()> {
    let base = server.trim_end_matches('/');
    let http = reqwest::Client::new();
    let friends: Value = http.get(format!("{base}/api/friends")).send().await?.json().await?;
    let groups: Value = http.get(format!("{base}/api/groups")).send().await?.json().await?;
    let providers: Value = http.get(format!("{base}/api/providers")).send().await?.json().await?;
    let provider_keys: Value = http
        .get(format!("{base}/api/provider_keys"))
        .send()
        .await?
        .json()
        .await?;
    let bundle = serde_json::json!({
        "friends": friends["friends"],
        "groups": groups["groups"],
        "providers": providers["providers"],
        "provider_keys_meta": provider_keys["provider_keys"],
    });
    tokio::fs::write(out_path, serde_json::to_vec_pretty(&bundle)?).await?;
    println!("exported {} bytes -> {out_path}", serde_json::to_vec(&bundle)?.len());
    Ok(())
}

pub async fn import_config(server: &str, path: &str) -> Result<()> {
    let base = server.trim_end_matches('/');
    let http = reqwest::Client::new();
    let bytes = tokio::fs::read(path).await?;
    let bundle: Value = serde_json::from_slice(&bytes)?;
    if let Some(arr) = bundle.get("friends").and_then(|v| v.as_array()) {
        for f in arr {
            let mut body = f.clone();
            if let Some(obj) = body.as_object_mut() {
                obj.remove("id");
                obj.remove("created_at");
                obj.remove("is_builtin");
            }
            let res = http
                .post(format!("{base}/api/friends"))
                .json(&body)
                .send()
                .await?;
            if !res.status().is_success() {
                eprintln!("friend import failed: {}", res.text().await.unwrap_or_default());
            }
        }
    }
    println!("import done");
    Ok(())
}
