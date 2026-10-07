---
description: Generate production SQL to retry failed VideoPost rows.
agent: build
---

Generate a guarded SQL transaction for manually retrying failed `VideoPost` rows in production.

The requested IDs are:

```text
$ARGUMENTS
```

Follow these rules exactly:

1. Parse IDs separated by whitespace and/or commas. Accept only lowercase CUIDs matching `^c[a-z0-9]{24}$`. Remove duplicates while preserving input order. If no valid IDs remain or any input token is invalid, do not generate SQL; briefly identify the invalid input.
2. Use `prod_db_query` only to inspect these exact IDs. Select only `id`, `platform`, `originPlatform`, `status`, `errorMessage`, `retryCount`, `nextRetryAt`, `processingLeaseId`, `processingLeaseExpiresAt`, `blobRef`, `mediaId`, `mediaStatus`, `containerId`, and `tiktokPublishId`. Never use a production tool to mutate data.
3. If an ID does not exist or is not currently in `error` status, mention that before the SQL. Keep every requested ID in the guarded query so the database remains the final source of truth.
4. Return one PostgreSQL code block using the template below. Replace the example ID list with safely quoted, validated IDs. Do not change the reset fields or remove the `status = 'error'` guard.
5. After the code block, state that rows not currently in `error` status will be left unchanged. Do not add unrelated guidance.

```sql
BEGIN;

WITH reset AS (
    UPDATE "VideoPost"
    SET "status" = 'pending',
        "errorMessage" = NULL,
        "retryCount" = 0,
        "nextRetryAt" = NULL,
        "processingLeaseId" = NULL,
        "processingLeaseExpiresAt" = NULL,
        "lastProgressAt" = CURRENT_TIMESTAMP,
        "blobRef" = NULL,
        "mediaId" = NULL,
        "mediaStatus" = NULL,
        "containerId" = NULL,
        "tiktokPublishId" = NULL,
        "updatedAt" = CURRENT_TIMESTAMP
    WHERE "id" IN ('example_cuid')
      AND "status" = 'error'
    RETURNING "id"
), queued AS (
    INSERT INTO "VideoPostQueueOutbox" (
        "id", "videoPostId", "availableAt", "createdAt"
    )
    SELECT gen_random_uuid()::text,
           reset."id",
           CURRENT_TIMESTAMP,
           CURRENT_TIMESTAMP
    FROM reset
    WHERE NOT EXISTS (
        SELECT 1
        FROM "VideoPostQueueOutbox" AS existing
        WHERE existing."videoPostId" = reset."id"
          AND existing."sentAt" IS NULL
    )
    RETURNING "videoPostId"
)
SELECT reset."id",
       EXISTS (
           SELECT 1
           FROM queued
           WHERE queued."videoPostId" = reset."id"
       ) AS "outboxCreated"
FROM reset
ORDER BY reset."id";

COMMIT;
```
