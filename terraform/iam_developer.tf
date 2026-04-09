# IAM policy for developers working on the variant-viewer.
# Grants the minimum permissions needed to build, deploy, debug, and
# run migrations — but NOT to modify infrastructure (Terraform) or
# manage IAM itself.
#
# Attach this policy to an IAM Identity Center permission set, an IAM
# user, or a role:
#
#   aws iam attach-user-policy  --user-name <USER> --policy-arn <ARN>
#   aws iam attach-role-policy  --role-name <ROLE> --policy-arn <ARN>

resource "aws_iam_policy" "developer" {
  name        = "${var.app_name}-developer"
  description = "Developer access for ${var.app_name}: ECR push, ECS deploy/exec, Lambda update, S3/logs read, Secrets Manager read"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [

      # ---------------------------------------------------------------
      # ECR — push and pull images (app + lambda repos)
      # ---------------------------------------------------------------
      {
        Sid      = "ECRAuth"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "ECRReadWrite"
        Effect = "Allow"
        Action = [
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchGetImage",
          "ecr:BatchCheckLayerAvailability",
          "ecr:PutImage",
          "ecr:InitiateLayerUpload",
          "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload",
          "ecr:DescribeRepositories",
          "ecr:DescribeImages",
          "ecr:ListImages",
        ]
        Resource = [
          aws_ecr_repository.app.arn,
          aws_ecr_repository.lambda.arn,
        ]
      },

      # ---------------------------------------------------------------
      # ECS — deploy new images, view tasks, ECS Exec for debugging
      # ---------------------------------------------------------------
      {
        Sid    = "ECSClusterRead"
        Effect = "Allow"
        Action = [
          "ecs:DescribeClusters",
          "ecs:ListServices",
        ]
        Resource = [aws_ecs_cluster.app.arn]
      },
      {
        Sid    = "ECSServiceDeploy"
        Effect = "Allow"
        Action = [
          "ecs:DescribeServices",
          "ecs:UpdateService",
          "ecs:ListTasks",
          "ecs:DescribeTasks",
        ]
        Resource = "*"
        Condition = {
          ArnEquals = {
            "ecs:cluster" = aws_ecs_cluster.app.arn
          }
        }
      },
      {
        # RegisterTaskDefinition and DescribeTaskDefinition don't
        # support resource-level constraints, so kept in a separate global statement
        Sid    = "ECSTaskDefGlobal"
        Effect = "Allow"
        Action = [
          "ecs:RegisterTaskDefinition",
          "ecs:DescribeTaskDefinition",
          "ecs:ListTaskDefinitions",
        ]
        Resource = "*"
      },
      {
        Sid      = "ECSExec"
        Effect   = "Allow"
        Action   = ["ecs:ExecuteCommand"]
        Resource = "*"
        Condition = {
          ArnEquals = {
            "ecs:cluster" = aws_ecs_cluster.app.arn
          }
        }
      },
      {
        # SSM Session Manager channels required by ECS Exec
        Sid    = "SSMSessionManager"
        Effect = "Allow"
        Action = [
          "ssmmessages:CreateControlChannel",
          "ssmmessages:CreateDataChannel",
          "ssmmessages:OpenControlChannel",
          "ssmmessages:OpenDataChannel",
        ]
        Resource = "*"
      },
      {
        # Pass existing roles to ECS task definitions
        Sid    = "PassECSRoles"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = [
          aws_iam_role.ecs_execution.arn,
          aws_iam_role.ecs_task.arn,
        ]
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ecs-tasks.amazonaws.com"
          }
        }
      },

      # ---------------------------------------------------------------
      # Lambda — update function code after pushing new image
      # ---------------------------------------------------------------
      {
        Sid    = "LambdaUpdate"
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
          "lambda:GetFunctionConfiguration",
          "lambda:ListFunctions",
        ]
        Resource = [aws_lambda_function.ingest.arn]
      },

      # ---------------------------------------------------------------
      # S3 — upload VCFs, read manifests, debug ingest issues
      # ---------------------------------------------------------------
      {
        Sid    = "S3VCFBucket"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = [
          aws_s3_bucket.vcf.arn,
          "${aws_s3_bucket.vcf.arn}/*",
        ]
      },
      {
        Sid    = "KMSDataKeys"
        Effect = "Allow"
        Action = [
          "kms:GenerateDataKey",
          "kms:Decrypt",
          "kms:Encrypt",
        ]
        Resource = [
          aws_kms_key.s3.arn,
          aws_kms_key.secrets.arn,
        ]
      },

      # ---------------------------------------------------------------
      # Secrets Manager — read DB credentials for migrations / debug
      # ---------------------------------------------------------------
      {
        Sid    = "SecretsRead"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret",
        ]
        Resource = [aws_secretsmanager_secret.db.arn]
      },

      # ---------------------------------------------------------------
      # CloudWatch Logs — view ECS and Lambda logs
      # ---------------------------------------------------------------
      {
        Sid    = "LogsRead"
        Effect = "Allow"
        Action = [
          "logs:GetLogEvents",
          "logs:FilterLogEvents",
          "logs:DescribeLogGroups",
          "logs:DescribeLogStreams",
          "logs:StartQuery",
          "logs:StopQuery",
          "logs:GetQueryResults",
        ]
        Resource = [
          "${aws_cloudwatch_log_group.ecs.arn}:*",
          "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${aws_lambda_function.ingest.function_name}:*",
        ]
      },

      # ---------------------------------------------------------------
      # SQS — inspect DLQ for failed ingest events
      # ---------------------------------------------------------------
      {
        Sid    = "DLQRead"
        Effect = "Allow"
        Action = [
          "sqs:GetQueueAttributes",
          "sqs:ReceiveMessage",
          "sqs:GetQueueUrl",
        ]
        Resource = [aws_sqs_queue.ingest_dlq.arn]
      },
    ]
  })

  tags = { Name = "${var.app_name}-developer-policy" }
}

output "developer_policy_arn" {
  description = "ARN of the developer IAM policy — attach to SSO permission set or IAM role"
  value       = aws_iam_policy.developer.arn
}
