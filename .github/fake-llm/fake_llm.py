"""Fake OpenAI-compatible LLM for workflow tests.

Records every request body to a JSONL file. The first request that offers
write_file gets one write_file call (adds a <help> section to demo.xml);
every other request gets a plain final answer.
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = sys.argv[2]
wrote = False


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        global wrote
        body = self.rfile.read(int(self.headers["Content-Length"]))
        with open(LOG, "a") as f:
            f.write(body.decode() + "\n")
        tools = [t["function"]["name"] for t in json.loads(body).get("tools", [])]
        msg, finish = {"role": "assistant", "content": "Done."}, "stop"
        if "write_file" in tools and not wrote:
            wrote = True
            xml = open("tools/demo/demo.xml").read().replace(
                "</tool>", "    <help><![CDATA[Copies the input.]]></help>\n</tool>")
            msg = {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "write_file",
                             "arguments": json.dumps({"path": "demo.xml", "content": xml})}}]}
            finish = "tool_calls"
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
