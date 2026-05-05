# ---------------------------------------------------------------------------
# vv.genomics-resources.uk — hosted zone for the refactored app environments
# ---------------------------------------------------------------------------

resource "aws_route53_zone" "vv" {
  name = "vv.genomics-resources.uk"
}

# Wildcard ACM certificate for *.vv.genomics-resources.uk
resource "aws_acm_certificate" "vv" {
  domain_name       = "*.vv.genomics-resources.uk"
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = { Name = "${var.app_name}-vv-cert" }
}

# DNS validation records in the vv zone
resource "aws_route53_record" "cert_validation_vv" {
  for_each = {
    for dvo in aws_acm_certificate.vv.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id = aws_route53_zone.vv.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

resource "aws_acm_certificate_validation" "vv" {
  certificate_arn         = aws_acm_certificate.vv.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation_vv : r.fqdn]
}

# dev.vv.genomics-resources.uk — ALB alias (same ALB as devv.)
resource "aws_route53_record" "dev_vv" {
  zone_id = aws_route53_zone.vv.zone_id
  name    = "dev.vv.genomics-resources.uk"
  type    = "A"

  alias {
    name                   = aws_lb.app.dns_name
    zone_id                = aws_lb.app.zone_id
    evaluate_target_health = true
  }
}

# Lower SOA minimum TTL to 60s to avoid long-lived NXDOMAIN caching
# (same fix applied to the devv. zone — see project_dns_terraform memory)
resource "aws_route53_record" "vv_soa" {
  zone_id         = aws_route53_zone.vv.zone_id
  name            = "vv.genomics-resources.uk"
  type            = "SOA"
  ttl             = 60
  allow_overwrite = true

  records = [
    "${aws_route53_zone.vv.name_servers[0]}. awsdns-hostmaster.amazon.com. 1 7200 900 1209600 60"
  ]
}

# Hosted zone for the subdomain in this account.
# After first apply, copy the NS records shown in the
# "subdomain_name_servers" output into the genomics-resources.uk
# zone in the other account.
resource "aws_route53_zone" "app" {
  name = var.domain_name
}

# ACM DNS validation record
resource "aws_route53_record" "cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.app.domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  }

  zone_id = aws_route53_zone.app.zone_id
  name    = each.value.name
  type    = each.value.type
  ttl     = 60
  records = [each.value.record]
}

resource "aws_acm_certificate_validation" "app" {
  certificate_arn         = aws_acm_certificate.app.arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# ALB alias record for the subdomain
resource "aws_route53_record" "app" {
  zone_id = aws_route53_zone.app.zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.app.dns_name
    zone_id                = aws_lb.app.zone_id
    evaluate_target_health = true
  }
}
