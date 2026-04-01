-- ============================================================
-- MAO 增量迁移脚本：mao_task.state_snapshot -> state_snapshot_key
-- 版本: v9.1
-- 执行时间: 2026-04-01
-- 说明: 快照正文仅存储于 Redis/DynamoDB，MySQL 仅存 state_snapshot_key
-- ============================================================

START TRANSACTION;

ALTER TABLE `mao_task`
  DROP COLUMN `state_snapshot`;

ALTER TABLE `mao_task`
  ADD COLUMN `state_snapshot_key` VARCHAR(128) DEFAULT NULL COMMENT 'StateDB 外置快照的 Key，实际快照存储于 Redis/DynamoDB' AFTER `status`;

ALTER TABLE `mao_task`
  ADD INDEX `idx_state_snapshot_key` (`state_snapshot_key`);

COMMIT;
