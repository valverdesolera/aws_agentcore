# ---- Invocation endpoint URL ----
# Format: https://bedrock-agentcore.{region}.amazonaws.com/runtimes/{url-encoded-arn}/invocations?qualifier=DEFAULT
# The ARN is percent-encoded (: → %3A, / → %2F) using Terraform's replace().
locals {
  runtime_arn_encoded = replace(
    replace(aws_bedrockagentcore_agent_runtime.agent.agent_runtime_arn, ":", "%3A"),
    "/", "%2F"
  )
  agent_endpoint = "https://bedrock-agentcore.${var.aws_region}.amazonaws.com/runtimes/${local.runtime_arn_encoded}/invocations?qualifier=DEFAULT"
}

# ---- AgentCore Memory ----
# Short-term memory (STM) for agent session context. Mirrors the CLI-created
# memory from .bedrock_agentcore.yaml (event_expiry_days: 30).
resource "aws_bedrockagentcore_memory" "agent" {
  name                  = "${var.project_name}-memory"
  event_expiry_duration = 30

  tags = {
    Project = var.project_name
  }
}

# ---- AgentCore Agent Runtime ----
# Replaces the manual `agentcore configure` + `agentcore deploy` CLI steps.
# Depends on ECR image already being present (built + pushed separately via CI
# or `docker build/push` before `terraform apply`).
resource "aws_bedrockagentcore_agent_runtime" "agent" {
  agent_runtime_name = var.project_name
  description        = "LangGraph ReAct financial analysis agent"
  role_arn           = aws_iam_role.agentcore_execution.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent.repository_url}:latest"
    }
  }

  # Equivalent to: agentcore deploy --env "LANGFUSE_SECRET_ARN=..."
  environment_variables = {
    LANGFUSE_SECRET_ARN = aws_secretsmanager_secret.langfuse.arn
  }

  # Equivalent to: network_mode: PUBLIC (from .bedrock_agentcore.yaml)
  network_configuration {
    network_mode = "PUBLIC"
  }

  # Equivalent to: --authorizer-config (Cognito JWT)
  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url    = "https://cognito-idp.${var.aws_region}.amazonaws.com/${aws_cognito_user_pool.main.id}/.well-known/openid-configuration"
      allowed_audience = [aws_cognito_user_pool_client.app_client.id]
    }
  }

  # Equivalent to: --request-header-allowlist "Authorization"
  request_header_configuration {
    request_header_allowlist = ["Authorization"]
  }

  # Equivalent to: server_protocol: HTTP (from .bedrock_agentcore.yaml)
  protocol_configuration {
    server_protocol = "HTTP"
  }

  tags = {
    Project = var.project_name
  }
}
