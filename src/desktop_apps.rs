use anyhow::{bail, Context, Result};
use schemars::JsonSchema;
use serde::Serialize;
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
    time::Duration,
};

#[derive(Debug, Clone, Serialize, JsonSchema)]
pub(crate) struct DesktopApp {
    pub desktop_id: String,
    pub name: String,
    pub app_id: String,
    pub startup_wm_class: Option<String>,
    pub path: String,
}

fn parse(id: String, path: &Path, source: &str) -> Option<DesktopApp> {
    let mut group = false;
    let mut fields = BTreeMap::new();
    for line in source.lines().map(str::trim) {
        if line.starts_with('[') {
            group = line == "[Desktop Entry]";
        } else if group && !line.starts_with('#') {
            if let Some((key, value)) = line.split_once('=') {
                fields.insert(key, value);
            }
        }
    }
    if fields.get("Hidden") == Some(&"true") || fields.get("Type") != Some(&"Application") {
        return None;
    }
    Some(DesktopApp {
        app_id: id.trim_end_matches(".desktop").to_string(),
        desktop_id: id,
        name: fields.get("Name")?.to_string(),
        startup_wm_class: fields.get("StartupWMClass").map(|s| s.to_string()),
        path: path.to_string_lossy().into_owned(),
    })
}

fn scan(root: &Path, dir: &Path, entries: &mut BTreeMap<String, Option<DesktopApp>>) {
    let Ok(children) = fs::read_dir(dir) else {
        return;
    };
    for entry in children.flatten() {
        let path = entry.path();
        // Do not follow directory symlinks or recurse outside the XDG root.
        if entry.file_type().is_ok_and(|t| t.is_dir()) {
            scan(root, &path, entries);
        } else if path.extension().is_some_and(|e| e == "desktop") {
            let Ok(relative) = path.strip_prefix(root) else {
                continue;
            };
            let id = relative.to_string_lossy().replace('/', "-");
            if entries.contains_key(&id) {
                continue;
            }
            if let Ok(text) = fs::read_to_string(&path) {
                entries.insert(id.clone(), parse(id, &path, &text));
            }
        }
    }
}

pub(crate) fn list() -> Vec<DesktopApp> {
    let data_home = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(std::env::var_os("HOME").unwrap_or_default()).join(".local/share")
        });
    let dirs = std::env::var("XDG_DATA_DIRS")
        .unwrap_or_else(|_| "/usr/local/share:/usr/share".to_string());
    let mut entries = BTreeMap::new();
    for base in std::iter::once(data_home)
        .chain(dirs.split(':').filter(|s| !s.is_empty()).map(PathBuf::from))
    {
        let root = base.join("applications");
        scan(&root, &root, &mut entries);
    }
    entries.into_values().flatten().collect()
}

pub(crate) async fn launch(id: &str) -> Result<DesktopApp> {
    let app = list()
        .into_iter()
        .find(|app| app.desktop_id == id || app.app_id == id)
        .context("unknown desktop_id; use list_desktop_apps")?;
    let status = tokio::time::timeout(
        Duration::from_secs(10),
        tokio::process::Command::new("gio")
            .arg("launch")
            .arg(&app.path)
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .kill_on_drop(true)
            .status(),
    )
    .await??;
    if !status.success() {
        bail!("gio launch failed with {status}");
    }
    Ok(app)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn desktop_group_and_hidden_override_are_respected() {
        let source = "[Desktop Entry]\nType=Application\nName=测试\nStartupWMClass=Probe\n[Desktop Action Other]\nName=Wrong\n";
        let app = parse("test.desktop".into(), Path::new("/test.desktop"), source).unwrap();
        assert_eq!(app.name, "测试");
        assert_eq!(app.app_id, "test");
        assert_eq!(app.startup_wm_class.as_deref(), Some("Probe"));
        assert!(parse(
            "test.desktop".into(),
            Path::new("/test.desktop"),
            &format!("{source}\n[Desktop Entry]\nHidden=true")
        )
        .is_none());
    }
}
