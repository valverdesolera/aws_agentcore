resource "aws_secretsmanager_secret" "langfuse" {
  name        = "${var.project_name}/langfuse"
  description = "Langfuse API keys for the stock agent"

  tags = {
    Project = var.project_name
  }
}

resource "aws_secretsmanager_secret_version" "langfuse" {
  secret_id = aws_secretsmanager_secret.langfuse.id
  secret_string = jsonencode({
    LANGFUSE_SECRET_KEY = var.langfuse_secret_key
    LANGFUSE_PUBLIC_KEY = var.langfuse_public_key
    LANGFUSE_BASE_URL   = var.langfuse_base_url
  })
}
