"""Delete exposed IAM access key pair.

AWS Best Practices Applied:
- Initialize SDK clients outside handler for connection reuse
- Structured logging with proper log levels
- Input validation before processing
- Specific error handling with context
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

# Initialize logger - AWS recommends structured logging
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Initialize SDK client outside handler for connection reuse (AWS Best Practice)
iam = boto3.client('iam')


def lambda_handler(event, context):
    """Handle Trusted Advisor exposed key event."""
    # Input validation
    if 'detail' not in event or 'check-item-detail' not in event.get('detail', {}):
        logger.error('Invalid event structure', extra={'event': event})
        raise ValueError('Invalid Trusted Advisor event structure')

    account_id = event['account']
    time_discovered = event['time']
    details = event['detail']['check-item-detail']
    username = details.get('User Name (IAM or Root)')
    access_key_id = details.get('Access Key ID')
    exposed_location = details.get('Location')

    if not username or not access_key_id:
        logger.error('Missing required fields', extra={
            'username': username,
            'access_key_id': access_key_id
        })
        raise ValueError('Missing username or access_key_id in event')

    logger.info('Processing exposed key deletion', extra={
        'username': username,
        'access_key_id': access_key_id[:8] + '***',  # Mask key for security
        'exposed_location': exposed_location
    })

    delete_exposed_key_pair(username, access_key_id)

    return {
        'account_id': account_id,
        'time_discovered': time_discovered,
        'username': username,
        'deleted_key': access_key_id,
        'exposed_location': exposed_location
    }


def delete_exposed_key_pair(username, access_key_id):
    """Delete IAM access key pair.

    Args:
        username: IAM username
        access_key_id: Access key ID to delete
    """
    try:
        iam.delete_access_key(UserName=username, AccessKeyId=access_key_id)
        logger.info('Access key deleted successfully', extra={
            'username': username,
            'access_key_id': access_key_id[:8] + '***'
        })
    except ClientError as e:
        error_code = e.response['Error']['Code']
        logger.error('Failed to delete access key', extra={
            'username': username,
            'access_key_id': access_key_id[:8] + '***',
            'error_code': error_code,
            'error_message': str(e)
        })
        raise
