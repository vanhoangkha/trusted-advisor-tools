"""Release unassociated Elastic IP addresses.

AWS Best Practices Applied:
- Environment variables for configuration (DRY_RUN mode)
- Structured logging
- Input validation
- Idempotent design with tag-based exclusion
"""

import logging
import os

import boto3
from botocore.exceptions import ClientError

# Initialize logger
logger = logging.getLogger()
logger.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))

# Configuration via environment variables (AWS Best Practice)
DRY_RUN = os.environ.get('DRY_RUN', 'true').lower() == 'true'
EXCLUDE_TAG_KEY = os.environ.get('EXCLUDE_TAG_KEY', 'TrustedAdvisorAutomate')
EXCLUDE_TAG_VALUE = os.environ.get('EXCLUDE_TAG_VALUE', 'false')


def lambda_handler(event, context):
    """Handle Trusted Advisor unassociated Elastic IP event."""
    # Input validation
    if 'detail' not in event or 'check-item-detail' not in event.get('detail', {}):
        logger.error('Invalid event structure')
        raise ValueError('Invalid Trusted Advisor event structure')

    details = event['detail']['check-item-detail']
    region = details.get('Region')
    eip = details.get('IP Address')

    if not region or not eip:
        logger.error('Missing required fields', extra={'region': region, 'eip': eip})
        raise ValueError('Missing region or IP Address in event')

    logger.info('Processing Elastic IP', extra={'eip': eip, 'region': region})

    # Initialize EC2 client for specific region
    ec2 = boto3.client('ec2', region_name=region)

    try:
        addresses = ec2.describe_addresses(PublicIps=[eip])['Addresses']
        if not addresses:
            logger.warning('Elastic IP not found', extra={'eip': eip})
            return {'statusCode': 200, 'body': f'Elastic IP {eip} not found'}

        allocation_id = addresses[0]['AllocationId']
    except ClientError as e:
        if e.response['Error']['Code'] == 'InvalidAddress.NotFound':
            logger.warning('Elastic IP not found', extra={'eip': eip})
            return {'statusCode': 200, 'body': f'Elastic IP {eip} not found'}
        logger.error('Failed to describe address', extra={
            'eip': eip,
            'error_code': e.response['Error']['Code']
        })
        raise

    # Check exclusion tag
    if _should_exclude(ec2, allocation_id):
        logger.info('Elastic IP excluded by tag', extra={'eip': eip})
        return {'statusCode': 200, 'body': f'Elastic IP {eip} excluded by tag'}

    # Release the Elastic IP
    return _release_address(ec2, eip, allocation_id)


def _should_exclude(ec2, allocation_id):
    """Check if Elastic IP should be excluded based on tags."""
    try:
        tags = ec2.describe_tags(
            Filters=[{'Name': 'resource-id', 'Values': [allocation_id]}]
        )['Tags']

        for tag in tags:
            if tag['Key'] == EXCLUDE_TAG_KEY and tag['Value'].lower() == EXCLUDE_TAG_VALUE:
                return True
        return False
    except ClientError:
        return False


def _release_address(ec2, eip, allocation_id):
    """Release Elastic IP address."""
    try:
        ec2.release_address(DryRun=DRY_RUN, AllocationId=allocation_id)
        logger.info('Elastic IP released', extra={'eip': eip, 'dry_run': DRY_RUN})
        return {'statusCode': 200, 'body': f'Elastic IP {eip} released (DryRun={DRY_RUN})'}
    except ClientError as e:
        if e.response['Error']['Code'] == 'DryRunOperation':
            logger.info('DryRun successful', extra={'eip': eip})
            return {'statusCode': 200, 'body': f'DryRun: Would release {eip}'}
        logger.error('Failed to release address', extra={
            'eip': eip,
            'error_code': e.response['Error']['Code']
        })
        raise
