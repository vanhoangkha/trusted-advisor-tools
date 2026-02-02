# AWS Trusted Advisor Tools

## Overview

AWS Trusted Advisor provides real-time guidance to help users provision their resources following AWS best practices. This repository contains sample automation tools that respond to Trusted Advisor check results using Amazon EventBridge.

## Architecture

![Trusted Advisor Automation Architecture](images/ta-architecture.png)

## AWS Best Practices Applied

All solutions in this repository follow AWS Well-Architected best practices:

### Lambda Function Best Practices
- **SDK Client Initialization**: Clients initialized outside handler for connection reuse
- **Structured Logging**: JSON log format for easier filtering and analysis
- **Environment Variables**: Configuration via environment variables, not hardcoded
- **Input Validation**: All events validated before processing
- **Idempotent Design**: Functions handle duplicate events gracefully
- **Least Privilege IAM**: Minimal permissions required for each function

### Infrastructure Best Practices
- **Modern Runtimes**: Python 3.12 (latest supported)
- **ARM64 Architecture**: Cost-optimized Graviton2 processors
- **Parameterized Templates**: Configurable via CloudFormation parameters
- **Tag-based Exclusions**: Opt-out mechanism for resources

## Prerequisites

- AWS Business Support+, Enterprise Support, or Unified Operations plan (required for Trusted Advisor EventBridge integration)
- AWS SAM CLI for deployment
- Trusted Advisor events are emitted to EventBridge in **us-east-1** only

## Available Solutions

| Solution | Description | Deployment |
|----------|-------------|------------|
| [ExposedAccessKeys](ExposedAccessKeys/) | Delete exposed IAM keys, lookup CloudTrail, notify security | CloudFormation, Terraform |
| [LowUtilizationEC2Instances](LowUtilizationEC2Instances/) | Stop EC2 instances with low utilization | CloudFormation |
| [HighUtilizationEC2Instances](HighUtilizationEC2Instances/) | Resize overutilized EC2 instances with approval | CloudFormation |
| [UnderutilzedEBSVolumes](UnderutilzedEBSVolumes/) | Snapshot and delete idle EBS volumes | CloudFormation |
| [UnassociatedElasticIPs](UnassociatedElasticIPs/) | Release unassociated Elastic IPs | SAM |
| [AmazonEBSSnapshots](AmazonEBSSnapshots/) | Create snapshots for volumes without backups | CloudFormation |
| [AmazonRDSIdleDBInstances](AmazonRDSIdleDBInstances/) | Stop or delete idle RDS instances | SAM |
| [S3BucketVersioning](S3BucketVersioning/) | Enable S3 bucket versioning | SAM |
| [S3IncompleteMPUAbort](S3IncompleteMPUAbort/) | Apply lifecycle rules for incomplete uploads | SAM |
| [IAMPasswordPolicy](IAMPasswordPolicy/) | Set IAM password policy | SAM |
| [TA-Responder](TA-Responder/) | Generic framework with Bedrock AI integration | CloudFormation |
| [TA-Integrations](TA-Integrations/) | Slack webhook for cost alerts | CloudFormation |
| [TA-WellArchitected](TA-WellArchitected/) | Well-Architected Framework integration | SAM |

## Quick Start

### Deploy with SAM CLI

```bash
cd <solution-directory>
sam build
sam deploy --guided
```

### Deploy with CloudFormation

Use the "Launch Stack" buttons in each solution's README, or:

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name <stack-name> \
  --capabilities CAPABILITY_IAM \
  --region us-east-1
```

## EventBridge Event Pattern

All solutions respond to Trusted Advisor events with this pattern:

```json
{
  "source": ["aws.trustedadvisor"],
  "detail-type": ["Trusted Advisor Check Item Refresh Notification"],
  "detail": {
    "status": ["WARN", "ERROR"],
    "check-name": ["<specific-check-name>"]
  }
}
```

## Security Considerations

1. **Test in DryRun mode first** - Most solutions support DryRun mode
2. **Use tag-based exclusions** - Protect critical resources from automation
3. **Review IAM permissions** - Each solution uses least-privilege policies
4. **Monitor CloudWatch Logs** - All functions emit structured logs

## Documentation References

- [Monitoring Trusted Advisor with EventBridge](https://docs.aws.amazon.com/awssupport/latest/user/cloudwatch-events-ta.html)
- [Lambda Best Practices](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [IAM Security Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [Trusted Advisor Check Reference](https://docs.aws.amazon.com/awssupport/latest/user/trusted-advisor-check-reference.html)

## License

Apache 2.0 License. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING](CONTRIBUTING.md) for guidelines.
