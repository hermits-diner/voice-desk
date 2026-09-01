//! 백엔드 sidecar 관리.
//!
//! 파이썬 백엔드를 자식 프로세스로 띄우고, **앱이 어떻게 끝나든** 같이 죽게 만든다.
//! 정상 종료 경로만 믿으면 앱이 크래시했을 때 파이썬이 GPU 메모리를 쥔 채 남는다.
//! Windows 에서는 Job Object 에 JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE 를 걸어두면
//! 부모가 사라지는 순간 커널이 자식을 정리해 준다.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

#[cfg(windows)]
use std::os::windows::io::AsRawHandle;
#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

pub const DEFAULT_PORT: u16 = 7860;

pub struct Backend {
    child: Mutex<Option<Child>>,
    root: PathBuf,
    port: Mutex<u16>,
    log: Mutex<Vec<String>>,
    #[cfg(windows)]
    job: Mutex<Option<JobHandle>>,
}

/// 프로세스 트리를 묶어두는 Job Object. Drop 될 때 자식이 함께 죽는다.
#[cfg(windows)]
pub struct JobHandle(windows::Win32::Foundation::HANDLE);

#[cfg(windows)]
unsafe impl Send for JobHandle {}

#[cfg(windows)]
impl Drop for JobHandle {
    fn drop(&mut self) {
        unsafe {
            let _ = windows::Win32::Foundation::CloseHandle(self.0);
        }
    }
}

#[cfg(windows)]
fn create_job() -> Option<JobHandle> {
    use windows::Win32::System::JobObjects::{
        CreateJobObjectW, SetInformationJobObject, JobObjectExtendedLimitInformation,
        JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    unsafe {
        // 이름 없는 Job. 보안 속성도 기본값.
        let job = CreateJobObjectW(None, windows::core::PCWSTR::null()).ok()?;
        let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        let ok = SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const core::ffi::c_void,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        );
        if ok.is_err() {
            let _ = windows::Win32::Foundation::CloseHandle(job);
            return None;
        }
        Some(JobHandle(job))
    }
}

#[cfg(windows)]
fn assign_to_job(job: &JobHandle, child: &Child) -> bool {
    use windows::Win32::Foundation::HANDLE;
    use windows::Win32::System::JobObjects::AssignProcessToJobObject;
    unsafe {
        AssignProcessToJobObject(job.0, HANDLE(child.as_raw_handle() as _)).is_ok()
    }
}

impl Backend {
    pub fn new(root: PathBuf) -> Self {
        Self {
            child: Mutex::new(None),
            root,
            port: Mutex::new(DEFAULT_PORT),
            log: Mutex::new(Vec::new()),
            #[cfg(windows)]
            job: Mutex::new(None),
        }
    }

    pub fn port(&self) -> u16 {
        *self.port.lock().unwrap()
    }

    pub fn recent_log(&self) -> Vec<String> {
        self.log.lock().unwrap().clone()
    }

    fn python(&self) -> PathBuf {
        self.root.join(".venv").join("Scripts").join("python.exe")
    }

    /// backend/settings.json 에서 포트를 읽는다. 백엔드와 같은 파일을 본다.
    fn configured_port(&self) -> u16 {
        let p = self.root.join("settings.json");
        let Ok(text) = std::fs::read_to_string(&p) else {
            return DEFAULT_PORT;
        };
        serde_json::from_str::<serde_json::Value>(&text)
            .ok()
            .and_then(|v| v.get("port").and_then(|x| x.as_u64()))
            .map(|x| x as u16)
            .unwrap_or(DEFAULT_PORT)
    }

    pub fn is_running(&self) -> bool {
        let mut guard = self.child.lock().unwrap();
        match guard.as_mut() {
            Some(c) => matches!(c.try_wait(), Ok(None)),
            None => false,
        }
    }

    /// 설정 포트가 막혀 있으면(이 PC 는 WSL 이 7860 을 점유) +10 까지 물러난다.
    fn pick_port(base: u16) -> u16 {
        for p in base..=base.saturating_add(10) {
            if std::net::TcpListener::bind(("127.0.0.1", p)).is_ok() {
                return p;
            }
        }
        base
    }

