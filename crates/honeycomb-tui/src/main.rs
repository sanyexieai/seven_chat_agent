use clap::{Parser, Subcommand};

mod api;
mod app;
mod io;

#[derive(Parser, Debug)]
#[command(version, about = "honeycomb TUI", long_about = None)]
struct Cli {
    /// HTTP base, e.g. http://127.0.0.1:18737
    #[arg(long, env = "HONEYCOMB_SERVER", default_value = "http://127.0.0.1:18737")]
    server: String,
    #[command(subcommand)]
    cmd: Option<Cmd>,
}

#[derive(Debug, Subcommand)]
enum Cmd {
    Export {
        #[arg(long, default_value = "honeycomb-config.json")]
        out: String,
    },
    Import {
        path: String,
    },
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stderr)
        .init();

    let cli = Cli::parse();
    match cli.cmd {
        Some(Cmd::Export { out }) => io::export_config(&cli.server, &out).await,
        Some(Cmd::Import { path }) => io::import_config(&cli.server, &path).await,
        None => app::run(&cli.server).await,
    }
}
