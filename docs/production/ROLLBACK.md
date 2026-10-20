# Rollback

Record the previous Git revision, image digests and database migration head before deployment. Application-only rollback selects the prior revision/images and runs Compose up after confirming schema compatibility. Never downgrade the database merely to match an image.

For an incompatible migration, stop writes, preserve a fresh dump, follow the migration's reviewed downgrade only when explicitly proven safe, or restore a verified pre-deployment backup into a fresh volume. Validate readiness, authentication, market retrieval, ledger counts and PAPER workflows before reopening.

Rollback never enables live flags. If data consistency or order state is unknown, remain closed and reconcile before any later activation.
