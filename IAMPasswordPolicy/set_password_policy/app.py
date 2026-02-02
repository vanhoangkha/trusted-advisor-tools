"""Set IAM password policy based on Trusted Advisor check.

AWS Best Practices Applied:
- Initialize SDK clients outside handler
- Structured logging
- Environment variables for configurable policy values
- Input validation
- Idempotent design (preserves existing settings where appropriate)
"""

import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

# Initialize logger
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Initialize SDK client outside handler (AWS Best Practice)
iam = boto3.client('iam')

# Configurable policy defaults via environment variables
DEFAULT_MIN_LENGTH = int(os.environ.get('MIN_PASSWORD_LENGTH', '12'))
DEFAULT_MAX_AGE = int(os.environ.get('MAX_PASSWORD_AGE', '90'))
DEFAULT_REUSE_PREVENTION = int(os.environ.get('PASSWORD_REUSE_PREVENTION', '12'))


def lambda_handler(event, context):
    """Handle Trusted Advisor IAM password policy check event."""
    # Input validation
    if 'detail' not in event:
        logger.error('Invalid event structure')
        raise ValueError('Invalid Trusted Advisor event structure')

    check_status = event['detail'].get('status')
    logger.info('Processing password policy check', extra={'status': check_status})

    if check_status != 'WARN':
        logger.info('Check status is not WARN, skipping')
        return {'statusCode': 200, 'body': 'No action needed'}

    # Get current policy to preserve user-configured values
    current_policy = _get_current_policy()

    # Update policy with required security settings
    return _update_password_policy(current_policy)


def _get_current_policy():
    """Get current IAM password policy."""
    try:
        return iam.get_account_password_policy()['PasswordPolicy']
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchEntity':
            logger.info('No existing password policy found')
            return {}
        raise


def _update_password_policy(current_policy):
    """Update IAM password policy with security requirements."""
    try:
        response = iam.update_account_password_policy(
            MinimumPasswordLength=current_policy.get('MinimumPasswordLength', DEFAULT_MIN_LENGTH),
            RequireSymbols=True,
            RequireNumbers=True,
            RequireUppercaseCharacters=True,
            RequireLowercaseCharacters=True,
            AllowUsersToChangePassword=current_policy.get('AllowUsersToChangePassword', True),
            PasswordReusePrevention=current_policy.get('PasswordReusePrevention', DEFAULT_REUSE_PREVENTION),
            MaxPasswordAge=current_policy.get('MaxPasswordAge', DEFAULT_MAX_AGE),
            HardExpiry=current_policy.get('HardExpiry', False),
        )
        logger.info('Password policy updated successfully')
        return {'statusCode': 200, 'body': json.dumps({'response': 'Policy updated'})}
    except ClientError as e:
        logger.error('Failed to update password policy', extra={
            'error_code': e.response['Error']['Code'],
            'error_message': str(e)
        })
        raise
