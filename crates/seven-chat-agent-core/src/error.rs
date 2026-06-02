use thiserror::Error;

pub type Result<T> = std::result::Result<T, Error>;

#[derive(Debug, Error)]
pub enum Error {
    #[error("database error: {0}")]
    Db(#[from] sqlx::Error),

    #[error("migration error: {0}")]
    Migrate(#[from] sqlx::migrate::MigrateError),

    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),

    #[error("io error: {0}")]
    Io(#[from] std::io::Error),

    #[error("not found: {0}")]
    NotFound(String),

    #[error("invalid request: {0}")]
    BadRequest(String),

    #[error("provider error: {0}")]
    Provider(String),

    #[error("agent error: {0}")]
    Agent(String),

    #[error("config error: {0}")]
    Config(String),

    #[error("unauthorized: {0}")]
    Unauthorized(String),

    #[error("other: {0}")]
    Other(#[from] anyhow::Error),
}

impl Error {
    pub fn unauthorized<S: Into<String>>(s: S) -> Self {
        Self::Unauthorized(s.into())
    }
    pub fn provider<S: Into<String>>(s: S) -> Self {
        Self::Provider(s.into())
    }
    pub fn agent<S: Into<String>>(s: S) -> Self {
        Self::Agent(s.into())
    }
    pub fn not_found<S: Into<String>>(s: S) -> Self {
        Self::NotFound(s.into())
    }
    pub fn bad_request<S: Into<String>>(s: S) -> Self {
        Self::BadRequest(s.into())
    }
}
