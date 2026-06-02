//! 请求级 tenant / user 上下文（dispatcher / provider / 工作区解析用）。

tokio::task_local! {
    pub static ACTIVE_TENANT: String;
    pub static ACTIVE_USER: Option<String>;
}

/// 当前异步任务绑定的 tenant；无则回退 `default_tenant`。
pub fn active_tenant_or(default_tenant: &str) -> String {
    ACTIVE_TENANT
        .try_with(|t| t.clone())
        .unwrap_or_else(|_| default_tenant.to_string())
}

/// 当前异步任务绑定的登录用户（用于工作区 cwd）。
pub fn active_user_id() -> Option<String> {
    ACTIVE_USER
        .try_with(|u| u.clone())
        .ok()
        .flatten()
        .filter(|s| !s.is_empty())
}

pub async fn with_active_tenant<F, Fut, T>(tenant_id: &str, f: F) -> T
where
    F: FnOnce() -> Fut,
    Fut: std::future::Future<Output = T>,
{
    ACTIVE_TENANT.scope(tenant_id.to_string(), f()).await
}

pub async fn with_active_scope<F, Fut, T>(
    tenant_id: &str,
    user_id: Option<&str>,
    f: F,
) -> T
where
    F: FnOnce() -> Fut,
    Fut: std::future::Future<Output = T>,
{
    let uid = user_id
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_string);
    ACTIVE_USER
        .scope(uid, ACTIVE_TENANT.scope(tenant_id.to_string(), f()))
        .await
}
