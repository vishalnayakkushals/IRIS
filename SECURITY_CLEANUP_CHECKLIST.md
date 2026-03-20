# Security Cleanup Checklist (Run At Project Sign-off)

Use this checklist only after you confirm development is complete and stable.

## Secrets
- [ ] Delete encrypted Google API key file: `data/secrets/google_api_key.enc`
- [ ] Delete encryption key file: `data/secrets/master.key`
- [ ] Revoke and rotate Google API key in Google Cloud console
- [ ] Revoke and rotate GitHub PATs used during development

## Runtime
- [ ] Stop sync background processes and disable scheduler jobs not needed in production
- [ ] Remove temporary debug logs in `data/exports/current/*.log`

## Docker
- [ ] Remove unused images/containers: `docker system prune -a`
- [ ] Clear build cache: `docker builder prune -af`

## Verification
- [ ] Confirm dashboard, sync, and exports work with new production secrets
- [ ] Confirm no secrets are present in git history, repo files, or screenshots
