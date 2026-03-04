import { NextRequest, NextResponse } from "next/server";
import {
  S3Client,
  PutObjectCommand,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

const BUCKET = process.env.VCF_BUCKET_NAME!;
const REGION = process.env.AWS_REGION ?? "eu-west-2";
const PRESIGNED_EXPIRES = 900; // 15 minutes

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const vcfKey = searchParams.get("vcfKey");
  if (!vcfKey) {
    return NextResponse.json(
      { error: "vcfKey query parameter required" },
      { status: 400 }
    );
  }
  const vcfKeyLower = vcfKey.toLowerCase();
  if (!vcfKeyLower.endsWith(".vcf.gz") && !vcfKeyLower.endsWith(".vcf")) {
    return NextResponse.json(
      { error: "vcfKey must end with .vcf.gz or .vcf" },
      { status: 400 }
    );
  }

  const manifestKey = vcfKey.replace(/\.(vcf\.gz|vcf)$/i, ".manifest.json");
  const s3 = new S3Client({ region: REGION });

  const vcfContentType = vcfKeyLower.endsWith(".vcf.gz") ? "application/gzip" : "text/plain";

  const [vcfUrl, manifestUrl] = await Promise.all([
    getSignedUrl(
      s3,
      new PutObjectCommand({
        Bucket: BUCKET,
        Key: vcfKey,
        ContentType: vcfContentType,
      }),
      { expiresIn: PRESIGNED_EXPIRES }
    ),
    getSignedUrl(
      s3,
      new PutObjectCommand({
        Bucket: BUCKET,
        Key: manifestKey,
        ContentType: "application/json",
      }),
      { expiresIn: PRESIGNED_EXPIRES }
    ),
  ]);

  return NextResponse.json({ vcfUrl, manifestUrl, vcfKey, manifestKey });
}
