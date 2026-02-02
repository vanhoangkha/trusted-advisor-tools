"""Apply S3 lifecycle policy for incomplete multipart uploads.

Security Improvements:
- Environment variable for role name
- External ID validation
- Input validation
- Structured logging
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

from model.aws.ta import Marshaller, AWSEvent, TAStateChangeNotification

logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

CROSS_ACCOUNT_ROLE_NAME = os.environ.get('CROSS_ACCOUNT_ROLE_NAME', 'CrossAccountS3AccessRole')
CALLER_ACCOUNT = boto3.client('sts').get_caller_identity()['Account']


def lambda_handler(event, context):
    """Handle Trusted Advisor S3 lifecycle check event."""
    # Support both full EventBridge format and simplified test format
    if 'detail-type' in event:
        aws_event: AWSEvent = Marshaller.unmarshall(event, AWSEvent)
        notification: TAStateChangeNotification = aws_event.detail
        check_name = notification.check_name
        bucket_name = notification.check_item_detail.get("Bucket Name")
        account_id = aws_event.account
        status = notification.status
    else:
        # Simplified event format for testing
        detail = event.get('detail', {})
        check_name = detail.get('check-name', '')
        bucket_name = detail.get('check-item-detail', {}).get('Bucket Name')
        account_id = event.get('account', CALLER_ACCOUNT)
        status = detail.get('status', 'WARN')

    if check_name not in ("Amazon S3 Bucket Lifecycle Configuration", "Amazon S3 Incomplete Multipart Upload Abort Configuration"):
        logger.info('Ignoring check', extra={'check_name': check_name})
        return {'statusCode': 200, 'body': f'Ignoring check: {check_name}'}

    if not bucket_name:
        logger.error('Missing bucket name in event')
        raise ValueError('Missing Bucket Name')

    logger.info('Processing bucket', extra={
        'bucket': bucket_name,
        'account': account_id,
        'status': status
    })

    if status == "WARN":
        _apply_lifecycle_policy(account_id, bucket_name)
    else:
        logger.info('Bucket compliant', extra={'bucket': bucket_name})

    return {'statusCode': 200, 'body': f'Processed bucket {bucket_name}'}


def _apply_lifecycle_policy(account_id, bucket_name):
    """Apply lifecycle policy to abort incomplete multipart uploads."""
    s3 = _get_cross_account_client(account_id)
    if not s3:
        return

    # Get existing rules
    try:
        existing = s3.get_bucket_lifecycle_configuration(Bucket=bucket_name)
        rules = existing.get('Rules', [])
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchLifecycleConfiguration':
            rules = []
        else:
            logger.error('Failed to get lifecycle config', extra={
                'bucket': bucket_name,
                'error': e.response['Error']['Code']
            })
            return

    # Check if rule already exists (idempotent)
    if any(r.get('AbortIncompleteMultipartUpload', {}).get('DaysAfterInitiation') == 7 for r in rules):
        logger.info('Rule already exists', extra={'bucket': bucket_name})
        return

    # Add new rule
    rules.append({
        'ID': 'AbortIncompleteMultipartUploads',
        'Status': 'Enabled',
        'Filter': {},
        'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 7}
    })

    try:
        s3.put_bucket_lifecycle_configuration(
            Bucket=bucket_name,
            LifecycleConfiguration={'Rules': rules}
        )
        logger.info('Applied lifecycle policy', extra={'bucket': bucket_name})
    except ClientError as e:
        logger.error('Failed to apply lifecycle policy', extra={
            'bucket': bucket_name,
            'error': e.response['Error']['Code']
        })


def _get_cross_account_client(account_id):
    """Get S3 client for cross-account access."""
    if account_id == CALLER_ACCOUNT:
        return boto3.client('s3')

    role_arn = f"arn:aws:iam::{account_id}:role/{CROSS_ACCOUNT_ROLE_NAME}"

    try:
        sts = boto3.client('sts')
        creds = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="TALifecyclePolicy",
            ExternalId=CALLER_ACCOUNT  # Security: require external ID
        )['Credentials']

        return boto3.client(
            's3',
            aws_access_key_id=creds['AccessKeyId'],
            aws_secret_access_key=creds['SecretAccessKey'],
            aws_session_token=creds['SessionToken']
        )
    except ClientError as e:
        logger.error('Failed to assume role', extra={
            'account': account_id,
            'error': e.response['Error']['Code']
        })
        return None