    pub fn start(&self) -> Result<u16, String> {
        if self.is_running() {
            return Ok(self.port());
        }
        let py = self.python();
        if !py.exists() {
            return Err(format!(
                "파이썬 환경이 없습니다: {}. SETUP.md 의 재현 절차로 venv 를 만들어주세요.",
                py.display()
            ));
        }
        let port = Self::pick_port(self.configured_port());

        let mut cmd = Command::new(&py);
        cmd.arg("-m")
            .arg("app.main")
            .arg("--port")
            .arg(port.to_string())
            .current_dir(&self.root)
            .env("HF_HOME", models_dir().join("hf-cache"))
            .env("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
            .env("PYTHONUNBUFFERED", "1")
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        #[cfg(windows)]
        cmd.creation_flags(CREATE_NO_WINDOW);

        let mut child = cmd
            .spawn()
            .map_err(|e| format!("백엔드를 시작하지 못했습니다: {e}"))?;

        // 자식이 뜬 직후 Job 에 넣는다. 이 시점 이후로는 앱이 죽으면 같이 죽는다.
        #[cfg(windows)]
        {
            if let Some(job) = create_job() {
                if assign_to_job(&job, &child) {
                    *self.job.lock().unwrap() = Some(job);
                } else {
                    self.push_log("경고: 백엔드를 Job Object 에 넣지 못했습니다.".into());
                }
            }
        }

        // 로그를 모아둔다. 기동 실패 시 프론트가 원인을 보여줄 수 있어야 한다.
        for (stream, tag) in [
            (child.stdout.take().map(|s| Box::new(s) as Box<dyn std::io::Read + Send>), "out"),
            (child.stderr.take().map(|s| Box::new(s) as Box<dyn std::io::Read + Send>), "err"),
        ] {
            if let Some(s) = stream {
                let sink = self.log_sink();
                std::thread::spawn(move || {
                    for line in BufReader::new(s).lines().map_while(Result::ok) {
                        sink(format!("[{tag}] {line}"));
                    }
                });
            }
        }

        *self.port.lock().unwrap() = port;
        *self.child.lock().unwrap() = Some(child);
        Ok(port)
    }

    fn log_sink(&self) -> impl Fn(String) + Send + 'static {
        // Mutex 를 스레드로 넘기기 위한 정적 저장소. 로그는 최근 200줄만 남긴다.
        let store = LOG.clone();
        move |line: String| {
            let mut v = store.lock().unwrap();
            if v.len() >= 200 {
                v.remove(0);
            }
            v.push(line);
        }
    }

    fn push_log(&self, line: String) {
        let mut v = LOG.lock().unwrap();
        v.push(line);
    }

    pub fn stop(&self) {
        if let Some(mut c) = self.child.lock().unwrap().take() {
            let _ = c.kill();
            let _ = c.wait();
        }
        #[cfg(windows)]
        {
            // Job 을 닫으면 남은 자식까지 커널이 정리한다.
            *self.job.lock().unwrap() = None;
        }
    }

    pub fn restart(&self) -> Result<u16, String> {
        self.stop();
        std::thread::sleep(std::time::Duration::from_millis(300));
        self.start()
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        self.stop();
    }
}

use std::sync::{Arc, LazyLock};
static LOG: LazyLock<Arc<Mutex<Vec<String>>>> =
    LazyLock::new(|| Arc::new(Mutex::new(Vec::new())));

pub fn global_log() -> Vec<String> {
    LOG.lock().unwrap().clone()
}

/// 개발 중에는 소스 트리, 배포본에서는 설치 경로 옆의 backend 를 쓴다.
pub fn backend_root() -> PathBuf {
    if let Ok(p) = std::env::var("VOICEDESK_BACKEND") {
        return PathBuf::from(p);
    }
    let fixed = Path::new(r"C:\ai\voice-desk\backend");
    if fixed.exists() {
        return fixed.to_path_buf();
    }
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("backend")))
        .unwrap_or_else(|| fixed.to_path_buf())
}

pub fn models_dir() -> PathBuf {
    PathBuf::from(r"C:\ai\models")
}
