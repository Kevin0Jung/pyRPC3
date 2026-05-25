from __future__ import annotations

import cgi
import json
import mimetypes
import os
import re
import sys
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

from .RPC3 import RPC3
from .csvtorsp import file_to_rpc3
from .readtocsv import export_data_to_csv

ROOT = Path(__file__).resolve().parents[1]


def default_output_root() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "pyRPC3" / "output" / "gui"
    return ROOT / "output" / "gui"


GUI_OUTPUT_ROOT = default_output_root()
UPLOAD_ROOT = GUI_OUTPUT_ROOT / "uploads"
JOB_ROOT = GUI_OUTPUT_ROOT / "jobs"


def run(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = False) -> None:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    JOB_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((host, port), GuiRequestHandler)
    url = f"http://{host}:{server.server_address[1]}"
    print(f"pyRPC3 GUI: {url}")
    if open_browser:
        threading.Timer(0.5, open_url, args=(url,)).start()
    server.serve_forever()


def open_url(url: str) -> None:
    import webbrowser

    webbrowser.open(url)


class GuiRequestHandler(BaseHTTPRequestHandler):
    server_version = "pyRPC3GUI/1.0"

    def do_GET(self) -> None:
        parsed_path = urlparse(self.path)
        if parsed_path.path == "/":
            self._send_html(INDEX_HTML)
            return
        if parsed_path.path.startswith("/download/"):
            self._send_download(parsed_path.path)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed_path = urlparse(self.path)
        try:
            if parsed_path.path == "/api/rsp-to-csv":
                self._handle_rsp_to_csv()
                return
            if parsed_path.path == "/api/csv-to-rsp":
                self._handle_csv_to_rsp()
                return
            self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _handle_rsp_to_csv(self) -> None:
        fields = self._parse_multipart()
        rsp_upload = fields.get("rsp")
        if rsp_upload is None:
            raise ValueError("请选择 RSP 文件。")

        job_id = new_job_id()
        upload_dir, job_dir = make_job_dirs(job_id)
        rsp_path = save_upload(rsp_upload, upload_dir, {".rsp", ".drv", ".rpc", ".tim"})

        csv_path = job_dir / f"{rsp_path.stem}.csv"
        metadata_path = job_dir / f"{rsp_path.stem}.rpc3meta.json"
        rpc3_obj = RPC3(str(rsp_path))
        if rpc3_obj.get_errors():
            raise ValueError("; ".join(rpc3_obj.get_errors()))

        export_data_to_csv(
            rpc3_obj=rpc3_obj,
            output_file=csv_path,
            overwrite=True,
            write_metadata=True,
            metadata_file=metadata_path,
        )
        self._send_json(
            {
                "ok": True,
                "job_id": job_id,
                "summary": {
                    "channels": len(rpc3_obj.channels),
                    "samples": rpc3_obj.sample_count,
                    "dt": rpc3_obj.dt,
                },
                "files": [
                    file_payload(job_id, csv_path),
                    file_payload(job_id, metadata_path),
                ],
            }
        )

    def _handle_csv_to_rsp(self) -> None:
        fields = self._parse_multipart()
        csv_upload = fields.get("csv")
        metadata_upload = fields.get("metadata")
        if csv_upload is None:
            raise ValueError("请选择 CSV 文件。")
        if metadata_upload is None:
            raise ValueError("CSV 转 RSP 需要同时提供 .rpc3meta.json 文件。")

        job_id = new_job_id()
        upload_dir, job_dir = make_job_dirs(job_id)
        csv_path = save_upload(csv_upload, upload_dir, {".csv"})
        metadata_path = save_upload(metadata_upload, upload_dir, {".json"})

        output_rsp_path = job_dir / f"{csv_path.stem}.rsp"
        file_to_rpc3(
            input_file_path=csv_path,
            output_rsp_file_path=output_rsp_path,
            metadata_path=metadata_path,
        )
        roundtrip = RPC3(str(output_rsp_path))
        if roundtrip.get_errors():
            raise ValueError("; ".join(roundtrip.get_errors()))

        self._send_json(
            {
                "ok": True,
                "job_id": job_id,
                "summary": {
                    "channels": len(roundtrip.channels),
                    "samples": roundtrip.sample_count,
                    "dt": roundtrip.dt,
                },
                "files": [file_payload(job_id, output_rsp_path)],
            }
        )

    def _parse_multipart(self) -> dict[str, cgi.FieldStorage]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("请求必须使用 multipart/form-data。")

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        fields: dict[str, cgi.FieldStorage] = {}
        for key in form.keys():
            item = form[key]
            if isinstance(item, list):
                item = item[0]
            if getattr(item, "filename", None):
                fields[key] = item
        return fields

    def _send_download(self, path: str) -> None:
        match = re.fullmatch(r"/download/([A-Za-z0-9_-]+)/([^/]+)", unquote(path))
        if not match:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        job_id, filename = match.groups()
        file_path = (JOB_ROOT / job_id / filename).resolve()
        job_dir = (JOB_ROOT / job_id).resolve()
        if not str(file_path).startswith(str(job_dir) + os.sep) or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header(
            "Content-Disposition",
            f"attachment; filename=\"{file_path.name}\"",
        )
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, content: str) -> None:
        data = content.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def new_job_id() -> str:
    return uuid.uuid4().hex


