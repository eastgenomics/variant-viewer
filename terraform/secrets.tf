resource "aws_secretsmanager_secret" "db" {
  name       = "${var.app_name}/db-credentials"
  kms_key_id = aws_kms_key.secrets.arn

  tags = { Name = "${var.app_name}-db-secret" }
}

resource "aws_secretsmanager_secret_version" "db" {
  secret_id = aws_secretsmanager_secret.db.id
  secret_string = jsonencode({
    username = aws_db_instance.postgres.username
    password = random_password.db.result
    host     = aws_db_instance.postgres.address
    port     = aws_db_instance.postgres.port
    dbname   = aws_db_instance.postgres.db_name
  })
}
