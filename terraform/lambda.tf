resource "aws_security_group" "lambda" {
  name        = "${var.app_name}-lambda-sg"
  description = "Lambda ingest function"
  vpc_id      = aws_vpc.main.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "${var.app_name}-lambda-sg" }
}

# SQS Dead Letter Queue for failed S3 events
resource "aws_sqs_queue" "ingest_dlq" {
  name                       = "${var.app_name}-ingest-dlq"
  message_retention_seconds  = 1209600 # 14 days
  visibility_timeout_seconds = 960     # > Lambda timeout

  tags = { Name = "${var.app_name}-ingest-dlq" }
}

resource "aws_lambda_function" "ingest" {
  function_name = "${var.app_name}-ingest"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.lambda.repository_url}:${var.ecr_image_tag}"
  memory_size   = var.lambda_memory_size
  timeout       = 900 # 15 minutes

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda.id]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.ingest_dlq.arn
  }

  environment {
    variables = {
      VCF_BUCKET_NAME = aws_s3_bucket.vcf.id
      DB_SECRET_ARN   = aws_secretsmanager_secret.db.arn
    }
  }

  depends_on = [aws_iam_role_policy_attachment.lambda_basic]

  tags = { Name = "${var.app_name}-ingest-lambda" }
}

# CloudWatch alarm: DLQ has messages → ingest failure is clinical-critical
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.app_name}-ingest-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "VCF ingest Lambda DLQ has failed messages — manual investigation required"
  alarm_actions       = length(var.dlq_alarm_email) > 0 ? [aws_sns_topic.alerts[0].arn] : []
  dimensions = {
    QueueName = aws_sqs_queue.ingest_dlq.name
  }
}

resource "aws_sns_topic" "alerts" {
  count = length(var.dlq_alarm_email) > 0 ? 1 : 0
  name  = "${var.app_name}-alerts"
}

resource "aws_sns_topic_subscription" "dlq_email" {
  count     = length(var.dlq_alarm_email) > 0 ? 1 : 0
  topic_arn = aws_sns_topic.alerts[0].arn
  protocol  = "email"
  endpoint  = var.dlq_alarm_email
}
