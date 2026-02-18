data "aws_caller_identity" "current" {}

# --- Trust policy: allows bedrock-agentcore service to assume this role ---
data "aws_iam_policy_document" "agentcore_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    # Conditions prevent cross-account confused deputy attacks
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:bedrock-agentcore:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"]
    }
  }
}

resource "aws_iam_role" "agentcore_execution" {
  name               = "${var.project_name}-agentcore-execution"
  assume_role_policy = data.aws_iam_policy_document.agentcore_assume_role.json

  tags = {
    Project = var.project_name
  }
}

# Bedrock model invocation (scoped to development convenience; narrow in production)
resource "aws_iam_role_policy_attachment" "bedrock_full" {
  role       = aws_iam_role.agentcore_execution.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonBedrockFullAccess"
}

# --- Runtime operational permissions (ECR, CloudWatch Logs, X-Ray, metrics) ---
data "aws_iam_policy_document" "agentcore_runtime_ops" {
  statement {
    sid = "ECRImageAccess"
    actions = [
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.agent.arn]
  }

  statement {
    sid       = "ECRTokenAccess"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    sid = "LogsCreateGroup"
    actions = [
      "logs:DescribeLogStreams",
      "logs:CreateLogGroup",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
    ]
  }

  statement {
    sid       = "LogsDescribeGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:*"]
  }

  statement {
    sid = "LogsWriteEvents"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = [
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
    ]
  }

  statement {
    sid = "XRayAccess"
    actions = [
      "xray:PutTraceSegments",
      "xray:PutTelemetryRecords",
      "xray:GetSamplingRules",
      "xray:GetSamplingTargets",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "CloudWatchMetrics"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["bedrock-agentcore"]
    }
  }
}

resource "aws_iam_role_policy" "agentcore_runtime_ops" {
  name   = "${var.project_name}-runtime-ops"
  role   = aws_iam_role.agentcore_execution.id
  policy = data.aws_iam_policy_document.agentcore_runtime_ops.json
}

# --- Secrets Manager: allows runtime to fetch Langfuse credentials ---
data "aws_iam_policy_document" "agentcore_secrets" {
  statement {
    sid       = "AllowLangfuseSecretRead"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.langfuse.arn]
  }
}

resource "aws_iam_role_policy" "agentcore_secrets" {
  name   = "${var.project_name}-secrets-policy"
  role   = aws_iam_role.agentcore_execution.id
  policy = data.aws_iam_policy_document.agentcore_secrets.json
}
