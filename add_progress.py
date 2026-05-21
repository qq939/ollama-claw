import re

with open('./control/app.py', 'r', encoding='utf-8') as f:
    content = f.read()

def add_progress_tracking(content):
    ollama_stream_request = '''
    def ollama_stream_request(path, payload=None, timeout=60 * 60):
        data = None
        headers = {"Content-Type": "application/json", "Accept": "application/x-ndjson"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        errors = []
        for base_url in ollama_base_urls():
            try:
                req = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    for line in resp:
                        if line:
                            yield json.loads(line.decode("utf-8"))
                return
            except Exception as e:
                errors.append(f"{base_url}: {e}")

'''

    pull_ollama_model_async = '''
    def pull_ollama_model_async(ollama_model):
        started_at = now_iso()
        ollama_pull_jobs[ollama_model] = {"status": "pulling", "started_at": started_at, "error": "", "progress": 0, "total": None, "digest": ""}

        def run_pull():
            try:
                for chunk in ollama_stream_request("/api/pull", {"name": ollama_model, "stream": True}, timeout=60 * 60):
                    if "error" in chunk:
                        ollama_pull_jobs[ollama_model]["status"] = "error"
                        ollama_pull_jobs[ollama_model]["error"] = chunk["error"]
                        return
                    if "status" in chunk:
                        ollama_pull_jobs[ollama_model]["status_message"] = chunk["status"]
                    if "progress" in chunk:
                        ollama_pull_jobs[ollama_model]["progress"] = chunk["progress"]
                    if "total" in chunk:
                        ollama_pull_jobs[ollama_model]["total"] = chunk["total"]
                    if "digest" in chunk:
                        ollama_pull_jobs[ollama_model]["digest"] = chunk["digest"]
                    if "completed" in chunk:
                        ollama_pull_jobs[ollama_model]["completed"] = chunk["completed"]
                ollama_pull_jobs[ollama_model] = {
                    "status": "done",
                    "started_at": started_at,
                    "finished_at": now_iso(),
                    "error": "",
                }
            except Exception as e:
                ollama_pull_jobs[ollama_model] = {
                    "status": "error",
                    "started_at": started_at,
                    "finished_at": now_iso(),
                    "error": str(e),
                }

        threading.Thread(target=run_pull, name=f"ollama-pull-{ollama_model}", daemon=True).start()
        return {"method": "ollama_http_api", "base_urls": ollama_base_urls(), "model": ollama_model, "started_at": started_at}

'''

    check_pull_status_js = '''
      async function checkPullStatus() {
        try {
          const res = await fetch("/api/ollama/models/pull/status");
          const data = await res.json();
          const status = document.getElementById("modelStatus");
          const pullLogs = document.getElementById("pullLogs");
          if (data.pulling) {
            const jobs = data.jobs || {};
            const jobKeys = Object.keys(jobs);
            if (jobKeys.length > 0) {
              const job = jobs[jobKeys[0]];
              let statusText = "下载中";
              if (job.status_message) {
                statusText += ": " + job.status_message;
              }
              if (job.progress !== undefined) {
                statusText += " (" + Math.round(job.progress) + "%)";
              }
              status.textContent = statusText;
              if (pullLogs) {
                pullLogs.textContent = (job.status_message || "下载中") + "\\\\n";
              }
            } else {
              status.textContent = "下载中...";
            }
            status.className = "model-status pulling";
            setTimeout(checkPullStatus, 2000);
          } else {
            status.textContent = "✓ 下载完成";
            status.className = "model-status";
            if (pullLogs) {
              pullLogs.textContent = "✓ 下载完成\\\\n";
            }
            await loadOllamaModels();
          }
        } catch (e) {
          console.error("Check pull status error:", e);
        }
      }
'''

    in_ollama_json_request = 'raise RuntimeError("Unable to reach Ollama API. Tried " + "; ".join(errors))'
    
    if 'def ollama_stream_request' not in content:
        content = content.replace(in_ollama_json_request, ollama_stream_request + in_ollama_json_request)
    
    old_pull = 'def pull_ollama_model_async(ollama_model):\n        started_at = now_iso()\n        ollama_pull_jobs[ollama_model] = {"status": "pulling", "started_at": started_at, "error": ""}'
    if old_pull in content and 'def pull_ollama_model_async' not in pull_ollama_model_async:
        content = content.replace(old_pull, 'def pull_ollama_model_async(ollama_model):\n        started_at = now_iso()\n        ollama_pull_jobs[ollama_model] = {"status": "pulling", "started_at": started_at, "error": "", "progress": 0, "total": None, "digest": ""}')
        
        old_run_pull = '''def run_pull():
            try:
                ollama_json_request("/api/pull", {"name": ollama_model, "stream": False}, timeout=60 * 60)'''
        
        new_run_pull = '''def run_pull():
            try:
                for chunk in ollama_stream_request("/api/pull", {"name": ollama_model, "stream": True}, timeout=60 * 60):
                    if "error" in chunk:
                        ollama_pull_jobs[ollama_model]["status"] = "error"
                        ollama_pull_jobs[ollama_model]["error"] = chunk["error"]
                        return
                    if "status" in chunk:
                        ollama_pull_jobs[ollama_model]["status_message"] = chunk["status"]
                    if "progress" in chunk:
                        ollama_pull_jobs[ollama_model]["progress"] = chunk["progress"]
                    if "total" in chunk:
                        ollama_pull_jobs[ollama_model]["total"] = chunk["total"]
                    if "digest" in chunk:
                        ollama_pull_jobs[ollama_model]["digest"] = chunk["digest"]
                    if "completed" in chunk:
                        ollama_pull_jobs[ollama_model]["completed"] = chunk["completed"]'''
        
        content = content.replace(old_run_pull, new_run_pull)
    
    old_check = '''async function checkPullStatus() {
        try {
          const res = await fetch("/api/ollama/models/pull/status");
          const data = await res.json();
          const status = document.getElementById("modelStatus");
          if (data.pulling) {
            status.textContent = "下载中...";
            status.className = "model-status pulling";
            setTimeout(checkPullStatus, 5000);
          } else {
            status.textContent = "✓ 下载完成";
            status.className = "model-status";
            await loadOllamaModels();
          }
        } catch (e) {
          console.error("Check pull status error:", e);
        }
      }'''

    new_check = '''async function checkPullStatus() {
        try {
          const res = await fetch("/api/ollama/models/pull/status");
          const data = await res.json();
          const status = document.getElementById("modelStatus");
          const pullLogs = document.getElementById("pullLogs");
          if (data.pulling) {
            const jobs = data.jobs || {};
            const jobKeys = Object.keys(jobs);
            if (jobKeys.length > 0) {
              const job = jobs[jobKeys[0]];
              let statusText = "下载中";
              if (job.status_message) {
                statusText += ": " + job.status_message;
              }
              if (job.progress !== undefined) {
                statusText += " (" + Math.round(job.progress) + "%)";
              }
              status.textContent = statusText;
              if (pullLogs) {
                pullLogs.textContent = (job.status_message || "下载中") + "\\\\n";
              }
            } else {
              status.textContent = "下载中...";
            }
            status.className = "model-status pulling";
            setTimeout(checkPullStatus, 2000);
          } else {
            status.textContent = "✓ 下载完成";
            status.className = "model-status";
            if (pullLogs) {
              pullLogs.textContent = "✓ 下载完成\\\\n";
            }
            await loadOllamaModels();
          }
        } catch (e) {
          console.error("Check pull status error:", e);
        }
      }'''

    content = content.replace(old_check, new_check)
    
    return content

content = add_progress_tracking(content)

with open('./control/app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")