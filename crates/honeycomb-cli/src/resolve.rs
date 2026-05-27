//! 可执行文件路径解析（与 honeycomb-server 的 PATH 解耦）。

pub fn path_if_executable(p: &std::path::Path) -> Option<String> {
    p.is_file().then(|| p.to_string_lossy().into_owned())
}

pub fn cli_command_works(cmd: &str) -> bool {
    std::process::Command::new(cmd)
        .arg("--version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

pub fn cli_command_help_works(cmd: &str) -> bool {
    std::process::Command::new(cmd)
        .arg("--help")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}
