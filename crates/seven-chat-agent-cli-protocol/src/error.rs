use thiserror::Error;

#[derive(Debug, Error)]
pub enum CliError {
    #[error("{0}")]
    Agent(String),
    #[error("{0}")]
    BadRequest(String),
}

impl CliError {
    pub fn agent(msg: impl Into<String>) -> Self {
        Self::Agent(msg.into())
    }

    pub fn bad_request(msg: impl Into<String>) -> Self {
        Self::BadRequest(msg.into())
    }
}

pub type Result<T> = std::result::Result<T, CliError>;
