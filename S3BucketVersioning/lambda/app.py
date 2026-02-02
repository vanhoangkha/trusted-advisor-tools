"""Enable S3 bucket versioning based on Trusted Advisor check.

AWS Best Practices Applied:
- Initialize SDK clients outside handler
- Structured logging
- Input validation
- Idempotent design (checks current state before modifying)
- Tag-based exclusion for opt-out
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

# Initialize logger
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Initialize SDK client outside handler (AWS Best Practice)
s3 = boto3.client('s3')

# Configuration
EXCLUDE_TAG = os.environ.get('EXCLUDE_TAG', 'DisableVersioning')


def lambda_handler(event, context):
    """Handle Trusted Advisor S3 versioning check event."""
    # Input validation
    if 'detail' not in event or 'check-item-detail' not in event.get('detail', {}):
        logger.error('Invalid event structure')
        raise ValueError('Invalid Trusted Advisor event structure')

    bucket_name = event['detail']['check-item-detail'].get('Bucket Name')
    if not bucket_name:
        logger.error('Missing bucket name in event')
        raise ValueError('Missing Bucket Name in event')

    logger.info('Processing bucket', extra={'bucket': bucket_name})

    # Check for exclusion tag (idempotent - respects opt-out)
    if _has_exclusion_tag(bucket_name):
        logger.info('Bucket excluded by tag', extra={'bucket': bucket_name})
        return {
            'statusCode': 200,
            'body': f'Bucket versioning intentionally disabled for {bucket_name}'
        }

    # Enable versioning
    return _enable_versioning(bucket_name)


def _has_exclusion_tag(bucket_name):
    """Check if bucket has exclusion tag."""
    try:
        tags = s3.get_bucket_tagging(Bucket=bucket_name)
        return EXCLUDE_TAG in [tag['Key'] for tag in tags.get('TagSet', [])]
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchTagSet':
            return False
        logger.warning('Failed to get bucket tags', extra={
            'bucket': bucket_name,
            'error_code': e.response['Error']['Code']
        })
        return False


def _enable_versioning(bucket_name):
    """Enable versioning on S3 bucket."""
    try:
        s3.put_bucket_versioning(
            Bucket=bucket_name,
            VersioningConfiguration={'Status': 'Enabled'}
        )
        logger.info('Versioning enabled', extra={'bucket': bucket_name})
        return {'statusCode': 200, 'body': f'Bucket versioning enabled for {bucket_name}'}
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code in ('NoSuchBucket', 'AccessDenied'):
            logger.warning('Bucket not accessible', extra={'bucket': bucket_name, 'error_code': error_code})
            return {'statusCode': 200, 'body': f'Bucket {bucket_name} not accessible: {error_code}'}
        logger.error('Failed to enable versioning', extra={'bucket': bucket_name, 'error_code': error_code})
        raise
