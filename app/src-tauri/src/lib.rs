mod backend;

use backend::Backend;
use std::sync::Arc;
use tauri::{Emitter, Manager, RunEvent, WindowEvent};

struct AppState {
    backend: Arc<Backend>,
}

#[tauri::command]
fn backend_start(state: tauri::State<AppState>) -> Result<u16, String> {
    state.backend.start()
}

#[tauri::command]
fn backend_restart(state: tauri::State<AppState>) -> Result<u16, String> {
    state.backend.restart()
}

#[tauri::command]
fn backend_status(state: tauri::State<AppState>) -> serde_json::Value {
    serde_json::json!({
        "running": state.backend.is_running(),
        "port": state.backend.port(),
        "log": backend::global_log(),
    })
}

#[tauri::command]
fn backend_log() -> Vec<String> {
    backend::global_log()
}

/// 탐색기에서 파일을 선택된 상태로 연다. 완료 화면의 "폴더 열기" 용도.
#[tauri::command]
fn reveal_in_explorer(path: String) -> Result<(), String> {
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        std::process::Command::new("explorer.exe")
            .arg("/select,")
            .arg(&path)
            .creation_flags(0x0800_0000)
            .spawn()
            .map_err(|e| format!("탐색기를 열지 못했습니다: {e}"))?;
    }
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let be = Arc::new(Backend::new(backend::backend_root()));
    let be_for_exit = be.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_window_state::Builder::default().build())
        .manage(AppState { backend: be.clone() })
        .invoke_handler(tauri::generate_handler![
            backend_start,
            backend_restart,
            backend_status,
            backend_log,
            reveal_in_explorer,
        ])
        .setup(move |app| {
            // 창이 뜨자마자 백엔드를 띄운다. 실패해도 앱은 살아 있어야 하고,
            // 프론트가 원인을 화면에 띄운다.
            let handle = app.handle().clone();
            let b = be.clone();
            std::thread::spawn(move || match b.start() {
                Ok(port) => {
                    let _ = handle.emit("backend-ready", port);
                }
                Err(e) => {
                    let _ = handle.emit("backend-failed", e);
                }
            });
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                if let Some(state) = window.app_handle().try_state::<AppState>() {
                    state.backend.stop();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("Tauri 앱을 시작하지 못했습니다")
        .run(move |_app, event| {
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                be_for_exit.stop();
            }
        });
}
