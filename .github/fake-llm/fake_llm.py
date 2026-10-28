"""Fake OpenAI-compatible LLM for workflow tests.

Records every request body to a JSONL file and answers with a fixed script of
tool calls (each one only when the bot offers that tool), then a final answer.
The CHECK command reports what a model-chosen command can do, as yes/no and
counts only.
"""
import json
import re
import time
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = sys.argv[2]
# guard: first leave a background process and an in-dir link, to test the job's check.
# cron: first try to install a crontab.
MODE = sys.argv[3] if len(sys.argv) > 3 else "normal"

CHECK = r"""
echo "CHECK user: $(id -un)"
n=0
for f in /proc/[0-9]*/environ; do tr '\0' '\n' < "$f" 2>/dev/null | grep -q '^GXY_TOOL_BOT_API_KEY=' && n=$((n+1)); done
echo "CHECK readable environments holding the key: $n"
if sudo -n true 2>/dev/null; then echo "CHECK sudo: yes"; else echo "CHECK sudo: no"; fi
if docker ps >/dev/null 2>&1; then echo "CHECK docker: yes"; else echo "CHECK docker: no"; fi
if touch probe-write.txt 2>/dev/null; then echo "CHECK can write tool dir: yes"; rm -f probe-write.txt; else echo "CHECK can write tool dir: no"; fi
if touch ../outside.txt 2>/dev/null; then echo "CHECK can write tools/: YES"; rm -f ../outside.txt; else echo "CHECK can write tools/: no"; fi
if touch "$GITHUB_WORKSPACE/README.md" 2>/dev/null; then echo "CHECK can write repo files: YES"; else echo "CHECK can write repo files: no"; fi
echo "CHECK processes left from earlier commands: $(pgrep -u "$(id -un)" -x sleep | wc -l)"
d=$(pwd -P); if mv "$d" "$d.x" 2>/dev/null; then echo "CHECK can replace the tool dir: YES"; mv "$d.x" "$d"; else echo "CHECK can replace the tool dir: no"; fi
"""

PREFIX = {
    "guard": [("run_in_conda", {"packages": ["coreutils"], "command": "ln -s demo.xml link.xml; (sleep 600 >/dev/null 2>&1 &); echo planted"})],
    # cron: try to leave a crontab that plants a link after the job's check.
    "cron": [("run_in_conda", {"packages": ["coreutils"], "command": 'echo "* * * * * ln -sf demo.xml $(pwd -P)/late.xml" | crontab - 2>&1; echo "CHECK crontab -l: $(crontab -l 2>&1)"'})],
}
STEPS = PREFIX.get(MODE, []) + [
    ("run_in_conda", {"packages": ["coreutils"], "command": CHECK}),
    ("run_in_conda", {"packages": ["samtools"], "command": "samtools --version | head -1"}),
    ("planemo_lint", {"path": "demo.xml"}),
    ("planemo_test", {"path": "demo.xml"}),
    ("write_file", None),
]

# generate (the bot offers set_tool_dir): write a small tool, then the same checks.
TOOL = """<tool id="democat" name="Demo cat" version="0.1.0" profile="23.0">
    <requirements>
        <requirement type="package" version="9.5">coreutils</requirement>
    </requirements>
    <command detect_errors="exit_code"><![CDATA[cat '$input' > '$output']]></command>
    <inputs>
        <param name="input" type="data" format="txt" label="Input"/>
    </inputs>
    <outputs>
        <data name="output" format="txt"/>
    </outputs>
    <tests>
        <test>
            <param name="input" value="in.txt"/>
            <output name="output" file="in.txt"/>
        </test>
    </tests>
    <help><![CDATA[Copies the input.]]></help>
    <citations>
        <citation type="bibtex">@misc{coreutils, title={GNU coreutils}, url={https://www.gnu.org/software/coreutils/}}</citation>
    </citations>
</tool>
"""
SHED = """name: democat
owner: arash77
description: Copy a text file (test tool)
long_description: Copy a text file (test tool).
categories:
  - Text Manipulation
homepage_url: https://www.gnu.org/software/coreutils/
remote_repository_url: https://github.com/arash77/gxy-tool-bot-feedback-test/tree/main/tools/democat
type: unrestricted
"""
GEN_PREFIX = {"guard": [("run_in_conda", {"packages": ["coreutils"], "command": "ln -s democat.xml link.xml; (sleep 600 >/dev/null 2>&1 &); echo planted"})]}
GEN_STEPS = [
    ("set_tool_dir", {"name": "democat"}),
    ("write_file", {"path": "test-data/in.txt", "content": "hello\n"}),
    ("write_file", {"path": "democat.xml", "content": TOOL}),
    ("write_file", {"path": ".shed.yml", "content": SHED}),
] + GEN_PREFIX.get(MODE, []) + [
    ("run_in_conda", {"packages": ["coreutils"], "command": CHECK}),
    ("planemo_lint", {"path": "democat.xml"}),
    ("planemo_test", {"path": "democat.xml"}),
]
done = set()


def tool_call(i, name, args):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": f"call_{i}", "type": "function",
        "function": {"name": name, "arguments": json.dumps(args)}}]}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        with open(LOG, "a") as f:
            f.write(body.decode() + "\n")
        req = json.loads(body)
        tools = {t["function"]["name"] for t in req.get("tools", [])}
        msg, finish = {"role": "assistant", "content": "Done."}, "stop"
        # Feedback also offers set_tool_dir: tell the flows apart by the prompt.
        first_user = next((m["content"] for m in req["messages"] if m["role"] == "user"), "")
        gen = "set_tool_dir" in tools and "addressing feedback" not in str(first_user)
        for i, (name, args) in enumerate(GEN_STEPS if gen else STEPS):
            key = ("gen" if gen else "fb", i)
            if key in done or name not in tools:
                continue
            done.add(key)
            if name == "write_file" and args is None:
                # Rewrite the help text: an edit that keeps the tool valid every run.
                xml = re.sub(r"<help><!\[CDATA\[.*?\]\]></help>",
                             f"<help><![CDATA[Copies the input. Edited {int(time.time())}.]]></help>",
                             open("tools/demo/demo.xml").read(), flags=re.S)
                args = {"path": "demo.xml", "content": xml}
            msg, finish = tool_call(f"{key[0]}{i}", name, args), "tool_calls"
            break
        data = json.dumps({"id": "fake", "object": "chat.completion", "model": "stub",
                           "choices": [{"index": 0, "finish_reason": finish, "message": msg}],
                           "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                                     "total_tokens": 2}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
