use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::{Manager, RunEvent};

struct BackendProcess(Mutex<Option<Child>>);

fn spawn_backend() -> Option<Child> {
    // CARGO_MANIFEST_DIR is frontend/src-tauri at compile time.
    // Two parent() calls reach the project root where `backend/` lives.
    let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent());

    let Some(root) = project_root else {
        eprintln!("[CreatorCutAI] could not resolve project root — backend not started");
        return None;
    };

    match Command::new("uv")
        .args([
            "run",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ])
        .current_dir(root)
        .spawn()
    {
        Ok(child) => {
            println!("[CreatorCutAI] backend started (pid {})", child.id());
            Some(child)
        }
        Err(e) => {
            eprintln!("[CreatorCutAI] failed to start backend: {e}");
            None
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let child = spawn_backend();
            app.manage(BackendProcess(Mutex::new(child)));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building CreatorCutAI")
        .run(|app_handle, event| {
            if let RunEvent::ExitRequested { .. } = event {
                let state = app_handle.state::<BackendProcess>();
                let child = {
                    let mut guard = state.0.lock().unwrap_or_else(|e| e.into_inner());
                    guard.take()
                };
                if let Some(mut child) = child {
                    let _ = child.kill();
                    let _ = child.wait();
                    println!("[CreatorCutAI] backend stopped");
                }
            }
        });
}
