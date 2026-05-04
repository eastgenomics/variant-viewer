---
name: ECS debugging techniques
description: Useful patterns for debugging the live ECS containers — DB queries, connectivity checks, log inspection
type: project
originSessionId: 8256cc3d-ebf1-485b-b123-491e9f90eb74
---
## Query DB from ECS Exec

The standalone Next.js image doesn't have the AWS SDK importable directly, but `pg` is available at `/app/node_modules/pg`:

```bash
# Get DB password from secret
DB_PASS=$(AWS_PROFILE=vv-dev aws secretsmanager get-secret-value \
  --secret-id variant-viewer/db-credentials --region eu-west-2 \
  --query SecretString --output text | python3 -c "import sys,json;print(json.load(sys.stdin)['password'])")

TASK=$(AWS_PROFILE=vv-dev aws ecs list-tasks --cluster variant-viewer --region eu-west-2 --query 'taskArns[0]' --output text)

# Run a query
AWS_PROFILE=vv-dev aws ecs execute-command --cluster variant-viewer --task "$TASK" \
  --container variant-viewer --interactive \
  --command "node -e \"const{Pool}=require('/app/node_modules/pg');
    const p=new Pool({host:'variant-viewer-postgres.cdmo48w4cc9h.eu-west-2.rds.amazonaws.com',
    port:5432,database:'variants',user:'variants_admin',password:'${DB_PASS}',
    ssl:{rejectUnauthorized:false}});
    p.query('SELECT COUNT(*) FROM patients').then(r=>{console.log(r.rows);p.end();});\"" \
  --region eu-west-2
```

## Test TCP connectivity from container

```bash
node -e "const net=require('net');const s=net.connect(PORT,'HOST',()=>{console.log('reachable');s.destroy();});s.on('error',e=>console.error(e.message));"
```

## Check Secrets Manager reachability

```bash
node -e "const https=require('https');https.get('https://secretsmanager.eu-west-2.amazonaws.com',r=>console.log('SM:',r.statusCode)).on('error',e=>console.error(e.message));"
```

## Homepage shows no cases silently

The homepage (`app/page.tsx`) has a try/catch — DB errors show a red banner but patients stays empty. If no banner and no cases, check:
1. Lambda ingest logs for errors
2. Audit log for unexpected deletes: `SELECT action,entity_type,occurred_at FROM audit_log ORDER BY occurred_at DESC LIMIT 10`
3. Patient count directly via ECS Exec query above

**Note:** 404s from `/patients/[id]` with non-numeric IDs (e.g. `.php`, `wp-admin`) are bots — not real issues.

## ECS Exec output buffer limit

- ECS Exec has a practical output limit of ~6 KB before it injects `Cannot perform start session: EOF` mid-JSON, corrupting it.
- Keep node queries to `LIMIT 20` for variants (each row ~300 bytes) to stay safely under the limit.
- Use `grep '^\['` to extract JSON lines from the mixed output.
- Parse with Python `rfind(']')` walk-back to recover truncated JSON if needed.
- The `Cannot perform start session: EOF` message is appended to stdout — strip it before JSON parsing.
