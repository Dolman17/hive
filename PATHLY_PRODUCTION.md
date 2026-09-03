# Pathly production binding

Pathly production is connected through the HIVE integration platform using service key `pathly` and the production marketplace migration in `migrations/versions/20260903_pathly_integration_config.py`.

The specialist service remains independently deployed with its own PostgreSQL database and persistent uploads volume. HIVE and Pathly share Railway-generated SSO/API secrets by secure service references within the HIVE Railway project.
