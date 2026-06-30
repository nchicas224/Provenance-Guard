"""Small Gradio interface for the Provenance Guard Flask API."""

import json
import os
from pathlib import Path
import urllib.error
import urllib.request

import gradio as gr


API_BASE_URL = os.getenv("PROVENANCE_API_BASE_URL", "http://127.0.0.1:5000")
EVALUATION_EXAMPLES_PATH = Path(__file__).parent / "docs" / "evaluation_examples.json"


def load_evaluation_examples():
    if not EVALUATION_EXAMPLES_PATH.exists():
        return []

    with EVALUATION_EXAMPLES_PATH.open(encoding="utf-8") as examples_file:
        examples = json.load(examples_file)

    return [
        [
            "user_123",
            example["content"],
            "manual_eval",
            example["id"],
            f"{example['expected_bucket']}: {example['title']}",
        ]
        for example in examples
    ]


def submit_text(creator_id, content, platform, submission_id, title):
    payload = {
        "creator_id": creator_id,
        "content_type": "text",
        "content": content,
        "metadata": {
            "platform": platform,
            "submission_id": submission_id,
            "title": title,
        },
    }
    payload["metadata"] = {
        key: value for key, value in payload["metadata"].items() if value
    }
    response_json = _post_json("/api/v1/submit", payload)
    return _format_submit_label(response_json), response_json


def submit_appeal(audit_id, creator_id, reason, email):
    payload = {
        "audit_id": audit_id,
        "creator_id": creator_id,
        "reason": reason,
        "contact": {"email": email} if email else {},
    }
    return _post_json("/api/v1/appeals", payload)


def check_health():
    return _get_json("/api/v1/health")


def _format_submit_label(response_json):
    if not isinstance(response_json, dict):
        return "The API returned an unexpected response shape."

    error = response_json.get("error")
    if isinstance(error, dict):
        code = error.get("code", "unknown_error")
        message = error.get("message", "The submission could not be analyzed.")
        return f"Error: {code}\n{message}"

    result = response_json.get("attribution_result", "unknown")
    confidence_level = response_json.get("confidence_level", "unknown")
    ai_likelihood = response_json.get("ai_likelihood")
    confidence_score = response_json.get("confidence_score")
    degraded = response_json.get("degraded", False)
    audit_id = response_json.get("audit_id", "not available")
    transparency_label = response_json.get("transparency_label", "")

    ai_likelihood_text = _format_score(ai_likelihood)
    confidence_score_text = _format_score(confidence_score)
    degraded_text = "Yes" if degraded else "No"

    return (
        f"Result: {result}\n"
        f"Confidence: {confidence_level} ({confidence_score_text})\n"
        f"AI likelihood: {ai_likelihood_text}\n"
        f"Degraded analysis: {degraded_text}\n"
        f"Audit ID: {audit_id}\n\n"
        f"{transparency_label}"
    )


def _format_score(value):
    if isinstance(value, int | float):
        return f"{value:.4f}"
    return "not available"


def _post_json(path, payload):
    request = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _send(request)


def _get_json(path):
    request = urllib.request.Request(f"{API_BASE_URL}{path}", method="GET")
    return _send(request)


def _send(request):
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {"error": {"code": "http_error", "message": body}}
    except urllib.error.URLError as error:
        return {
            "error": {
                "code": "api_unreachable",
                "message": f"Could not reach Flask API at {API_BASE_URL}: {error.reason}",
            }
        }


with gr.Blocks(title="Provenance Guard") as demo:
    gr.Markdown("# Provenance Guard")
    gr.Markdown(
        "A small evaluation interface for the Flask API. Start `python run.py` "
        "before using this UI."
    )

    with gr.Tab("Submit"):
        creator_id = gr.Textbox(label="Creator ID", value="user_123")
        content = gr.Textbox(label="Text submission", lines=10)
        with gr.Row():
            platform = gr.Textbox(label="Platform", value="manual_eval")
            submission_id = gr.Textbox(label="Submission ID")
            title = gr.Textbox(label="Title")
        submit_button = gr.Button("Analyze")
        submit_label = gr.Textbox(
            label="User-facing label",
            lines=8,
            interactive=False,
        )
        submit_output = gr.JSON(label="API response")
        submit_button.click(
            submit_text,
            inputs=[creator_id, content, platform, submission_id, title],
            outputs=[submit_label, submit_output],
        )
        gr.Examples(
            examples=load_evaluation_examples(),
            inputs=[creator_id, content, platform, submission_id, title],
        )

    with gr.Tab("Appeal"):
        appeal_audit_id = gr.Textbox(label="Audit ID")
        appeal_creator_id = gr.Textbox(label="Creator ID", value="user_123")
        appeal_reason = gr.Textbox(label="Appeal reason", lines=5)
        appeal_email = gr.Textbox(label="Contact email")
        appeal_button = gr.Button("Submit Appeal")
        appeal_output = gr.JSON(label="API response")
        appeal_button.click(
            submit_appeal,
            inputs=[appeal_audit_id, appeal_creator_id, appeal_reason, appeal_email],
            outputs=appeal_output,
        )

    with gr.Tab("Health"):
        health_button = gr.Button("Check API Health")
        health_output = gr.JSON(label="API response")
        health_button.click(check_health, outputs=health_output)


if __name__ == "__main__":
    demo.launch()