def make_job_dirs(job_id: str) -> tuple[Path, Path]:
    upload_dir = UPLOAD_ROOT / job_id
    job_dir = JOB_ROOT / job_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    job_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir, job_dir


def save_upload(upload: cgi.FieldStorage, directory: Path, allowed_suffixes: set[str]) -> Path:
    filename = safe_filename(upload.filename or "upload")
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed_suffixes:
        allowed = ", ".join(sorted(allowed_suffixes))
        raise ValueError(f"文件类型不支持：{filename}。允许：{allowed}")

    output_path = directory / filename
    data = upload.file.read()
    if not data:
        raise ValueError(f"文件为空：{filename}")
    output_path.write_bytes(data)
    return output_path


def safe_filename(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^A-Za-z0-9._() -]+", "_", name).strip(" .")
    return name or "upload"


def file_payload(job_id: str, file_path: Path) -> dict[str, object]:
    return {
        "name": file_path.name,
        "size": file_path.stat().st_size,
        "url": f"/download/{job_id}/{quote(file_path.name)}",
    }


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pyRPC3 GUI</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #17202a;
      --muted: #667085;
      --line: #d8dde6;
      --accent: #1f7a68;
      --accent-dark: #17594d;
      --danger: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      color: var(--ink);
      background: var(--bg);
    }
    header {
      padding: 20px 24px 14px;
      border-bottom: 1px solid var(--line);
      background: #fff;
    }
    h1 { margin: 0; font-size: 24px; font-weight: 700; }
    main {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      padding: 18px;
      max-width: 1240px;
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      min-width: 0;
    }
    h2 { margin: 0 0 14px; font-size: 18px; }
    .drop {
      border: 2px dashed #a8b2c1;
      border-radius: 8px;
      min-height: 132px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 16px;
      margin-bottom: 12px;
      background: #fbfcfe;
      transition: border-color 120ms ease, background 120ms ease;
      cursor: pointer;
    }
    .drop.active {
      border-color: var(--accent);
      background: #eef8f5;
    }
    .drop strong { display: block; font-size: 15px; margin-bottom: 6px; }
    .drop span { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
    input[type="file"] { display: none; }
    button {
      width: 100%;
      height: 42px;
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font-size: 15px;
      font-weight: 650;
      cursor: pointer;
    }
    button:hover { background: var(--accent-dark); }
    button:disabled { background: #98a2b3; cursor: wait; }
    .status {
      min-height: 24px;
      margin-top: 12px;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .status.error { color: var(--danger); }
    .downloads {
      display: grid;
      gap: 8px;
      margin-top: 12px;
    }
    .downloads a {
      color: var(--accent-dark);
      text-decoration: none;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      background: #fff;
      overflow-wrap: anywhere;
    }
    .summary {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-top: 12px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      background: #fbfcfe;
      min-width: 0;
    }
    .metric b { display: block; font-size: 17px; margin-bottom: 3px; }
    .metric span { color: var(--muted); font-size: 12px; }
    @media (max-width: 820px) {
      main { grid-template-columns: 1fr; padding: 12px; }
      header { padding: 16px; }
    }
  </style>
</head>
<body>
  <header><h1>pyRPC3</h1></header>
  <main>
    <section>
      <h2>RSP -> CSV + JSON</h2>
      <div class="drop" data-input="rspFile">
        <div><strong>选择 RSP 文件</strong><span id="rspName">拖拽到这里或点击</span></div>
      </div>
      <input id="rspFile" type="file" accept=".rsp,.drv,.rpc,.tim">
      <button id="rspButton">转换</button>
      <div id="rspStatus" class="status"></div>
      <div id="rspSummary" class="summary"></div>
      <div id="rspDownloads" class="downloads"></div>
    </section>

    <section>
      <h2>CSV + JSON -> RSP</h2>
      <div class="drop" data-input="csvFile">
        <div><strong>选择 CSV 文件</strong><span id="csvName">拖拽到这里或点击</span></div>
      </div>
      <input id="csvFile" type="file" accept=".csv">
      <div class="drop" data-input="metadataFile">
        <div><strong>选择 JSON 文件</strong><span id="metadataName">拖拽到这里或点击</span></div>
      </div>
      <input id="metadataFile" type="file" accept=".json,.rpc3meta.json">
      <button id="csvButton">转换</button>
      <div id="csvStatus" class="status"></div>
      <div id="csvSummary" class="summary"></div>
      <div id="csvDownloads" class="downloads"></div>
    </section>
  </main>

  <script>
    const state = { rspFile: null, csvFile: null, metadataFile: null };

    function bindDrop(drop) {
      const input = document.getElementById(drop.dataset.input);
      const label = document.getElementById(drop.dataset.input.replace("File", "Name"));
      drop.addEventListener("click", () => input.click());
      drop.addEventListener("dragover", event => {
        event.preventDefault();
        drop.classList.add("active");
      });
      drop.addEventListener("dragleave", () => drop.classList.remove("active"));
      drop.addEventListener("drop", event => {
        event.preventDefault();
        drop.classList.remove("active");
        if (event.dataTransfer.files.length) {
          setFile(input.id, event.dataTransfer.files[0], label);
        }
      });
      input.addEventListener("change", () => {
        if (input.files.length) setFile(input.id, input.files[0], label);
      });
    }

    function setFile(id, file, label) {
      state[id] = file;
      label.textContent = file.name;
    }

    async function postFiles(url, files, statusId, downloadsId, summaryId, buttonId) {
      const status = document.getElementById(statusId);
      const downloads = document.getElementById(downloadsId);
      const summary = document.getElementById(summaryId);
      const button = document.getElementById(buttonId);
      status.classList.remove("error");
      status.textContent = "处理中...";
      downloads.innerHTML = "";
      summary.innerHTML = "";
      button.disabled = true;

      try {
        const form = new FormData();
        for (const [name, file] of Object.entries(files)) form.append(name, file);
        const response = await fetch(url, { method: "POST", body: form });
        const payload = await response.json();
        if (!response.ok || !payload.ok) throw new Error(payload.error || "转换失败");
        status.textContent = "完成";
        renderSummary(summary, payload.summary);
        renderDownloads(downloads, payload.files);
      } catch (error) {
        status.classList.add("error");
        status.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    }

    function renderSummary(container, data) {
      container.innerHTML = [
        metric(data.channels, "channels"),
        metric(data.samples, "samples"),
        metric(data.dt, "dt")
      ].join("");
    }

    function metric(value, label) {
      return `<div class="metric"><b>${value}</b><span>${label}</span></div>`;
    }

    function renderDownloads(container, files) {
      container.innerHTML = files.map(file =>
        `<a href="${file.url}">${file.name}</a>`
      ).join("");
    }

    document.querySelectorAll(".drop").forEach(bindDrop);
    document.getElementById("rspButton").addEventListener("click", () => {
      if (!state.rspFile) {
        const status = document.getElementById("rspStatus");
        status.classList.add("error");
        status.textContent = "请选择 RSP 文件。";
        return;
      }
      postFiles("/api/rsp-to-csv", { rsp: state.rspFile }, "rspStatus", "rspDownloads", "rspSummary", "rspButton");
    });
    document.getElementById("csvButton").addEventListener("click", () => {
      const status = document.getElementById("csvStatus");
      if (!state.csvFile || !state.metadataFile) {
        status.classList.add("error");
        status.textContent = "请选择 CSV 和 JSON 文件。";
        return;
      }
      postFiles(
        "/api/csv-to-rsp",
        { csv: state.csvFile, metadata: state.metadataFile },
        "csvStatus",
        "csvDownloads",
        "csvSummary",
        "csvButton"
      );
    });
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    run()
