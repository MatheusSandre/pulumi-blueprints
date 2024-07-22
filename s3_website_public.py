import pulumi_aws as aws

from block_s3_cloudfront import S3Cloudfront
from block_cloudfront_cdn import CDN
from block_dns import DNS
from aws_s3 import S3

from cloudflare_pagerule import PageRule

class S3WebsitePublic:
    @staticmethod
    def create_architecture(environment, project_name, s3_cors_rules, prefix, certificate,
                            app_urls, cloudflare_zone_id, route53_zone_id,
                            cloudfront_bucket_log, price_class, tags):

        resource_name = f"{prefix}{project_name}"

        s3_cloudfront = S3Cloudfront.create_resources(
            project_name=project_name,
            s3_cors_rules=s3_cors_rules,
            environment=environment,
            prefix=prefix,
            tags=tags
        )

        statements = [aws.iam.GetPolicyDocumentStatementArgs(
            effect="Allow",
            principals=[aws.iam.GetPolicyDocumentStatementPrincipalArgs(
                type="AWS",
                identifiers=[s3_cloudfront["origin_access_identity"].iam_arn],
            )],
            actions=[
                "s3:GetObject"
            ],
            resources=[
                s3_cloudfront["bucket"].arn.apply(lambda arn: f"{arn}/*"),
            ],
        )]

        S3.create_policy_bucket(
            bucket_name=f"{resource_name}",
            statements=statements
        )

        ######### Cloudfront #########

        origins = [
            {
                "type": "s3",
                "dns": s3_cloudfront["bucket"].bucket_domain_name,
                "name": project_name,
                "access_identity": s3_cloudfront["origin_access_identity"].cloudfront_access_identity_path,
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
        )

        ordered_cache_behaviors = []
        custom_error_responses = []
        behaviors = {
            "default": default_behavior,
            "ordered": ordered_cache_behaviors,
            "custom_responses": custom_error_responses
        }

        cdn_dns = CDN.create_cdn(
            prefix=prefix,
            project_name=project_name,
            environment=environment,
            certificate=certificate,
            origins=origins,
            log_bucket=cloudfront_bucket_log,
            aliases=app_urls,
            behaviors=behaviors,
            price_class=price_class,
            tags=tags
        )

        for url in app_urls:
            DNS.create_resources(
                app_url=url,
                cf_zone_id=cloudflare_zone_id,
                route53_zone_id=route53_zone_id,
                dns_type="CNAME",
                dns_value=cdn_dns
            )

            if cloudflare_zone_id:
                PageRule.create_page_rule(
                    name=f"{resource_name}-cache",
                    zone_id=cloudflare_zone_id,
                    target=f"{url}/*",
                    actions={
                        "cache_level": "bypass"
                    },
                    status="active"
                )