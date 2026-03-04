import { Pool, PoolClient, QueryResult, QueryResultRow } from "pg";
import {
  SecretsManagerClient,
  GetSecretValueCommand,
} from "@aws-sdk/client-secrets-manager";

let pool: Pool | undefined;
let secretsResolved = false;

async function resolveSecrets(): Promise<void> {
  if (secretsResolved) return;

  const secretArn = process.env.DB_SECRET_ARN;
  if (secretArn) {
    const sm = new SecretsManagerClient({ region: process.env.AWS_REGION ?? "eu-west-2" });
    const resp = await sm.send(new GetSecretValueCommand({ SecretId: secretArn }));
    const secret = JSON.parse(resp.SecretString ?? "{}");
    // Secrets Manager stores: { username, password, host, port, dbname }
    const { username, password, host, dbname } = secret;
    if (!username || !password || !host || !dbname) {
      throw new Error(
        `DB secret ${secretArn} is missing required fields (username, password, host, dbname)`
      );
    }
    process.env.DATABASE_URL = `postgresql://${username}:${encodeURIComponent(
      password
    )}@${host}:${secret.port ?? 5432}/${dbname}`;
  }

  if (!process.env.DATABASE_URL) {
    throw new Error("DATABASE_URL or DB_SECRET_ARN must be set");
  }

  secretsResolved = true;
}

async function getPool(): Promise<Pool> {
  await resolveSecrets();

  if (!pool) {
    pool = new Pool({
      connectionString: process.env.DATABASE_URL,
      max: 10,
      idleTimeoutMillis: 30_000,
      connectionTimeoutMillis: 5_000,
      // RDS requires SSL; rejectUnauthorized false is acceptable within a private VPC
      ssl: process.env.NODE_ENV === "production" ? { rejectUnauthorized: false } : false,
    });
    pool.on("error", (err) => {
      console.error("Unexpected error on idle pg client", err);
    });
  }
  return pool;
}

export async function query<T extends QueryResultRow = QueryResultRow>(
  text: string,
  params?: unknown[]
): Promise<QueryResult<T>> {
  return (await getPool()).query<T>(text, params);
}

export async function withClient<T>(
  fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  const client = await (await getPool()).connect();
  try {
    return await fn(client);
  } finally {
    client.release();
  }
}

export async function withTransaction<T>(
  fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  return withClient(async (client) => {
    await client.query("BEGIN");
    try {
      const result = await fn(client);
      await client.query("COMMIT");
      return result;
    } catch (err) {
      await client.query("ROLLBACK");
      throw err;
    }
  });
}
