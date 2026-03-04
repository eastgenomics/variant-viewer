#!/usr/bin/env node
/**
 * Simple migration runner.
 * Runs SQL migration files in order, tracking applied migrations
 * in a schema_migrations table.
 *
 * Usage: node scripts/migrate.js
 * Env: DATABASE_URL
 */

const { Pool } = require("pg");
const fs = require("fs");
const path = require("path");

async function run() {
  const pool = new Pool({ connectionString: process.env.DATABASE_URL });

  // Ensure migration tracking table exists
  await pool.query(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      version TEXT PRIMARY KEY,
      applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);

  const migrationsDir = path.join(__dirname, "..", "migrations");
  const files = fs
    .readdirSync(migrationsDir)
    .filter((f) => f.endsWith(".sql"))
    .sort();

  const client = await pool.connect();
  try {
    // Acquire advisory lock to serialize concurrent migration runners
    await client.query("SELECT pg_advisory_lock(hashtext('schema_migrations'))");

    for (const file of files) {
      const version = file.replace(".sql", "");
      const existing = await client.query(
        "SELECT version FROM schema_migrations WHERE version = $1",
        [version]
      );
      if (existing.rows.length > 0) {
        console.log(`  skipped  ${file} (already applied)`);
        continue;
      }

      const sql = fs.readFileSync(path.join(migrationsDir, file), "utf-8");
      console.log(`  applying ${file}…`);

      // Apply migration and bookkeeping atomically
      await client.query("BEGIN");
      try {
        await client.query(sql);
        await client.query(
          "INSERT INTO schema_migrations (version) VALUES ($1)",
          [version]
        );
        await client.query("COMMIT");
        console.log(`  done     ${file}`);
      } catch (err) {
        await client.query("ROLLBACK");
        throw err;
      }
    }

    // Release advisory lock
    await client.query("SELECT pg_advisory_unlock(hashtext('schema_migrations'))");
  } finally {
    client.release();
    await pool.end();
  }
  console.log("Migrations complete.");
}

run().catch((err) => {
  console.error("Migration failed:", err);
  process.exit(1);
});
