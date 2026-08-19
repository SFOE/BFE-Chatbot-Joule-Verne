# CloudFront & WAF Configuration for FastAPI + Vue Migration

This document provides the AWS CLI commands and configuration needed to update
the CloudFront distribution and WAF rules after migrating from Streamlit to
FastAPI + Vue.

## Prerequisites

- AWS CLI v2 configured with appropriate permissions
- Know your CloudFront distribution ID (`DISTRIBUTION_ID`)
- Know your WAF Web ACL ID and name (`WEB_ACL_ID`, `WEB_ACL_NAME`)
- WAF scope: `CLOUDFRONT` (must be configured in us-east-1)

---

## 1. WAF — Allow Document Uploads (fixes blocked uploads)

The upload endpoint accepts multipart POST bodies up to 50 MB total.
WAF's default body inspection limit (8 KB) causes intermittent blocking.

### Option A: Add an Allow rule before managed rules (recommended)

```bash
# Get current Web ACL configuration
aws wafv2 get-web-acl \
  --name "$WEB_ACL_NAME" \
  --scope CLOUDFRONT \
  --id "$WEB_ACL_ID" \
  --region us-east-1

# Add a rule that allows requests to /v1/documents/upload
# This must have a LOWER priority number than your managed rule groups
# so it evaluates first and short-circuits.
#
# Add this to the Rules array in your Web ACL update:
```

```json
{
  "Name": "AllowDocumentUpload",
  "Priority": 1,
  "Statement": {
    "ByteMatchStatement": {
      "SearchString": "/v1/documents/upload",
      "FieldToMatch": {
        "UriPath": {}
      },
      "TextTransformations": [
        {
          "Priority": 0,
          "Type": "NONE"
        }
      ],
      "PositionalConstraint": "STARTS_WITH"
    }
  },
  "Action": {
    "Allow": {}
  },
  "VisibilityConfig": {
    "SampledRequestsEnabled": true,
    "CloudWatchMetricsEnabled": true,
    "MetricName": "AllowDocumentUpload"
  }
}
```

### Option B: Set OversizeHandling to CONTINUE on managed rules

For each managed rule group that inspects the request body, update the
`OversizeHandling` field:

```json
{
  "ManagedRuleGroupStatement": {
    "VendorName": "AWS",
    "Name": "AWSManagedRulesCommonRuleSet"
  },
  "OverrideAction": { "None": {} },
  "RuleLabels": [],
  "Statement": {
    "ManagedRuleGroupStatement": {
      "ScopeDownStatement": {
        "NotStatement": {
          "Statement": {
            "ByteMatchStatement": {
              "SearchString": "/v1/documents/upload",
              "FieldToMatch": { "UriPath": {} },
              "TextTransformations": [{ "Priority": 0, "Type": "NONE" }],
              "PositionalConstraint": "STARTS_WITH"
            }
          }
        }
      }
    }
  }
}
```

This excludes the upload path from the managed rule group entirely.

---

## 2. CloudFront — Cache Behaviors

### Get current distribution config

```bash
aws cloudfront get-distribution-config \
  --id "$DISTRIBUTION_ID" \
  --output json > distribution-config.json
```

### Add cache behaviors

Add these to the `CacheBehaviors.Items` array (order matters — first match wins):

```json
[
  {
    "PathPattern": "/v1/*",
    "TargetOriginId": "ALB-Origin",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 7,
      "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
      "CachedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] }
    },
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3",
    "Compress": true,
    "SmoothStreaming": false
  },
  {
    "PathPattern": "/assets/*",
    "TargetOriginId": "ALB-Origin",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 2,
      "Items": ["GET", "HEAD"],
      "CachedMethods": { "Quantity": 2, "Items": ["GET", "HEAD"] }
    },
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    "Compress": true,
    "SmoothStreaming": false
  }
]
```

