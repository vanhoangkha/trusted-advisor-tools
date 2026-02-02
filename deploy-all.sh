#!/bin/bash
# Deploy all Trusted Advisor Tools to AWS
# Usage: ./deploy-all.sh [--dry-run]

set -e

REGION="us-east-1"
DRY_RUN="${1:-}"

echo "============================================"
echo "  Trusted Advisor Tools - Deploy All"
echo "  Region: $REGION"
echo "============================================"

# Check prerequisites
command -v sam >/dev/null 2>&1 || { echo "❌ SAM CLI required. Install: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html"; exit 1; }
command -v aws >/dev/null 2>&1 || { echo "❌ AWS CLI required"; exit 1; }

# Verify AWS credentials
aws sts get-caller-identity >/dev/null 2>&1 || { echo "❌ AWS credentials not configured"; exit 1; }
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "Account: $ACCOUNT_ID"

cd "$(dirname "$0")"

deploy_sam() {
    local dir=$1
    local stack=$2
    echo ""
    echo ">>> Deploying $stack..."
    cd "$dir"
    sam build --use-container 2>/dev/null || sam build
    sam deploy \
        --stack-name "$stack" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --no-confirm-changeset \
        --no-fail-on-empty-changeset \
        --resolve-s3
    cd - >/dev/null
    echo "✅ $stack deployed"
}

deploy_cfn() {
    local template=$1
    local stack=$2
    shift 2
    echo ""
    echo ">>> Deploying $stack..."
    aws cloudformation deploy \
        --template-file "$template" \
        --stack-name "$stack" \
        --region "$REGION" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --no-fail-on-empty-changeset \
        "$@"
    echo "✅ $stack deployed"
}

# 1. Unassociated Elastic IPs
deploy_sam "UnassociatedElasticIPs" "TA-UnassociatedElasticIPs"

# 2. S3 Bucket Versioning
deploy_sam "S3BucketVersioning" "TA-S3BucketVersioning"

# 3. IAM Password Policy
deploy_sam "IAMPasswordPolicy" "TA-IAMPasswordPolicy"

# 4. RDS Idle DB Instances
deploy_sam "AmazonRDSIdleDBInstances" "TA-RDSIdleDBInstances"

# 5. S3 Incomplete MPU Abort
deploy_sam "S3IncompleteMPUAbort/ta-s3-incomplete-mpu-abort" "TA-S3IncompleteMPU"

# 6. Exposed Access Keys
deploy_sam "ExposedAccessKeys/cloudformation" "TA-ExposedAccessKeys"

# 7. High Utilization EC2 (needs approver ARN)
echo ""
echo ">>> Deploying TA-HighUtilEC2..."
APPROVER_ARN="arn:aws:iam::${ACCOUNT_ID}:root"
deploy_cfn "HighUtilizationEC2Instances/ta-automation-highutil-ec2.yml" "TA-HighUtilEC2" \
    --parameter-overrides "ResizeAutomationApproverUserARN=$APPROVER_ARN"

# 8. Slack Integration (optional - needs webhook URL)
# Uncomment and set SLACK_WEBHOOK_URL to deploy
# SLACK_WEBHOOK_URL="https://hooks.slack.com/services/xxx"
# if [ -n "$SLACK_WEBHOOK_URL" ]; then
#     deploy_cfn "TA-Integrations/TA-Red-Cost-Slack-Webhook/CF-TA-Red-Slack-Webhook.yml" "TA-SlackIntegration" \
#         --parameter-overrides "SlackWebhookURL=$SLACK_WEBHOOK_URL"
# fi

echo ""
echo "============================================"
echo "  ✅ All deployments complete!"
echo "============================================"
echo ""
echo "Deployed stacks:"
aws cloudformation list-stacks \
    --region "$REGION" \
    --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
    --query "StackSummaries[?starts_with(StackName,'TA-')].{Name:StackName,Status:StackStatus}" \
    --output table
