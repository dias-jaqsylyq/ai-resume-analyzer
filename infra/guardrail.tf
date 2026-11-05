# Bedrock Guardrail for the analysis (RA-11). The CV and the job description are untrusted
# input, so the guardrail is attached to every live Converse call and then applied once more
# to the finished report (ApplyGuardrail, source OUTPUT):
#
# - Converse evaluates the user message text: the prompt-attack filter blocks prompt injection
#   hidden in a CV or job description. Converse does NOT evaluate tool-call arguments, and the
#   report arrives as a toolUse input, so the output-side policies run through ApplyGuardrail.
# - On the report: personal data (names, emails, phones, addresses) is masked to {NAME},
#   {EMAIL}, ... and harmful content is blocked.
# - PII is not checked on input: every CV is full of personal data by design.
#
# Encryption: the guardrail stores only this policy text (no user data), so it uses the
# AWS-owned key; the project keeps exactly one customer managed key (see docs/decisions.md).
# Cost: nothing while idle; charged per 1,000 characters evaluated, and only in live mode.

resource "aws_bedrock_guardrail" "analysis" {
  name                      = local.name
  description               = "Blocks prompt injection in CVs and job descriptions; masks personal data in reports"
  blocked_input_messaging   = "This resume or job description could not be analyzed because it looks like it contains instructions for the AI."
  blocked_outputs_messaging = "The analysis was blocked by the content filter."

  content_policy_config {
    # Prompt attacks are an input-only filter (output strength must be NONE).
    filters_config {
      type            = "PROMPT_ATTACK"
      input_strength  = "HIGH"
      output_strength = "NONE"
    }

    # Harmful-content filters only on the report: on input they would reject real CVs
    # (e.g. security or medical work history) for no benefit.
    dynamic "filters_config" {
      for_each = toset(["HATE", "INSULTS", "SEXUAL", "VIOLENCE"])
      content {
        type            = filters_config.value
        input_strength  = "NONE"
        output_strength = "MEDIUM"
      }
    }
  }

  sensitive_information_policy_config {
    dynamic "pii_entities_config" {
      for_each = toset(["NAME", "EMAIL", "PHONE", "ADDRESS"])
      content {
        type           = pii_entities_config.value
        action         = "ANONYMIZE"
        input_enabled  = false
        output_enabled = true
        output_action  = "ANONYMIZE"
      }
    }
  }
}

# The Lambda uses a numbered (immutable) version, never DRAFT. Any change to the guardrail
# above publishes a new version, created before the old one is deleted.
resource "aws_bedrock_guardrail_version" "analysis" {
  guardrail_arn = aws_bedrock_guardrail.analysis.guardrail_arn
  description   = "Published by Terraform"

  lifecycle {
    create_before_destroy = true
    replace_triggered_by  = [aws_bedrock_guardrail.analysis]
  }
}

output "guardrail_id" {
  description = "Bedrock Guardrail used by process-analysis (live mode)"
  value       = aws_bedrock_guardrail.analysis.guardrail_id
}

output "guardrail_version" {
  description = "Published guardrail version used by process-analysis"
  value       = aws_bedrock_guardrail_version.analysis.version
}
