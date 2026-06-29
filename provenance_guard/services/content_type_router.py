"""Content type routing service."""

from provenance_guard.models import TextPipelineInput
from provenance_guard.services.errors import SubmitValidationError


class ContentTypeRouter:
    """Routes validated content envelopes to supported pipelines."""

    def __init__(self, text_pipeline):
        self.text_pipeline = text_pipeline

    def route(self, envelope, audit_context):
        if envelope.content_type != "text":
            raise SubmitValidationError(
                code="unsupported_content_type",
                message="v1 supports text submissions only.",
                status_code=415,
            )

        pipeline_input = TextPipelineInput(
            audit_context=audit_context,
            content=envelope.content,
            metadata=envelope.metadata,
        )
        return self.text_pipeline.run(pipeline_input)