Cache Policy IDs (AWS managed):
- `4135ea2d-6df8-44a3-9df3-4b5a84be39ad` = **CachingDisabled**
- `658327ea-f89d-4fab-a63d-7e88639e58f6` = **CachingOptimized**

Origin Request Policy IDs (AWS managed):
- `216adef6-5c7f-47e4-b989-5492eafa07d3` = **AllViewer**

### Default behavior (SPA index.html)

The default behavior (`*`) should use **CachingDisabled** so that new deploys
are picked up immediately without invalidation:

```json
{
  "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
}
```

---

## 3. CloudFront — Increase Origin Timeouts

The agent can take 30-90 seconds to respond. Default CloudFront origin read
timeout is 30 seconds — too short.

```bash
# Update the origin configuration in the distribution
# Set OriginReadTimeout to 120 seconds (max is 180)
```

In the distribution config, update the origin:

```json
{
  "CustomOriginConfig": {
    "HTTPPort": 80,
    "HTTPSPort": 443,
    "OriginProtocolPolicy": "https-only",
    "OriginReadTimeout": 120,
    "OriginKeepaliveTimeout": 60
  }
}
```

Also update the ALB idle timeout to match:

```bash
aws elbv2 modify-load-balancer-attributes \
  --load-balancer-arn "$ALB_ARN" \
  --attributes Key=idle_timeout.timeout_seconds,Value=120
```

---

## 4. CloudFront — Response Headers Policy

Add security headers to all responses:

```bash
aws cloudfront create-response-headers-policy \
  --response-headers-policy-config '{
    "Name": "JouleVerneSecurityHeaders",
    "SecurityHeadersConfig": {
      "StrictTransportSecurity": {
        "Override": true,
        "AccessControlMaxAgeSec": 63072000,
        "IncludeSubdomains": true,
        "Preload": true
      },
      "ContentTypeOptions": {
        "Override": true
      },
      "FrameOptions": {
        "Override": true,
        "FrameOption": "DENY"
      },
      "ReferrerPolicy": {
        "Override": true,
        "ReferrerPolicy": "strict-origin-when-cross-origin"
      }
    }
  }'
```

Then attach the returned policy ID to your cache behaviors.

---

## 5. CloudFront — Cache Invalidation (post-deploy)

After each frontend deploy, invalidate the SPA entry point:

```bash
aws cloudfront create-invalidation \
  --distribution-id "$DISTRIBUTION_ID" \
  --paths "/index.html" "/"
```

Note: `/assets/*` files are content-hashed by Vite, so they never need
invalidation. API routes are uncached, so they also don't need it.

---

## 6. Enable WAF Logging (for debugging)

```bash
aws wafv2 put-logging-configuration \
  --logging-configuration '{
    "ResourceArn": "arn:aws:wafv2:us-east-1:ACCOUNT_ID:global/webacl/WEB_ACL_NAME/WEB_ACL_ID",
    "LogDestinationConfigs": [
      "arn:aws:logs:us-east-1:ACCOUNT_ID:log-group:aws-waf-logs-jouleverne"
    ],
    "RedactedFields": []
  }'
```

Then check blocked requests:

```bash
aws logs filter-log-events \
  --log-group-name "aws-waf-logs-jouleverne" \
  --filter-pattern '{ $.action = "BLOCK" }' \
  --start-time $(date -d '1 hour ago' +%s000)
```

---

## Verification Checklist

After applying these changes, verify:

- [ ] `POST /v1/documents/upload` with a 5 MB PDF succeeds (no WAF block)
- [ ] `POST /v1/chat` streams for 60+ seconds without timeout
- [ ] `GET /assets/index-*.js` returns with `Cache-Control: max-age=31536000`
- [ ] `GET /v1/health` returns with `Cache-Control: no-store` (or no cache header)
- [ ] `GET /` returns fresh `index.html` after a deploy + invalidation
- [ ] Security headers (HSTS, X-Frame-Options) present in responses
- [ ] WAF logs show upload requests as ALLOW (not BLOCK)
