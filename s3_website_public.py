import pulumi
import pulumi_aws as aws

from block_s3_cloudfront import S3Cloudfront
from block_cloudfront_cdn import CDN
from block_dns import DNS
from aws_s3 import S3
from aws_cloudfront import Cloudfront

from cloudflare_pagerule import PageRule

SPA_ROUTING_FUNCTION = """
function handler(event) {
    var request = event.request;
    var uri = request.uri;
    if (uri.endsWith('/')) {
        request.uri += 'index.html';
    } else if (!uri.includes('.')) {
        request.uri = '/index.html';
    }
    return request;
}
"""


class S3WebsitePublic:
    @staticmethod
    def create_architecture(environment, project_name, s3_cors_rules, prefix, certificate,
                            app_url, cloudflare_zone_id, route53_zone_id,
                            cloudfront_bucket_log, price_class, tags):

        resource_name = f"{prefix}{project_name}"

        s3_cloudfront = S3Cloudfront.create_resources(
            project_name=project_name,
            s3_cors_rules=s3_cors_rules,
            environment=environment,
            prefix=prefix,
            tags=tags
        )

        spa_function = Cloudfront.create_function(
            name=f"{resource_name}-spa-routing",
            code=SPA_ROUTING_FUNCTION,
            comment=f"SPA routing for {resource_name}",
            runtime="cloudfront-js-2.0",
            publish=True
        )

        ######### Cloudfront #########

        origins = [
            {
                "type": "s3",
                "dns": s3_cloudfront["bucket"].bucket_regional_domain_name,
                "name": project_name,
                "access_control_id": s3_cloudfront["origin_access_control"].id,
                "origin_shield_enabled": False,
                "origin_shield_region": "us-east-1"
            }
        ]

        default_behavior = aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
            allowed_methods=[
                "GET",
                "HEAD"
            ],
            cached_methods=[
                "GET",
                "HEAD",
            ],
            compress=True,
            default_ttl=0,
            forwarded_values=aws.cloudfront.DistributionDefaultCacheBehaviorForwardedValuesArgs(
                cookies=aws.cloudfront.DistributionDefaultCacheBehaviorForwardedValuesCookiesArgs(
                    forward="none",
                ),
                headers=[],
                query_string=False,
            ),
            max_ttl=0,
            target_origin_id=f"s3-{resource_name}-{project_name}",
            viewer_protocol_policy="redirect-to-https",
            function_associations=[
                aws.cloudfront.DistributionDefaultCacheBehaviorFunctionAssociationArgs(
                    event_type="viewer-request",
                    function_arn=spa_function.arn,
                )
            ],
        )

        ordered_cache_behaviors = []
        custom_error_responses = []
        behaviors = {
            "default": default_behavior,
            "ordered": ordered_cache_behaviors,
            "custom_responses": custom_error_responses
        }

        distribution = CDN.create_cdn(
            prefix=prefix,
            project_name=project_name,
            environment=environment,
            certificate=certificate,
            origins=origins,
            log_bucket=cloudfront_bucket_log,
            aliases=[app_url],
            behaviors=behaviors,
            price_class=price_class,
            tags=tags
        )

        bucket_policy_statements = [aws.iam.GetPolicyDocumentStatementArgs(
            sid="AllowCloudFrontServicePrincipalRead",
            effect="Allow",
            principals=[aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                type="Service",
                identifiers=["cloudfront.amazonaws.com"],
            )],
            actions=["s3:GetObject"],
            resources=[s3_cloudfront["bucket"].arn.apply(lambda arn: f"{arn}/*")],
            conditions=[aws.iam.GetPolicyDocumentStatementConditionArgs(
                test="StringEquals",
                variable="AWS:SourceArn",
                values=[distribution.arn],
            )],
        )]

        S3.create_policy_bucket(
            bucket_name=f"{resource_name}",
            statements=bucket_policy_statements
        )

        DNS.create_resources(
            app_url=app_url,
            cf_zone_id=cloudflare_zone_id,
            route53_zone_id=route53_zone_id,
            dns_type="CNAME",
            dns_value=distribution.domain_name
        )

        if cloudflare_zone_id:
            PageRule.create_page_rule(
                name=f"{resource_name}-cache",
                zone_id=cloudflare_zone_id,
                target=f"{app_url}/*",
                actions={
                    "cache_level": "bypass"
                },
                status="active"
            )
